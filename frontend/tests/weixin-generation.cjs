const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')

const source = fs.readFileSync(path.join(__dirname, '../src/composables/useMemeGeneration.js'), 'utf8')
  .replace(/^import .*$/gm, '')
  .replace('export function useMemeGeneration', 'function useMemeGeneration')

async function verify() {
  const requests = [], writes = [], shares = [], statuses = []
  const context = {holdBackgroundWork:()=>()=>{},notifyGeneration:()=>{},noticeIdentity:()=>'guest',writeOwnedFile:async(filePath,data)=>{writes.push({filePath,data})},
    ref: value => ({ value }),
    rememberGuestMeme:()=>{},
    visitorHeaders: () => ({ 'X-Gensticker-Visitor': 'test-visitor-123456789' }),
    tryClientRender: async () => null,
    API_BASE_URL: 'https://example.test/api',
    getGenerateUrl: key => `/memes/${key}/`,
    getFileExtensionFromContentType: () => 'png',
    console,
    uni: {
      env: { USER_DATA_PATH: '/sandbox' },
      getStorageSync:()=>null,
      getFileSystemManager: () => ({
        stat: o => o.success({ stats: { size: 10 } }),
        readFile: o => o.success({ data: Buffer.from(o.filePath).toString('base64') }),
        writeFile: o => { writes.push(o); o.success() },
        unlink: () => {},
      }),
      request: async o => {
        requests.push(o)
        return { statusCode: 200, header: { 'content-type': 'image/png' }, data: new ArrayBuffer(8) }
      },
      showShareImageMenu: o => shares.push(o),
    },
  }
  vm.createContext(context)
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../src/services/imageGeometry.js'),'utf8').replace(/export /g,''),context)
  const preparation = fs.readFileSync(path.join(__dirname, '../src/services/imagePreparation.js'),'utf8').replace(/^import .*$/gm,'').replace(/export /g,'')
  vm.runInContext(preparation,context)
  context.encodeGenerationImages=async paths=>({images:await Promise.all(paths.map(async path=>Buffer.from(await context.prepareImage(path)).toString('base64')))})
  const sharing=fs.readFileSync(path.join(__dirname,'../src/services/wechatSharing.js'),'utf8').replace(/^import .*$/gm,'').replace(/export /g,'')
  vm.runInContext(sharing,context)
  vm.runInContext(source, context)
  const app = context.useMemeGeneration(s => statuses.push(s))
  await app.generateFromTemplate('two_images', ['/a.png', '/b.png'], ['标题', '内容'], { enabled: true })
  assert.equal(requests[0].url, 'https://example.test/api/memes/two_images/generate')
  assert.equal(requests[0].header['Content-Type'], 'application/json')
  assert.equal(requests[0].responseType, 'arraybuffer')
  assert.deepEqual(JSON.parse(JSON.stringify(requests[0].data)), {
    images: [Buffer.from('/a.png').toString('base64'), Buffer.from('/b.png').toString('base64')],
    texts: ['标题', '内容'], args: { enabled: true }, extract_subject:false,
  })
  assert.equal(writes[0].data.byteLength, 8)
  assert.match(app.generatedMeme.value, /^\/sandbox\/generated_meme_\d+\.png$/)
  app.shareMeme()
  assert.equal(shares[0].path, app.generatedMeme.value)
  let directShare
  context.wx={getEnterOptionsSync:()=>({apiCategory:'chatTool'}),shareEmojiToGroup:o=>{directShare=o}}
  app.shareMeme();assert.equal(directShare.imagePath,app.generatedMeme.value)
  context.wx=undefined
  await app.generateFromTemplate('text_only', [], ['你好'])
  assert.equal(requests[1].data.images.length, 0)
  assert.equal(requests[1].data.texts[0], '你好')
  context.uni.request = async () => ({ statusCode: 503, header: {}, data: new ArrayBuffer(0) })
  await app.generateFromTemplate('text_only', [], ['你好'])
  assert.equal(app.isGenerating.value, false)
  assert.equal(app.generatedMeme.value, '')
  assert.match(statuses.at(-1), /服务繁忙/)
  context.uni.request = async o => { requests.push(o); return { statusCode: 200, header: { 'content-type': 'image/png' }, data: new ArrayBuffer(8) } }
  const compressions = []
  context.uni.getImageInfo = o => o.success({ width: 4000, height: 3000, type: 'jpeg' })
  context.uni.compressImage = o => { compressions.push(o); o.success({ tempFilePath: '/compressed.jpg' }) }
  await app.generateFromTemplate('single', ['/camera.jpg'])
  assert.equal(compressions[0].compressedWidth, 1280)
  assert.equal(compressions[0].compressedHeight, 960)
  assert.equal(requests.at(-1).data.images[0], Buffer.from('/compressed.jpg').toString('base64'))
  await app.generateFromTemplate('single', ['/camera.jpg'], [], {}, {extractSubject:true})
  assert.equal(requests.at(-1).data.extract_subject,true)
  const originalEncoder=context.encodeGenerationImages
  context.encodeGenerationImages=async()=>({images:['colour'],image_masks:['lossless-alpha']})
  await app.generateFromTemplate('single',['/cutout.png'])
  assert.equal(requests.at(-1).data.image_masks[0],'lossless-alpha')
  context.encodeGenerationImages=originalEncoder
  context.uni.getImageInfo=o=>o.success({width:4000,height:2400,type:'jpeg',orientation:'right'})
  await context.prepareImage('/rotated-large.jpg')
  assert.equal(compressions.at(-1).compressedWidth,768,'EXIF upright width is used during compression')
  assert.equal(compressions.at(-1).compressedHeight,1280,'portrait compression must not flatten the output')
  context.uni.request = async () => { throw { errMsg: 'request:fail timeout' } }
  await app.generateFromTemplate('single', [])
  assert.match(statuses.at(-1), /网络传输超时/)
  assert.doesNotMatch(statuses.at(-1), /undefined/)
  context.uni.request = async () => ({ statusCode: 429, header: {}, data: new ArrayBuffer(0) })
  await app.generateFromTemplate('single', [])
  assert.match(statuses.at(-1), /操作太频繁/)
  context.uni.getStorageSync=()=>({access_token:'legacy-token',profile:{id:'legacy-user'}})
  context.supportsStudio=async()=>false
  let deliver
  context.uni.request = async () => new Promise(resolve => { deliver=resolve })
  const backgrounded=app.generateFromTemplate('text_only',[],['取消测试'])
  await new Promise(resolve=>setImmediate(resolve))
  app.closePreview()
  deliver({statusCode:200,header:{'content-type':'image/png'},data:new ArrayBuffer(8)})
  await backgrounded
  assert.equal(app.generatedMeme.value,'');assert.equal(app.showPreview.value,false)
  console.log('PASS: multiple images, texts, binary image, native share, text-only generation, busy server and background completion')
}
verify().catch(e => { console.error(e); process.exitCode = 1 })
