const assert = require('node:assert/strict')
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm')
const source = fs.readFileSync(path.join(__dirname, '../src/composables/useLibrary.js'), 'utf8')
  .replace(/^import .*$/gm, '').replace('export function useLibrary', 'function useLibrary')
  .replace(/\/\/ #ifndef MP-WEIXIN[\s\S]*?\/\/ #endif/g, '')
const clone = value => JSON.parse(JSON.stringify(value))
const storage = new Map(), calls = []
let remote = { favorite_keys: [], history: [] }
const context = {
  ref: value => ({ value }), computed: getter => ({ get value() { return getter() } }), console,
  uni: { getStorageSync: key => storage.get(key), setStorageSync: (k, v) => storage.set(k, clone(v)), removeStorageSync: k => storage.delete(k), login: o => o.success({ code: 'test-code' }) },
  apiRequest: async (url, options = {}) => {
    calls.push({ url, options })
    if (url === '/account/config') return { login_enabled: true }
    if (url === '/auth/wechat') return { access_token: 'test-token', expires_at: Date.now() / 1000 + 600, profile: { id: 'user-a', name: '微信用户' } }
    if (url === '/account/library/merge') { remote = clone(options.data); return clone(remote) }
    if (url === '/account/library') return clone(remote)
    return null
  },
}
vm.createContext(context); vm.runInContext(source, context)
;(async () => {
  const a = context.useLibrary()
  a.recordVisit('one'); a.recordVisit('two'); a.recordVisit('one')
  assert.deepEqual(clone(a.library.value.history.map(r => r.key)), ['one', 'two'])
  assert.equal(a.toggleFavorite('one'), true)
  assert.equal(a.toggleFavorite('one'), false)
  a.toggleFavorite('two')
  for (let i = 0; i < 110; i++) a.recordVisit('key-' + i)
  assert.equal(a.historyCount.value, 100)
  await a.loginWeChat()
  assert.equal(a.session.value.profile.id, 'user-a')
  await a.syncLibrary() // Login returns immediately; migration completes in the background.
  assert.equal(remote.favorite_keys[0], 'two')
  assert.equal(remote.history.length, 100)
  assert.equal(storage.has('gensticker.library.guest.v1'), false)
  assert.ok(storage.has('gensticker.library.user-a.v1'))
  await a.logout()
  assert.equal(a.session.value, null)
  assert.equal(a.historyCount.value, 0)
  assert.equal(a.favoritesCount.value, 0)
  assert.ok(calls.some(c => c.url === '/auth/session' && c.options.method === 'DELETE'))
  console.log('PASS: guest history deduplication and limit, favorite toggle, login migration, account cache isolation, logout')
})().catch(e => { console.error(e); process.exitCode = 1 })
