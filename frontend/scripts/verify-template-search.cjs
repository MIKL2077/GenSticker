const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const os = require('node:os')
const automator = require('miniprogram-automator')

// Real catalog + actual native input events, separate from deterministic unit tests.
async function main() {
  const output = path.resolve(process.argv[2] || fs.mkdtempSync(path.join(os.tmpdir(), 'gensticker-search-check-')))
  fs.mkdirSync(output, { recursive: true })
  const project = path.resolve(__dirname, '../dist/build/mp-weixin')
  assert.equal(JSON.parse(fs.readFileSync(path.join(project,'project.config.json'))).setting.urlCheck,true)
  const app = process.env.WECHAT_AUTOMATION_ENDPOINT
    ? await automator.connect({ wsEndpoint: process.env.WECHAT_AUTOMATION_ENDPOINT })
    : await automator.launch({
    projectPath: project,
    port: 10000 + Math.floor(Math.random()*30000),
    cliPath: process.env.WECHAT_DEVTOOLS_CLI_PATH || '/Applications/wechatwebdevtools.app/Contents/MacOS/cli',
    timeout: 60000,
  })
  const errors = []
  app.on('exception', e => errors.push(String(e.message || e)))
  const wait = async check => {
    const deadline = Date.now() + 90000
    while (Date.now() < deadline) {
      if (await check()) return
      await new Promise(resolve => setTimeout(resolve, 250))
    }
    throw Error('native catalog/input did not settle')
  }
  const state = () => app.evaluate(() => {
    const vm = getCurrentPages().slice(-1)[0]?.$vm
    if (!vm) return null
    return { loading: vm.isLoadingTemplates, query: vm.searchQuery, count: vm.searchResultCount,
      page: vm.currentPage, cards: vm.currentPageTemplates.map(x => ({ name: x.name, animated: x.animated, key: x.key })),
      error: vm.loadError }
  })
  try {
    await wait(async () => {
      try { return !!(await app.currentPage()) }
      catch (e) { if (/rawPath|getPageMetaByWebviewId/.test(e.message)) return false; throw e }
    })
    await app.reLaunch('/pages/index/index')
    await wait(async () => { const s = await state(); return s && !s.loading && s.count > 0 })
    const page = await app.currentPage()
    const input = await page.$('.template-search-input')
    const initial = await state()
    assert.equal(initial.error, '')
    const results = []
    for (const query of ['哈基米', 'ASCII', '社畜', '猫咪快乐动图', '狗，动图', 'ikun', '不开心']) {
      await input.input(query)
      await wait(async () => (await state())?.query === query)
      const result = await state()
      assert.ok(result.count > 0, 'no results for ' + query)
      assert.equal(result.page,1,'search resets pagination')
      if (query.includes('动图')) assert.ok(result.cards.every(x => x.animated), query + ' contains still output')
      if (query === 'ASCII') assert.ok(result.cards.some(x => x.key === 'charpic'))
      if (query === '不开心') assert.ok(result.cards.every(x => x.name !== '蔡徐坤满脸写着开心'))
      results.push({ query, count: result.count, visible: result.cards })
    }
    await input.input('猫咪快乐动图')
    await wait(async () => (await state())?.query === '猫咪快乐动图')
    await app.evaluate(() => wx.pageScrollTo({selector:'.template-search',duration:0}))
    await app.screenshot({ path: path.join(output, 'search-joined.png') })
    await input.input('不存在的模板测试XYZ987')
    await wait(async () => (await state())?.count === 0)
    assert.match(await (await page.$('.search-summary')).text(), /没找到/)
    await (await page.$('.search-clear')).tap()
    await wait(async () => (await state())?.query === '')
    assert.equal((await state()).count, initial.count)
    await app.evaluate(() => {
      const vm=getCurrentPages().slice(-1)[0].$vm
      vm.selectedTemplateDetail={name:'双行及上下独立文字检查',imageCount:'0-0',textCount:'2-2',defaultTexts:['第一行\n第二行','下方独立文字']}
      vm.textInputs=['第一行\n第二行','下方独立文字'];vm.showTemplateDetail=true
    })
    let fields
    await wait(async () => {
      fields=[await page.getElementByXpath('(//textarea)[1]'),await page.getElementByXpath('(//textarea)[2]')]
      return fields.every(Boolean)
    })
    const multiline=['上方第一行\n上方第二行','下方第一行\n下方第二行']
    await fields[0].input(multiline[0]);await fields[1].input(multiline[1])
    await wait(() => app.evaluate(() => getCurrentPages().slice(-1)[0].$vm.textInputs[1]==='下方第一行\n下方第二行'))
    assert.deepEqual(await app.evaluate(() => getCurrentPages().slice(-1)[0].$vm.textInputs),multiline)
    await app.screenshot({path:path.join(output,'multiline.png')})
    await app.reLaunch('/pages/index/index')
    assert.deepEqual(errors, [])
    const sdk=await app.evaluate(() => wx.getSystemInfoSync().SDKVersion)
    assert.equal(sdk,JSON.parse(fs.readFileSync(path.join(__dirname,'../src/manifest.json')))['mp-weixin'].libVersion)
    const report = { status: 'passed', sdk, baseline: initial.count, queries: results,
      checks:['pagination reset','empty state','native clear button','multiline in both independent text slots'],
      runtimeErrors: errors, scope: 'WeChat simulator; live public catalog; native input events' }
    fs.writeFileSync(path.join(output, 'search-report.json'), JSON.stringify(report, null, 2) + '\n')
    console.log(JSON.stringify(report, null, 2))
  } finally { await app.disconnect() }
}
main().catch(e => { console.error(e); process.exitCode = 1 })
