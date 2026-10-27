import {registerCacheFile} from '@/services/ownedFiles'
import { apiRequest, apiImageRequest } from '@/services/apiService'
import { API_BASE_URL } from '@/constants'

// Cache outside Vue state: only small metadata and file paths cross setData.
const requests = new Map()
const cached = new Map()
const epochs = new Map()
const versions = new Map()
const animatedKeys = new Set()
const downloads = []
let activeDownloads = 0
const thumbnailSizes = new Map()
let thumbnailBytes = 0
let visibleKeys = new Set()
const evictions = new Set()
const CATALOG_CACHE='gensticker.public-catalog.v4'
const PREVIEW_CACHE='gensticker.public-previews.v4'
let diskPreviews={}
try{diskPreviews=uni.getStorageSync?.(PREVIEW_CACHE)||{}}catch(_){}
function savePreviewIndex(){try{uni.setStorageSync?.(PREVIEW_CACHE,diskPreviews)}catch(_){}}
function forgetDiskPreview(key){
  const old=diskPreviews[key]
  if(old)uni.getFileSystemManager?.().unlink({filePath:old.path,fail:()=>{}})
  delete diskPreviews[key];savePreviewIndex()
  const hit=cached.get('image:'+key)
  if(hit && (!old || hit.value===old.path)){
    cached.delete('image:'+key);thumbnailBytes-=thumbnailSizes.get(key)||0;thumbnailSizes.delete(key)
    for(const callback of evictions)callback(key)
  }
}
function rememberPreview(key,path,bytes,version){
  const evict=()=>{if(diskPreviews[key]?.path===path){delete diskPreviews[key];savePreviewIndex()}const hit=cached.get('image:'+key);if(hit?.value===path){cached.delete('image:'+key);thumbnailBytes-=thumbnailSizes.get(key)||0;thumbnailSizes.delete(key);for(const callback of evictions)callback(key)}}
  registerCacheFile(path,{bytes,protected:()=>visibleKeys.has(key),onEvict:evict})
  diskPreviews[key]={path,bytes,version,at:Date.now()};savePreviewIndex()
  const entries=Object.entries(diskPreviews).sort((a,b)=>a[1].at-b[1].at)
  let total=entries.reduce((n,[,v])=>n+v.bytes,0),count=entries.length
  for(const [old,v] of entries){if(count<=48&&total<=8*1024*1024)break;if(visibleKeys.has(old))continue;forgetDiskPreview(old);count--;total-=v.bytes}
}
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
  const epoch=epochs.get(key)||0
  const task = load().then(value => { if((epochs.get(key)||0)===epoch)cached.set(key, { value, at: Date.now() }); return value }).finally(() => {if(requests.get(key)===task)requests.delete(key)})
  requests.set(key, task)
  return task
}
function catalogVersions(data) {
  for(const card of data.cards || []) {
    if(card.animated)animatedKeys.add(card.key);else animatedKeys.delete(card.key)
    const old=versions.get(card.key)
    if(old!==undefined && old!==card.version) {
      const hit=cached.get(`image:${card.key}`)
      if(hit)uni.getFileSystemManager?.().unlink({filePath:hit.value,fail:()=>{}})
      for(const name of [`info:${card.key}`,`image:${card.key}`]) {cached.delete(name);requests.delete(name);epochs.set(name,(epochs.get(name)||0)+1)}
      thumbnailBytes-=thumbnailSizes.get(card.key)||0;thumbnailSizes.delete(card.key)
      for(const callback of evictions)callback(card.key)
      forgetDiskPreview(card.key)
    }
    versions.set(card.key,card.version)
  }
  return data
}
export function getCategories(force=false,onRefresh) {
  const refresh=()=>{
    if(force)cached.delete('categories')
    return memo('categories',()=>apiRequest('/memes/categories?compact=true',{timeout:25000},2),300000).then(data=>{
      catalogVersions(data)
      try{uni.setStorageSync?.(CATALOG_CACHE,{at:Date.now(),data})}catch(_){}
      return data
    })
  }
  if(!force){
    let saved
    try{saved=uni.getStorageSync?.(CATALOG_CACHE)}catch(_){}
    if(saved?.data?.cards?.length && Date.now()-saved.at<86400000){
      // Reopen instantly; reconcile new/withdrawn/versioned templates quietly.
      refresh().then(data=>onRefresh?.(data)).catch(()=>{})
      return Promise.resolve(catalogVersions(saved.data))
    }
  }
  return refresh()
}
export function getTemplateInfo(key) { return memo(`info:${key}`, () => apiRequest(`/memes/${encodeURIComponent(key)}/info`)) }
export function getTemplatePreviewData(key) { return apiImageRequest(`/memes/${encodeURIComponent(key)}/thumbnail`) }
export function getTemplatePreviewPath(key, background = false) {
  const version=versions.get(key)
  const url = `${API_BASE_URL}/memes/${encodeURIComponent(key)}/thumbnail${version===undefined?'?r=motion4':`?r=motion4&v=${encodeURIComponent(version)}`}`
  // #ifdef H5
  return Promise.resolve(url)
  // #endif
  // #ifndef H5
  return memo(`image:${key}`, async () => {
    const fs=uni.getFileSystemManager?.(),saved=diskPreviews[key]
    if(saved && saved.version===version && Date.now()-saved.at<7*86400000 && fs?.access){
      const exists=await new Promise(resolve=>fs.access({path:saved.path,success:()=>resolve(true),fail:()=>resolve(false)}))
      if(exists){rememberPreview(key,saved.path,saved.bytes,version);return saved.path}
      forgetDiskPreview(key)
    }
    return scheduledDownload(key, () => new Promise((resolve, reject) => {
    uni.downloadFile({ url, timeout: 20000, success: r => {
      if(r.statusCode!==200) return reject(new Error(`预览加载失败: ${r.statusCode}`))
      const finish = async bytes => {
        if(version!==versions.get(key)){uni.getFileSystemManager?.().unlink({filePath:r.tempFilePath,fail:()=>{}});reject(new Error('模板已更新，请重新加载预览'));return}
        let path=r.tempFilePath
        if(fs?.copyFile && uni.env?.USER_DATA_PATH){
          const contentType=r.header?.['Content-Type']||r.header?.['content-type']||''
          const extension=contentType.includes('gif')||animatedKeys.has(key)||/\.gif$/i.test(r.tempFilePath)?'gif':'jpg'
          const destination=`${uni.env.USER_DATA_PATH}/gensticker_material_thumb_${encodeURIComponent(key)}_${version||1}_motion4.${extension}`
          path=await new Promise(resolve=>fs.copyFile({srcPath:r.tempFilePath,destPath:destination,success:()=>resolve(destination),fail:()=>resolve(r.tempFilePath)}))
        }
        if(version!==versions.get(key)){fs?.unlink({filePath:path,fail:()=>{}});reject(new Error('模板已更新，请重新加载预览'));return}
        thumbnailBytes-=thumbnailSizes.get(key)||0;thumbnailSizes.delete(key);thumbnailSizes.set(key,bytes);thumbnailBytes+=bytes;rememberPreview(key,path,bytes,version);resolve(path);setTimeout(trimThumbnails,0)
      }
      const fs=uni.getFileSystemManager?.()
      if(fs?.stat) fs.stat({path:r.tempFilePath,success:s=>finish(s.stats.size),fail:()=>finish(256*1024)})
      else finish(256*1024)
    }, fail: reject })
  }), background)
  })
  // #endif
}
export function getGenerateUrl(templateKey) { return `/memes/${templateKey}/` }
