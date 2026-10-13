import { apiRequest } from '@/services/apiService'
import { API_BASE_URL } from '@/constants'

const token = () => uni.getStorageSync('gensticker.session.v1')?.access_token
export const getQuota = () => apiRequest('/recommend/quota', {}, 1)
export const listJobs = () => apiRequest('/recommend/jobs', {}, 1)
export const getJob = id => apiRequest(`/recommend/jobs/${id}`, {}, 1)
export const createJob = (asset_id, idempotency_key) => apiRequest('/recommend/jobs', { method:'POST', data:{asset_id,idempotency_key} }, 1)
export const selectResults = (id, slots, action = 'choose') => apiRequest(`/recommend/jobs/${id}/selections`, { method:'POST', data:{event_id:`${Date.now()}-${Math.random().toString(36).slice(2)}`, slots, action} }, 1)
export const removeJob = id => apiRequest(`/recommend/jobs/${id}`, { method:'DELETE' }, 1)
export const setPersonalization = enabled => apiRequest('/recommend/preferences', { method:'PUT', data:{enabled} }, 1)

export async function uploadPhoto(path) {
  const info = await uni.getImageInfo({ src:path })
  if (info.type === 'jpeg' || info.type === 'jpg') {
    const scale = Math.min(1,1280 / Math.max(info.width,info.height))
    const compressed = await uni.compressImage({ src:path, quality:82, compressedWidth:Math.round(info.width*scale), compressedHeight:Math.round(info.height*scale) })
    path = compressed.tempFilePath
  }
  return new Promise((resolve,reject) => uni.uploadFile({
    url:`${API_BASE_URL}/recommend/assets`, filePath:path, name:'file', header:{Authorization:`Bearer ${token()}`}, timeout:30000,
    success:r=>{try {const data=JSON.parse(r.data);if(r.statusCode===201) resolve(data);else reject(Object.assign(new Error(data.detail || '上传失败'),{statusCode:r.statusCode}))}catch(e){reject(e)}}, fail:reject,
  }))
}

export function downloadResult(url) {
  return new Promise((resolve,reject) => uni.downloadFile({
    url:`${API_BASE_URL}${url}`, header:{Authorization:`Bearer ${token()}`}, timeout:20000,
    success:r=>r.statusCode===200 ? resolve(r.tempFilePath) : reject(new Error(r.statusCode===401 ? '登录已过期，请重新登录' : '图片暂时无法下载')), fail:reject,
  }))
}
