// Losslessly repack PNG IDAT streams after uni-app copies static assets.
// Pixels, PNG filters, palettes, transparency and metadata stay byte-identical
// after decompression. No resampling, quantization or remote assets are used.
const fs = require('node:fs')
const path = require('node:path')
const zlib = require('node:zlib')
const assert = require('node:assert/strict')

const MEDIA_LIMIT = 200 * 1024
const PACKAGE_LIMIT = 1.5 * 1024 * 1024
const MEDIA_EXTENSIONS = new Set(['.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.svg', '.mp3', '.wav', '.ogg', '.aac', '.m4a', '.flac'])
const SIGNATURE = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10])
const CRC_TABLE = Array.from({length:256}, (_, index) => {
  let value = index
  for (let bit = 0; bit < 8; bit++) value = value & 1 ? 0xedb88320 ^ (value >>> 1) : value >>> 1
  return value >>> 0
})
function crc32(bytes) {
  let crc = 0xffffffff
  for (const value of bytes) crc = CRC_TABLE[(crc ^ value) & 255] ^ (crc >>> 8)
  return (crc ^ 0xffffffff) >>> 0
}
function pngChunks(bytes) {
  assert.ok(bytes.subarray(0,8).equals(SIGNATURE), 'Invalid PNG signature')
  const chunks = []
  for (let offset = 8; offset < bytes.length;) {
    assert.ok(offset + 12 <= bytes.length, 'Truncated PNG chunk')
    const length = bytes.readUInt32BE(offset), end = offset + length + 12
    assert.ok(end <= bytes.length, 'Truncated PNG data')
    const chunk = bytes.subarray(offset,end), type = chunk.toString('ascii',4,8)
    assert.equal(crc32(chunk.subarray(4,chunk.length-4)), chunk.readUInt32BE(chunk.length-4), 'Invalid PNG CRC')
    chunks.push({type, bytes:chunk, data:chunk.subarray(8,chunk.length-4)})
    offset = end
  }
  assert.equal(chunks[0]?.type, 'IHDR')
  assert.equal(chunks.at(-1)?.type, 'IEND')
  assert.ok(chunks.some(chunk => chunk.type === 'IDAT'), 'Missing PNG image stream')
  return chunks
}
function idatChunk(data) {
  const bytes = Buffer.alloc(data.length + 12)
  bytes.writeUInt32BE(data.length)
  bytes.write('IDAT',4,'ascii')
  data.copy(bytes,8)
  bytes.writeUInt32BE(crc32(bytes.subarray(4,bytes.length-4)),bytes.length-4)
  return bytes
}
function optimizePng(bytes) {
  const chunks = pngChunks(bytes)
  const packed = Buffer.concat(chunks.filter(chunk=>chunk.type==='IDAT').map(chunk=>chunk.data))
  const raw = zlib.inflateSync(packed)
  let best = packed
  for (const strategy of [zlib.constants.Z_DEFAULT_STRATEGY,zlib.constants.Z_FILTERED]) {
    for (const level of [8,9]) {
      for (const memLevel of [3,4,5,6,7,8,9]) {
        const candidate = zlib.deflateSync(raw,{strategy,level,memLevel})
        if (candidate.length < best.length) best = candidate
      }
    }
  }
  assert.ok(zlib.inflateSync(best).equals(raw), 'PNG scanlines changed during compression')
  let written = false
  const output = Buffer.concat([SIGNATURE,...chunks.flatMap(chunk=>{
    if(chunk.type!=='IDAT')return [chunk.bytes]
    if(written)return []
    written = true
    return [idatChunk(best)]
  })])
  return output.length < bytes.length ? output : bytes
}
function files(directory) {
  return fs.readdirSync(directory,{withFileTypes:true}).flatMap(entry=>{
    assert.ok(!entry.isSymbolicLink(), 'Unexpected symlink in WeChat package')
    const file = path.join(directory,entry.name)
    return entry.isDirectory() ? files(file) : [file]
  })
}
function auditPackage(directory) {
  const project = JSON.parse(fs.readFileSync(path.join(directory,'project.config.json'),'utf8'))
  const app = JSON.parse(fs.readFileSync(path.join(directory,'app.json'),'utf8'))
  assert.equal(project.setting.urlCheck,true,'Keep domain validation enabled')
  for (const setting of ['minified','minifyWXML','minifyWXSS']) {
    assert.equal(project.setting[setting],true,`Enable ${setting} in manifest.json`)
  }
  assert.equal(app.lazyCodeLoading,'requiredComponents','Enable component lazy injection')
  let packageBytes = 0, mediaBytes = 0
  for (const file of files(directory)) {
    const size = fs.statSync(file).size
    packageBytes += size
    if (MEDIA_EXTENSIONS.has(path.extname(file).toLowerCase())) mediaBytes += size
  }
  assert.ok(mediaBytes<=MEDIA_LIMIT,`Images/audio total ${mediaBytes} exceeds ${MEDIA_LIMIT} bytes`)
  assert.ok(packageBytes<PACKAGE_LIMIT,`Package total ${packageBytes} exceeds the 1.5 MiB budget; review before adding subpackages`)
  return {packageBytes,mediaBytes,mediaLimitBytes:MEDIA_LIMIT}
}
function optimizePackage(directory) {
  assert.ok(directory && fs.existsSync(path.join(directory,'app.json')),'Missing WeChat build directory')
  // UiIcon names can be dynamic. Keep every name for dynamic names, and every
  // tone for unbounded tone expressions; only omit provably unreferenced pairs.
  const source=path.resolve(__dirname,'../src'),icons=path.join(directory,'static/icons')
  const names=fs.readdirSync(icons).filter(name=>name.endsWith('-ink.png')).map(name=>name.slice(0,-8))
  const tones=['ink','accent','white'],used=new Set()
  for(const file of files(source).filter(file=>file.endsWith('.vue'))) {
    const text=fs.readFileSync(file,'utf8')
    for(const match of text.matchAll(/<ui-icon\b([^>]+)>/g)) {
      const attrs=match[1],name=attrs.match(/(?:^|\s)name="([^"]+)"/),tone=attrs.match(/(?:^|\s)tone="([^"]+)"/),dynamic=attrs.match(/:tone="([^"]+)"/)
      const selectedNames=name?[name[1]]:names
      const literals=dynamic?[...dynamic[1].matchAll(/'([^']+)'/g)].map(m=>m[1]).filter(t=>tones.includes(t)):[]
      const selectedTones=tone?[tone[1]]:dynamic?(literals.length?literals:tones):['ink']
      for(const n of selectedNames)for(const t of selectedTones)used.add(`${n}-${t}.png`)
    }
  }
  for(const file of files(icons)) {
    const name=path.basename(file)
    if(!used.has(name) && !files(source).some(sourceFile=>['.js','.vue'].includes(path.extname(sourceFile)) && fs.readFileSync(sourceFile,'utf8').includes('/static/icons/'+name)))fs.unlinkSync(file)
  }
  let savedBytes = 0
  for (const file of files(directory).filter(file=>path.extname(file).toLowerCase()==='.png')) {
    const before = fs.readFileSync(file), after = optimizePng(before)
    if (after.length < before.length) {
      fs.writeFileSync(file,after)
      savedBytes += before.length-after.length
    }
  }
  return {...auditPackage(directory),savedBytes}
}
module.exports = {optimizePng,pngChunks,auditPackage,optimizePackage}
if (require.main === module) {
  const directory = process.argv[2] || path.resolve(__dirname,'../dist/build/mp-weixin')
  console.log(JSON.stringify(auditPackage(directory),null,2))
}
