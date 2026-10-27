const assert = require('node:assert/strict')
const fs = require('node:fs')
const vm = require('node:vm')
const path = require('node:path')
const source = fs.readFileSync(path.join(__dirname, '../src/services/memeService.js'), 'utf8')
  .replace(/^import .*$/gm, '').replace(/export /g, '')
  .replace(/\/\/ #ifdef H5[\s\S]*?\/\/ #endif/, '')
async function verify() {
  let downloads = 0, infos = 0, failNext = true
  const context = {registerCacheFile:p=>p, setTimeout, Map, Date, Promise, Error, API_BASE_URL: 'https://example.test',
    apiRequest: async () => { infos++; return { key: 'petpet' } },
    uni: { downloadFile: o => {
      downloads++
      Promise.resolve().then(() => {
        if (failNext) { failNext = false; o.fail(new Error('offline')) }
        else o.success({ statusCode: 200, tempFilePath: '/tmp/preview.png' })
      })
    } },
  }
  Object.assign(context,require('./helpers/owned-files.cjs')(context));vm.createContext(context); vm.runInContext(source, context)
  await assert.rejects(context.getTemplatePreviewPath('petpet'), /offline/)
  const results = await Promise.all([context.getTemplatePreviewPath('petpet'), context.getTemplatePreviewPath('petpet')])
  assert.equal(downloads, 2)
  assert.equal(results[0], '/tmp/preview.png')
  assert.equal(await context.getTemplatePreviewPath('petpet'), '/tmp/preview.png')
  assert.equal(downloads, 2)
  await Promise.all([context.getTemplateInfo('petpet'), context.getTemplateInfo('petpet')])
  assert.equal(infos, 1)
  console.log('PASS: file paths, shared requests, failed download retry, metadata cache')
}
verify().catch(e => { console.error(e); process.exitCode = 1 })
