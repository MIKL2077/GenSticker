const assert = require('node:assert/strict')
const fs = require('node:fs'), path = require('node:path'), os = require('node:os')
const {PNG} = require('pngjs')
const {optimizePng,pngChunks,auditPackage} = require('../scripts/weixin-package.cjs')
const root = path.resolve(__dirname,'..')
const allPngs = directory => fs.readdirSync(directory,{withFileTypes:true}).flatMap(entry=>{
  const file = path.join(directory,entry.name)
  return entry.isDirectory() ? allPngs(file) : file.endsWith('.png') ? [file] : []
})
let beforeBytes=0, afterBytes=0
for (const source of allPngs(path.join(root,'src/static'))) {
  const original = fs.readFileSync(source), optimized = optimizePng(original)
  const before = PNG.sync.read(original), after = PNG.sync.read(optimized)
  assert.equal(after.width,before.width)
  assert.equal(after.height,before.height)
  assert.ok(after.data.equals(before.data),`Pixels or alpha changed: ${source}`)
  const metadata = bytes=>Buffer.concat(pngChunks(bytes).filter(chunk=>chunk.type!=='IDAT').map(chunk=>chunk.bytes))
  assert.ok(metadata(original).equals(metadata(optimized)),`PNG metadata changed: ${source}`)
  assert.ok(optimizePng(optimized).equals(optimized),'Optimization must be idempotent')
  assert.ok(optimized.length<=original.length,'Optimization must not enlarge an asset')
  beforeBytes+=original.length;afterBytes+=optimized.length
}
assert.ok(afterBytes<=200*1024,'All current PNGs must fit the image/audio budget')
assert.ok(afterBytes<beforeBytes)
assert.throws(()=>optimizePng(Buffer.from('not PNG')),/PNG/)
const example = fs.readFileSync(path.join(root,'src/static/logo.png'))
const broken = Buffer.from(example);broken[16]^=1
assert.throws(()=>optimizePng(broken),/CRC/,'Reject corruption rather than rewriting it')

const fixture = fs.mkdtempSync(path.join(os.tmpdir(),'gensticker-package-test-'))
try {
  const sdkVersion=JSON.parse(fs.readFileSync(path.join(root,'src/manifest.json'),'utf8'))['mp-weixin'].libVersion
  const project={libVersion:sdkVersion,setting:{urlCheck:true,minified:true,minifyWXML:true,minifyWXSS:true}}
  const writeProject=()=>fs.writeFileSync(path.join(fixture,'project.config.json'),JSON.stringify(project))
  writeProject()
  fs.writeFileSync(path.join(fixture,'app.json'),JSON.stringify({lazyCodeLoading:'requiredComponents'}))
  assert.equal(auditPackage(fixture).mediaBytes,0)
  project.libVersion='';writeProject()
  assert.throws(()=>auditPackage(fixture),/verified SDK version/,'An unpinned build can silently switch to an unavailable SDK')
  project.libVersion=sdkVersion;writeProject()
  project.setting.minified=false;writeProject()
  assert.throws(()=>auditPackage(fixture),/minified/,'Missing upload compression must fail')
  project.setting.minified=true;writeProject()
  fs.writeFileSync(path.join(fixture,'too-large.jpg'),Buffer.alloc(200*1024+1))
  assert.throws(()=>auditPackage(fixture),/Images\/audio total/,'Future oversized media must fail')
  fs.unlinkSync(path.join(fixture,'too-large.jpg'))
  fs.writeFileSync(path.join(fixture,'app.json'),'{}')
  assert.throws(()=>auditPackage(fixture),/lazy injection/)
} finally {fs.rmSync(fixture,{recursive:true,force:true})}
console.log(`PASS lossless PNG pixels/alpha/metadata, idempotence, CRC rejection and package gates (${beforeBytes} → ${afterBytes} media bytes)`)
