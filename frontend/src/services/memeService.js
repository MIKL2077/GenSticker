import { apiRequest, apiImageRequest } from '@/services/apiService'
import { API_BASE_URL } from '@/constants'

// Cache outside Vue state: only small metadata and file paths cross setData.
const requests = new Map()
const cached = new Map()
const downloads = []
let activeDownloads = 0
const thumbnailSizes = new Map()
let thumbnailBytes = 0
let visibleKeys = new Set()
const evictions = new Set()
export function onThumbnailEvict(callback) { evictions.add(callback); return () => evictions.delete(callback) }
export function setThumbnailWindow(keys) {
  visibleKeys = new Set(keys)
  downloads.sort((a,b) => Number(visibleKeys.has(b.key))-Number(visibleKeys.has(a.key)))
}
function trimThumbnails() {
  for(const [key,bytes] of thumbnailSizes) {
    if(thumbnailSizes.size<=96 && thumbnailBytes<=8*1024*1024) break
    if(visibleKeys.has(key)) continue
    const hit=cached.get(`image:${key}`)
    if(hit) uni.getFileSystemManager?.().unlink({filePath:hit.value,fail:()=>{}})
    cached.delete(`image:${key}`);thumbnailSizes.delete(key);thumbnailBytes-=bytes
    for(const callback of evictions) callback(key)
  }
}
function drainDownloads() {
  while (activeDownloads < 4 && downloads.length) {
    const task = downloads.shift(); activeDownloads++
    task.run().then(task.resolve, task.reject).finally(() => { activeDownloads--; drainDownloads() })
  }
}
function scheduledDownload(key, run, background) {
  return new Promise((resolve, reject) => { const task = { key, run, resolve, reject }; if(downloads.length>=72) return reject(new Error('预加载队列已满')); background ? downloads.push(task) : downloads.unshift(task); drainDownloads() })
}
function memo(key, load, ttl = 3600000) {
  const hit = cached.get(key)
  if (hit && Date.now() - hit.at < ttl) return Promise.resolve(hit.value)
  if (requests.has(key)) return requests.get(key)
  const task = load().then(value => { cached.set(key, { value, at: Date.now() }); return value }).finally(() => requests.delete(key))
  requests.set(key, task)
  return task
}
export function getCategories(force=false) { if(force)cached.delete('categories');return memo('categories', () => apiRequest('/memes/categories',{timeout:25000},2), 300000) }
export function getTemplateInfo(key) { return memo(`info:${key}`, () => apiRequest(`/memes/${encodeURIComponent(key)}/info`)) }
export function getTemplatePreviewData(key) { return apiImageRequest(`/memes/${encodeURIComponent(key)}/thumbnail`) }
export function getTemplatePreviewPath(key, background = false) {
  const url = `${API_BASE_URL}/memes/${encodeURIComponent(key)}/thumbnail`
  // #ifdef H5
  return Promise.resolve(url)
  // #endif
  // #ifndef H5
  return memo(`image:${key}`, () => scheduledDownload(key, () => new Promise((resolve, reject) => {
    uni.downloadFile({ url, timeout: 20000, success: r => {
      if(r.statusCode!==200) return reject(new Error(`预览加载失败: ${r.statusCode}`))
      const finish = bytes => { thumbnailBytes-=thumbnailSizes.get(key)||0;thumbnailSizes.delete(key);thumbnailSizes.set(key,bytes);thumbnailBytes+=bytes;resolve(r.tempFilePath);setTimeout(trimThumbnails,0) }
      const fs=uni.getFileSystemManager?.()
      if(fs?.stat) fs.stat({path:r.tempFilePath,success:s=>finish(s.stats.size),fail:()=>finish(256*1024)})
      else finish(256*1024)
    }, fail: reject })
  }), background))
  // #endif
}
export function getGenerateUrl(templateKey) { return `/memes/${templateKey}/` }
