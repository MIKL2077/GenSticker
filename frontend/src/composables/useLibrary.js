import { ref, computed } from 'vue'
import { apiRequest } from '@/services/apiService'

const SESSION_KEY = 'gensticker.session.v1'
const GUEST_KEY = 'gensticker.library.guest.v1'
const empty = () => ({ favorite_keys: [], history: [], pending: [] })
const read = key => { try { return uni.getStorageSync(key) || null } catch (_) { return null } }
const session = ref(read(SESSION_KEY))
if (session.value?.expires_at <= Date.now() / 1000) { session.value = null; uni.removeStorageSync(SESSION_KEY) }
const owner = () => session.value?.profile?.id || 'guest'
const storageKey = id => id === 'guest' ? GUEST_KEY : `gensticker.library.${id}.v1`
const load = id => {
  const data = read(storageKey(id)) || {}
  return {
    favorite_keys: Array.isArray(data.favorite_keys) ? data.favorite_keys.filter(k => typeof k === 'string').slice(0, 100) : [],
    history: Array.isArray(data.history) ? data.history.filter(r => typeof r?.key === 'string' && Number.isFinite(r.visited_at)).slice(0, 100) : [],
    pending: Array.isArray(data.pending) ? data.pending : [],
  }
}
const library = ref(load(owner()))
const syncError = ref('')
const loggingIn = ref(false)
let syncing = null
let sequence = 0
const persist = () => uni.setStorageSync(storageKey(owner()), JSON.parse(JSON.stringify(library.value)))
const enqueue = op => {
  if (!session.value) return
  // Preserve clear/merge boundaries; collapse only adjacent updates to the same record.
  const pending = library.value.pending
  const last = pending[pending.length - 1]
  if (last?.type === op.type && last?.key === op.key && !['merge', 'clear'].includes(op.type)) pending.pop()
  pending.push({ ...op, id: `${Date.now()}-${++sequence}` })
}

async function flush() {
  const id = owner()
  if (id === 'guest') return
  const header = { Authorization: `Bearer ${session.value.access_token}` }
  while (owner() === id && library.value.pending.length) {
    const op = library.value.pending[0]
    if (op.type === 'favorite') await apiRequest(`/account/favorites/${encodeURIComponent(op.key)}`, { method: op.value ? 'PUT' : 'DELETE', header })
    if (op.type === 'visit') await apiRequest(`/account/history/${encodeURIComponent(op.key)}`, { method: 'PUT', header })
    if (op.type === 'clear') await apiRequest('/account/history', { method: 'DELETE', header })
    if (op.type === 'merge') { await apiRequest('/account/library/merge', { method: 'POST', data: op.data, header }); uni.removeStorageSync(GUEST_KEY) }
    if (owner() !== id) return
    library.value.pending = library.value.pending.filter(p => p.id !== op.id)
    persist()
  }
}

function syncLibrary() {
  if (!session.value) return Promise.resolve()
  if (syncing) return syncing
  const id = owner()
  syncing = (async () => {
    try {
      await flush()
      if (owner() !== id) return
      const data = await apiRequest('/account/library')
      // Do not overwrite new optimistic edits made during the fetch.
      if (owner() === id && !library.value.pending.length) { library.value = { ...empty(), ...data }; persist() }
      syncError.value = ''
    } catch (e) {
      syncError.value = e.statusCode === 401 ? '登录已过期，请重新登录；本机记录已保留' : '记录已保存在本机，联网后可重试同步'
      if (e.statusCode === 401 && owner() === id) { session.value = null; uni.removeStorageSync(SESSION_KEY); library.value = load('guest') }
    } finally { syncing = null }
  })()
  return syncing
}

function recordVisit(key) {
  library.value.history = [{ key, visited_at: Date.now() }, ...library.value.history.filter(r => r.key !== key)].slice(0, 100)
  enqueue({ type: 'visit', key }); persist(); syncLibrary()
}

function toggleFavorite(key) {
  const value = !library.value.favorite_keys.includes(key)
  if (value && library.value.favorite_keys.length >= 100) throw new Error('收藏最多 100 个模板')
  library.value.favorite_keys = value ? [key, ...library.value.favorite_keys] : library.value.favorite_keys.filter(k => k !== key)
  enqueue({ type: 'favorite', key, value }); persist(); syncLibrary()
  return value
}

function clearHistory() {
  library.value.history = []; enqueue({ type: 'clear' }); persist(); syncLibrary()
}

async function loginWeChat() {
  if (loggingIn.value) return
  loggingIn.value = true
  try {
    const config = await apiRequest('/account/config', { auth: false })
    if (!config.login_enabled) throw new Error('微信登录尚未配置；历史与收藏仍可在本机使用')
    // #ifndef MP-WEIXIN
    throw new Error('请在微信小程序中登录')
    // #endif
    // #ifdef MP-WEIXIN
    const credentials = await new Promise((resolve, reject) => uni.login({ provider: 'weixin', success: resolve, fail: reject }))
    if (!credentials.code) throw new Error('未获得微信登录凭证，请重试')
    const account = await apiRequest('/auth/wechat', { method: 'POST', data: { code: credentials.code }, auth: false }, 1)
    const guest = load('guest')
    session.value = account; uni.setStorageSync(SESSION_KEY, account)
    library.value = load(owner())
    if (guest.favorite_keys.length || guest.history.length) {
      library.value.favorite_keys = [...new Set([...library.value.favorite_keys, ...guest.favorite_keys])].slice(0, 100)
      const records = new Map()
      for (const r of [...library.value.history, ...guest.history]) if (!records.has(r.key) || records.get(r.key).visited_at < r.visited_at) records.set(r.key, r)
      library.value.history = [...records.values()].sort((a, b) => b.visited_at - a.visited_at).slice(0, 100)
      enqueue({ type: 'merge', data: { favorite_keys: guest.favorite_keys, history: guest.history } })
      persist()
    }
    await syncLibrary()
    // #endif
  } finally { loggingIn.value = false }
}

async function logout() {
  await syncLibrary()
  if (session.value) {
    try { await apiRequest('/auth/session', { method: 'DELETE' }) }
    catch (e) { if (e.statusCode && e.statusCode !== 401) throw e }
  }
  session.value = null; uni.removeStorageSync(SESSION_KEY); library.value = load('guest'); syncError.value = ''
}

export function useLibrary() {
  return { session, library, syncError, loggingIn, loginWeChat, logout, syncLibrary, recordVisit, toggleFavorite, clearHistory,
    favoritesCount: computed(() => library.value.favorite_keys.length), historyCount: computed(() => library.value.history.length),
    isFavorite: key => library.value.favorite_keys.includes(key) }
}
