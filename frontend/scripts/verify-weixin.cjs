const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const automator = require('miniprogram-automator')

// Run against the production build in WeChat, including its second compiler.
const args = process.argv.slice(2)
const options = {}
for (let i = 0; i < args.length; i += 2) {
  if (!['--project', '--ws-endpoint', '--output-dir', '--screenshots'].includes(args[i]) || !args[i + 1]) {
    throw Error('Usage: node scripts/verify-weixin.cjs [--project path] [--ws-endpoint ws://127.0.0.1:port] [--output-dir path] [--screenshots on|off]')
  }
  options[args[i].slice(2)] = args[i + 1]
}
const build = path.resolve(options.project || path.join(__dirname, '../dist/build/mp-weixin'))
const output = path.resolve(options['output-dir'] || fs.mkdtempSync(path.join(os.tmpdir(), 'gensticker-weixin-check-')))
if (options.screenshots && !['on', 'off'].includes(options.screenshots)) throw Error('--screenshots must be on or off')
const screenshots = options.screenshots !== 'off'
const pause = ms => new Promise(resolve => setTimeout(resolve, ms))

async function verify() {
  const config = JSON.parse(fs.readFileSync(path.join(build, 'project.config.json'), 'utf8'))
  assert.equal(config.setting.urlCheck, true, 'WeChat domain validation must remain enabled')
  let project = build
  if (!options.project && !options['ws-endpoint']) {
    // Match preview: import the actual build without old machine-only settings.
    project = fs.mkdtempSync(path.join(os.tmpdir(), 'gensticker-weixin-check-project-'))
    fs.cpSync(build, project, { recursive: true, filter: file => path.basename(file) !== 'project.private.config.json' })
    config.projectname = 'GenSticker-check-' + path.basename(project).split('-').at(-1)
    fs.writeFileSync(path.join(project, 'project.config.json'), JSON.stringify(config, null, 2) + '\n')
  }
  fs.mkdirSync(output, { recursive: true })
  const app = options['ws-endpoint']
    ? await automator.connect({ wsEndpoint: options['ws-endpoint'] })
    : await automator.launch({
      projectPath: project,
      cliPath: process.env.WECHAT_DEVTOOLS_CLI_PATH || '/Applications/wechatwebdevtools.app/Contents/MacOS/cli',
      timeout: 60000,
    })
  console.log('WeChat connected:', project)
  const errors = []
  app.on('exception', error => errors.push(String(error.message || error)))
  app.on('console', entry => {
    const message = (entry.args || []).map(value => typeof value === 'string' ? value : value?.stack || '').join('\n')
    if (entry.type === 'error' && /MiniProgramError|appServiceSDKScriptError|read-only|ReferenceError|SyntaxError/.test(message)) errors.push(message)
  })
  async function waitFor(check, description, timeout = 30000) {
    const deadline = Date.now() + timeout
    do {
      assert.deepEqual(errors, [], 'WeChat runtime exception')
      if (await check()) return
      await pause(250)
    } while (Date.now() < deadline)
    throw Error('Timed out: ' + description)
  }
  async function currentPage() {
    try { return await app.currentPage() }
    catch (error) {
      // A new WeChat project can expose the automation socket before its first
      // webview metadata exists. Wait for that native lifecycle to finish.
      if (/rawPath|getPageMetaByWebviewId/.test(error.message)) return null
      throw error
    }
  }
  async function pageReady(selector, route) {
    await waitFor(() => app.evaluate(expected => {
      const page = getCurrentPages().slice(-1)[0]
      return page?.route === expected && !!page.$vm
    }, route), route + ' Vue initialization', 10000)
    let page
    await waitFor(async () => { page = await currentPage(); return page?.path === route }, route + ' native webview')
    await waitFor(() => page.$(selector), selector + ' rendered')
    return page
  }
  try {
    await waitFor(async () => !!(await currentPage()), 'initial WeChat webview')
    const sdkVersion = await app.evaluate(() => wx.getSystemInfoSync().SDKVersion)
    const expectedSdk = JSON.parse(fs.readFileSync(path.join(__dirname,'../src/manifest.json'),'utf8'))['mp-weixin'].libVersion
    assert.equal(sdkVersion, expectedSdk, 'DevTools must run the verified SDK; check the project local settings')
    await app.reLaunch('/pages/index/index')
    const home = await pageReady('.live-entry', 'pages/index/index')
    assert.match(await (await home.$('.live-entry')).text(), /视频转 GIF/)
    await waitFor(() => app.evaluate(() => {
      const vm = getCurrentPages().slice(-1)[0].$vm
      return !vm.isLoadingTemplates && (vm.currentPageTemplates?.length > 0 || !!vm.loadError)
    }), 'real API template loading', 90000)
    const templates = await app.evaluate(() => {
      const vm = getCurrentPages().slice(-1)[0].$vm
      return { count: vm.currentPageTemplates.length, error: vm.loadError || '' }
    })
    assert.equal(templates.error, '', 'real template API must load')
    assert.ok(templates.count > 0, 'home must render templates')
    if (screenshots) await app.screenshot({ path: path.join(output, 'home.png') })

    await (await home.$('.live-entry')).tap()
    const video = await pageReady('.live-tip', 'pages/live/index')
    assert.equal(video.path, 'pages/live/index')
    const welcome = await video.$('.welcome')
    assert.equal((await welcome.$$('button')).length, 1, 'only the video picker remains')
    assert.match(await (await welcome.$('button')).text(), /从相册选视频/)
    assert.match(await (await video.$('.live-tip')).text(), /手机相册.*存储为视频/)
    if (screenshots) await app.screenshot({ path: path.join(output, 'video.png') })

    await app.switchTab('/pages/my/index')
    await pageReady('.my-page', 'pages/my/index')
    await app.navigateTo('/pages/recommend/index')
    await pageReady('.recommend-page', 'pages/recommend/index')
    await app.navigateTo('/pages/queue/index')
    await pageReady('.queue-page', 'pages/queue/index')
    await app.reLaunch('/pages/create/index')
    await pageReady('.create-page', 'pages/create/index')
    await app.navigateTo('/pages/library/index?type=history')
    await pageReady('.library-page', 'pages/library/index')
    await app.reLaunch('/pages/index/index')
    await pageReady('.live-entry', 'pages/index/index')
    assert.deepEqual(errors, [], 'no WeChat initialization errors across pages')
    const performanceEntries = await app.evaluate(() => {
      try {
        return wx.getPerformance().getEntries().filter(entry => ['navigation', 'render', 'script'].includes(entry.entryType)).map(entry => ({ name: entry.name, type: entry.entryType, startTime: entry.startTime, duration: entry.duration }))
      } catch (_) { return [] }
    })
    const report = { status: 'passed', templateCount: templates.count, pages: ['index', 'live', 'my', 'recommend', 'queue', 'create', 'library'], videoPickerCount: 1, liveGuidance: true, runtimeErrors: errors, domainValidation: true, screenshots, performanceScope: 'WeChat simulator entries; not physical-device or SDK-wait wall time', performanceEntries }
    fs.writeFileSync(path.join(output, 'report.json'), JSON.stringify({ ...report, sdkVersion }, null, 2) + '\n')
    console.log('PASS WeChat production startup, real templates, video-only entry, Live guidance and seven pages')
    console.log('Evidence:', output)
  } finally {
    await app.disconnect()
  }
}
const watchdog = setTimeout(() => { console.error('WeChat verification timed out; check the DevTools login, CLI port and simulator console.'); process.exit(1) }, 180000)
watchdog.unref()
verify().catch(error => { console.error(error); process.exitCode = 1 }).finally(() => clearTimeout(watchdog))
