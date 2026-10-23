const assert = require('node:assert/strict')
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm')
const {ref, computed, watch, nextTick, effectScope} = require('vue')
const source = fs.readFileSync(path.join(__dirname, '../src/components/FirstUseGuide.vue'), 'utf8')
  .split('<script>')[1].split('</script>')[0].replace(/^import .*$/gm, '').replace('export default', 'const component =')

async function verify() {
  const storage = new Map(), session = ref(null)
  const scopes = []
  function mount() {
    const hooks = {}, scope = effectScope()
    scopes.push(scope)
    const context = {ref, computed, watch, UiIcon:{}, useLibrary:()=>({session}),
      onShow:fn=>hooks.show=fn, onHide:fn=>hooks.hide=fn, onUnload:fn=>hooks.unload=fn,
      uni:{getStorageSync:key=>storage.get(key), setStorageSync:(key,value)=>storage.set(key,value)}}
    vm.createContext(context)
    scope.run(()=>vm.runInContext(source+'\nthis.guide=component.setup()', context))
    return {guide:context.guide, hooks}
  }
  try {
    const home = mount(), destination = mount()
    home.hooks.show()
    assert.equal(home.guide.visible.value, false, 'guests are not interrupted by a login guide')
    session.value = {profile:{id:'first-user'}}
    await nextTick()
    assert.equal(home.guide.visible.value, true, 'first login opens the guide on the active page')
    assert.equal(destination.guide.visible.value, false, 'hidden pages do not open a second guide')
    home.guide.next()
    assert.equal(home.guide.current.value.title, '生成队列')
    home.guide.next()
    assert.equal(home.guide.current.value.title, '一键生成')
    home.guide.next()
    assert.equal(home.guide.visible.value, false)
    home.hooks.hide(); destination.hooks.show()
    assert.equal(destination.guide.visible.value, false, 'completion survives navigation to another mounted page')
    const reopened = mount(); reopened.hooks.show()
    assert.equal(reopened.guide.visible.value, false, 'completion survives a fresh component instance')
    reopened.hooks.hide()
    session.value = null; await nextTick()
    session.value = {profile:{id:'first-user'}}; await nextTick()
    assert.equal(destination.guide.visible.value, false, 'logging in again does not repeat a completed guide')
    session.value = {profile:{id:'second-user'}}; await nextTick()
    assert.equal(destination.guide.visible.value, true, 'another account gets its own guide')
    assert.equal(destination.guide.step.value, 0)
    destination.guide.finish()
    destination.hooks.hide(); destination.hooks.show()
    assert.equal(destination.guide.visible.value, false, 'skipping also persists')
    session.value = {profile:{id:'third-user'}}; await nextTick()
    destination.guide.next()
    destination.hooks.hide(); destination.hooks.show()
    assert.equal(destination.guide.current.value.title, '生成队列', 'temporary backgrounding preserves progress')
    destination.hooks.unload()
    assert.equal(destination.guide.visible.value, false)
    console.log('PASS first-login guide, three steps, page visibility, completion persistence, re-login, account isolation and skip')
  } finally { scopes.forEach(scope=>scope.stop()) }
}
verify().catch(error=>{console.error(error);process.exitCode=1})
