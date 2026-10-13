const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')

const source = fs.readFileSync(path.join(__dirname, '../src/composables/useMemeGeneration.js'), 'utf8')
  .replace(/^import .*$/gm, '')
  .replace('export function useMemeGeneration', 'function useMemeGeneration')

async function verify() {
  const requests = [], writes = [], shares = [], statuses = []
  const context = {
    ref: value => ({ value }),
    API_BASE_URL: 'https://example.test/api',
    getGenerateUrl: key => `/memes/${key}/`,
    getFileExtensionFromContentType: () => 'png',
    console,
    uni: {
      env: { USER_DATA_PATH: '/sandbox' },
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
  vm.runInContext(source, context)
  const app = context.useMemeGeneration(s => statuses.push(s))
  await app.generateFromTemplate('two_images', ['/a.png', '/b.png'], ['标题', '内容'], { enabled: true })
  assert.equal(requests[0].url, 'https://example.test/api/memes/two_images/generate')
  assert.equal(requests[0].header['Content-Type'], 'application/json')
  assert.equal(requests[0].responseType, 'arraybuffer')
  assert.deepEqual(JSON.parse(JSON.stringify(requests[0].data)), {
    images: [Buffer.from('/a.png').toString('base64'), Buffer.from('/b.png').toString('base64')],
    texts: ['标题', '内容'], args: { enabled: true },
  })
  assert.equal(writes[0].data.byteLength, 8)
  assert.match(app.generatedMeme.value, /^\/sandbox\/generated_meme_\d+\.png$/)
  app.shareMeme()
  assert.equal(shares[0].path, app.generatedMeme.value)
  await app.generateFromTemplate('text_only', [], ['你好'])
  assert.equal(requests[1].data.images.length, 0)
  assert.equal(requests[1].data.texts[0], '你好')
  context.uni.request = async () => ({ statusCode: 503, header: {}, data: new ArrayBuffer(0) })
  await app.generateFromTemplate('text_only', [], ['你好'])
  assert.equal(app.isGenerating.value, false)
  assert.equal(app.generatedMeme.value, '')
  assert.match(statuses.at(-1), /服务繁忙/)
  console.log('PASS: multiple images, texts, binary image, native share, text-only generation, busy server')
}
verify().catch(e => { console.error(e); process.exitCode = 1 })
