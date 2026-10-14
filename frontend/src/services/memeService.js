import { apiRequest, apiImageRequest } from '@/services/apiService'
import { API_BASE_URL } from '@/constants'

// Cache outside Vue state: only small metadata and file paths cross setData.
const requests = new Map()
const cached = new Map()
const downloads = []
let activeDownloads = 0
function drainDownloads() {
  while (activeDownloads < 4 && downloads.length) {
    const task = downloads.shift(); activeDownloads++
    task.run().then(task.resolve, task.reject).finally(() => { activeDownloads--; drainDownloads() })
  }
}
function scheduledDownload(run, background) {
  return new Promise((resolve, reject) => { const task = { run, resolve, reject }; background ? downloads.push(task) : downloads.unshift(task); drainDownloads() })
}
function memo(key, load, ttl = 3600000) {
  const hit = cached.get(key)
  if (hit && Date.now() - hit.at < ttl) return Promise.resolve(hit.value)
  if (requests.has(key)) return requests.get(key)
  const task = load().then(value => { cached.set(key, { value, at: Date.now() }); return value }).finally(() => requests.delete(key))
  requests.set(key, task)
  return task
}
export function getCategories() { return memo('categories', () => apiRequest('/memes/categories'), 300000) }
export function getTemplateInfo(key) { return memo(`info:${key}`, () => apiRequest(`/memes/${encodeURIComponent(key)}/info`)) }
export function getTemplatePreviewData(key) { return apiImageRequest(`/memes/${encodeURIComponent(key)}/thumbnail`) }
export function getTemplatePreviewPath(key, background = false) {
  const url = `${API_BASE_URL}/memes/${encodeURIComponent(key)}/thumbnail`
  // #ifdef H5
  return Promise.resolve(url)
  // #endif
  // #ifndef H5
  return memo(`image:${key}`, () => scheduledDownload(() => new Promise((resolve, reject) => {
    uni.downloadFile({ url, timeout: 20000, success: r => r.statusCode === 200 ? resolve(r.tempFilePath) : reject(new Error(`预览加载失败: ${r.statusCode}`)), fail: reject })
  }), background))
  // #endif
}
export function getGenerateUrl(templateKey) { return `/memes/${templateKey}/` }
