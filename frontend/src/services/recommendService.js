import {withStorageRecovery,registerTemporary,releaseTemporary} from '@/services/ownedFiles'
import {displayImageSize} from '@/services/imageGeometry'
import { apiRequest } from '@/services/apiService'
import { API_BASE_URL } from '@/constants'
import {openCollageGif} from '@/services/collageGif'
import {exportGif} from '@/services/resultCollage'

const token = () => uni.getStorageSync('gensticker.session.v1')?.access_token
export const getQuota = () => apiRequest('/recommend/quota', {}, 1)
export const listJobs = () => apiRequest('/recommend/jobs', {}, 1)
export const getJob = id => apiRequest(`/recommend/jobs/${id}`, {}, 1)
export const createJob = (asset_id, idempotency_key, previous_job_id) => apiRequest('/recommend/jobs', { method:'POST', data:{asset_id,idempotency_key,previous_job_id} }, 1)
export const selectResults = (id, slots, action = 'choose') => apiRequest(`/recommend/jobs/${id}/selections`, { method:'POST', data:{event_id:`${Date.now()}-${Math.random().toString(36).slice(2)}`, slots, action} }, 1)
export const removeJob = id => apiRequest(`/recommend/jobs/${id}`, { method:'DELETE' }, 1)
export const setPersonalization = enabled => apiRequest('/recommend/preferences', { method:'PUT', data:{enabled} }, 1)

export async function uploadPhoto(path,subjectSelected=false) {
  const session=uni.getStorageSync('gensticker.session.v1'),owner=session?.profile?.id,uploadToken=session?.access_token
  const original=path
  try {
  const info = await uni.getImageInfo({ src:path })
  if (info.type === 'jpeg' || info.type === 'jpg') {
    const scale = Math.min(1,1280 / Math.max(info.width,info.height))
    const compressed = await withStorageRecovery(()=>uni.compressImage({ src:path, quality:82, compressedWidth:Math.round(displayImageSize(info).width*scale), compressedHeight:Math.round(displayImageSize(info).height*scale) }))
    path = compressed.tempFilePath
    if(path!==original)registerTemporary(path)
  }
  if(owner!==uni.getStorageSync('gensticker.session.v1')?.profile?.id)throw Error('账号已切换，请重新选图')
  return await new Promise((resolve,reject) => uni.uploadFile({
    url:`${API_BASE_URL}/recommend/assets`, filePath:path, name:'file', formData:{subject_selected:String(subjectSelected)}, header:{Authorization:`Bearer ${uploadToken}`}, timeout:30000,
    success:r=>{try {const data=JSON.parse(r.data);if(r.statusCode===201) resolve(data);else reject(Object.assign(new Error(data.detail || '上传失败'),{statusCode:r.statusCode}))}catch(e){reject(e)}}, fail:reject,
  }))
  }finally{if(path!==original)releaseTemporary(path)}
}

export function downloadResult(url,timeout=20000) {
  return withStorageRecovery(()=>new Promise((resolve,reject) => uni.downloadFile({
    url:`${API_BASE_URL}${url}`, header:{Authorization:`Bearer ${token()}`}, timeout,
    success:r=>{if(r.tempFilePath)registerTemporary(r.tempFilePath);if(r.statusCode===200)resolve(r.tempFilePath);else{if(r.tempFilePath)releaseTemporary(r.tempFilePath);reject(new Error(r.statusCode===401 ? '登录已过期，请重新登录' : '图片暂时无法下载'))}}, fail:reject,
  })))
}

export async function createRecommendationCollage(id,slots,cancelled=()=>false) {
  const session=uni.getStorageSync('gensticker.session.v1'),owner=session?.profile?.id
  const check=()=>{if(cancelled()||owner!==uni.getStorageSync('gensticker.session.v1')?.profile?.id)throw Error('拼图制作已取消')}
  check()
  const response=await new Promise((resolve,reject)=>{
    let timer,task,settled=false
    const finish=(error,result)=>{if(settled)return;settled=true;clearTimeout(timer);error?reject(error):resolve(result)}
    const watch=()=>{try{check();timer=setTimeout(watch,200)}catch(error){finish(error);task?.abort?.()}}
    task=uni.request({url:`${API_BASE_URL}/recommend/jobs/${encodeURIComponent(id)}/collage`,method:'POST',
      data:{slots},responseType:'arraybuffer',timeout:60000,header:{Authorization:`Bearer ${session?.access_token}`},
      success:r=>finish(null,r),fail:error=>finish(error)})
    if(!settled)watch()
  })
  check()
  if(response.statusCode!==200){const error=Error(response.statusCode===401?'登录已过期，请重新登录':'服务端拼图暂未完成');error.statusCode=response.statusCode;throw error}
  const bytes=new Uint8Array(response.data)
  if(bytes.length>2*1024*1024)throw Error('动态拼图返回体积超限')
  const gif=openCollageGif(bytes),meta={animated:gif.animated,width:gif.width,height:gif.height,duration:gif.duration,bytes:bytes.length}
  gif.close();check()
  const path=await exportGif(bytes)
  try{check();return {...meta,path}}
  catch(error){releaseTemporary(path);throw error}
}
