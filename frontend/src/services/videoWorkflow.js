import { API_BASE_URL } from '@/constants'
import { apiRequest } from '@/services/apiService'
import { uniqueKey, trackStudioJob } from '@/services/studioService'
import { albumMotion, localVideoInfo } from '@/services/liveGifService'

export const isNativeVideo = () => typeof document==='undefined' && typeof wx!=='undefined'
export const isCancelled = error => /cancel|取消/i.test(error?.errMsg||error?.message||'')
const call = (api,options) => new Promise((resolve,reject)=>api({...options,success:resolve,fail:reject}))
export async function chooseAlbumVideo(live=false) {
  let file
  if(isNativeVideo()&&wx.chooseMedia){
    // mix allows the system to return a Live clip as video when supported by that client.
    const data=await call(wx.chooseMedia.bind(wx),{count:1,mediaType:live?['mix']:['video'],sourceType:['album'],sizeType:['original']})
    file=data.tempFiles[0]
  }else if(live){const data=await call(uni.chooseImage,{count:1,sizeType:['original'],sourceType:['album']});file={tempFilePath:data.tempFilePaths[0],fileType:'image'}}
  else file=await call(uni.chooseVideo,{sourceType:['album'],compressed:false})
  let path=file.tempFilePath||file.path
  if(live&&file.fileType!=='video'&&!(file.duration>0))path=await albumMotion(path)
  return {...file,tempFilePath:path}
}
export async function nativeTrim(file) {
  if(!isNativeVideo()||!wx.openVideoEditor)return {file,trimmed:false}
  try{
    const result=await call(wx.openVideoEditor.bind(wx),{filePath:file.tempFilePath,minDuration:'.2',maxDuration:'9'})
    // This official API returns duration in milliseconds, unlike chooseMedia.
    let info
    try{info=await localVideoInfo(result.tempFilePath)}catch(_){info={width:file.width,height:file.height,duration:result.duration/1000}}
    return {file:{...file,...info,tempFilePath:result.tempFilePath,thumbTempFilePath:result.tempThumbPath,size:result.size,duration:result.duration/1000||info.duration},trimmed:true}
  }catch(error){if(isCancelled(error))throw error;return {file,trimmed:false}}
}
export async function mediaInfo(file) {
  if(file.duration>0&&file.width>0&&file.height>0)return file
  return {...file,...await localVideoInfo(file.tempFilePath)}
}
export function uploadLiveSource(path,token,onProgress=()=>{}) {
  let task
  const promise=new Promise((resolve,reject)=>{
    task=uni.uploadFile({url:API_BASE_URL+'/studio/live/assets',filePath:path,name:'file',header:{Authorization:'Bearer '+token},timeout:120000,
      success:r=>{try{const value=JSON.parse(r.data);if(r.statusCode===201)resolve(value);else reject(Object.assign(Error(typeof value.detail==='string'?value.detail:'视频上传没有完成，请重试'),{statusCode:r.statusCode}))}catch(e){reject(e)}},fail:reject})
    task?.onProgressUpdate?.(event=>onProgress(event.progress))
  })
  return {promise,abort:()=>task?.abort?.()}
}
// A mobile job is accepted into the durable queue before conversion starts. No
// native decoder or page lifetime is needed for the FFmpeg worker to finish it.
export async function submitVideoJob(asset,options,key=uniqueKey(),token) {
  const owner=uni.getStorageSync('gensticker.session.v1')?.profile?.id
  const job=await apiRequest('/studio/live/jobs',{method:'POST',header:token?{Authorization:'Bearer '+token}:{},timeout:30000,data:{asset_id:asset.asset_id,idempotency_key:key,...options}},1)
  return trackStudioJob(job,owner)
}

// A small, 10 fps intermediate lets the native decoder read sequentially. It
// also bounds fallback upload size on slow cellular links. Picker originals stay intact.
export async function prepareLocalSource(path,info,crop=[0,0,1,1]) {
  if(!isNativeVideo())return {path,sequential:false}
  if(!wx.compressVideo||info.duration>30)return {path,sequential:false,nativeUnavailable:true}
  const edge=Math.min(1280,Math.max(720,240/Math.min(crop[2],crop[3])))
  let timer
  const compression=call(wx.compressVideo.bind(wx),{src:path,bitrate:600,fps:10,resolution:Math.min(1,edge/Math.max(info.width,info.height))})
  try{
    const result=await Promise.race([compression,new Promise((_,reject)=>timer=setTimeout(()=>reject(Error('本地压缩没有响应')),30000))])
    return {path:result.tempFilePath,sequential:true}
  }catch(_){return {path,sequential:false,nativeUnavailable:true}}
  finally{clearTimeout(timer)}
}
