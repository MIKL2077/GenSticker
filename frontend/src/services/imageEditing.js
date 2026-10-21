import {requestError} from '@/services/networkErrors'
import { API_BASE_URL } from '@/constants'
import { visitorHeaders } from '@/services/popularityService'
import { prepareImage } from '@/services/imagePreparation'
import { prepareForeground, applyForegroundMask } from '@/services/localBackground'

import {registerTemporary,releaseTemporary,writeOwnedFile} from '@/services/ownedFiles'
export const disposeEditedImage=releaseTemporary

// Native callbacks reject plain {errMsg} objects, rather than Error instances.
export function imageEditError(error) {
  const raw=String(error?.errMsg || error?.message || '')
  if(/request:fail|uploadFile:fail|downloadFile:fail|timeout|timed out|ssl|domain|dns/i.test(raw))return requestError(error)
  if(/canvasToTempFilePath|createOffscreenCanvas/i.test(raw))return Error('当前微信未能导出图片，请重新打开小程序或升级微信；原图已保留')
  if(/getImageInfo|readFile|stat:fail/i.test(raw))return Error('图片读取失败，请重新选择照片；原图已保留')
  return error?.message ? error : Error('图片处理未完成，请重试；原图已保留')
}
function responseDetail(data) {
  try {
    if(data instanceof ArrayBuffer){
      const bytes=new Uint8Array(data,0,Math.min(data.byteLength,8192))
      data=JSON.parse(decodeURIComponent(Array.from(bytes,byte=>'%'+byte.toString(16).padStart(2,'0')).join('')))
    }else if(typeof data==='string')data=JSON.parse(data)
    return typeof data?.detail==='string' ? data.detail : ''
  }catch(_){return ''}
}

export function cropGeometry(width, height, frameWidth, frameHeight, zoom = 1, offsetX = 0, offsetY = 0) {
  const scale = Math.max(frameWidth / width, frameHeight / height) * Math.max(1, zoom)
  const drawnWidth = width * scale, drawnHeight = height * scale
  const extraWidth=Math.max(0,drawnWidth-frameWidth),extraHeight=Math.max(0,drawnHeight-frameHeight)
  const dx = Math.max(-extraWidth/2, Math.min(extraWidth/2, offsetX))
  const dy = Math.max(-extraHeight/2, Math.min(extraHeight/2, offsetY))
  const rw=Math.min(1,frameWidth/scale/width),rh=Math.min(1,frameHeight/scale/height)
  return { width:drawnWidth, height:drawnHeight, x:dx, y:dy,
    rect:[Math.max(0,Math.min(1-rw,(extraWidth/2-dx)/scale/width)),Math.max(0,Math.min(1-rh,(extraHeight/2-dy)/scale/height)),rw,rh] }

}

async function exportCanvas(canvas, fileType='png') {
  if (typeof document !== 'undefined') {
    const blob = await new Promise(resolve=>canvas.toBlob(resolve, fileType==='jpg'?'image/jpeg':'image/png',.88))
    if (!blob) throw new Error('图片导出失败，请重试')
    return registerTemporary(URL.createObjectURL(blob))
  }
  const temporary=await new Promise((resolve,reject)=>wx.canvasToTempFilePath({canvas,fileType,quality:.88,success:r=>resolve(r.tempFilePath),fail:reject}))
  return registerTemporary(temporary)
}

export async function editImage(path, operation) {
  if(!operation.skipPrepare)path = await prepareImage(path)
  const info = await new Promise((resolve,reject)=>uni.getImageInfo({src:path,success:resolve,fail:reject}))
  // Browser/native image decoding supplies a static frame for animated inputs.
  if (info.width*info.height > 40_000_000) throw new Error('图片超过 4000 万像素，请先缩小后编辑')
  let canvas, image
  try {
    canvas = typeof document !== 'undefined' ? document.createElement('canvas') : wx.createOffscreenCanvas?.({type:'2d',width:1,height:1})
    if (!canvas) throw new Error('当前设备暂不支持图片编辑，请升级微信')
    image = typeof document !== 'undefined' ? new Image() : canvas.createImage()
    await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('图片读取超时')),10000);image.onload=()=>{clearTimeout(timer);resolve()};image.onerror=()=>{clearTimeout(timer);reject(new Error('图片读取失败'))};image.src=path})
    const sourceWidth=image.width, sourceHeight=image.height
    let rect = operation.rect || [0,0,1,1]
    if (!Array.isArray(rect) || rect.length!==4 || rect.some(n=>!Number.isFinite(n)) || rect[0]<0 || rect[1]<0 || rect[2]<=0 || rect[3]<=0 || rect[0]+rect[2]>1.00001 || rect[1]+rect[3]>1.00001) throw new Error('裁剪区域无效')
    const sw=sourceWidth*rect[2], sh=sourceHeight*rect[3], rotated=operation.type==='rotate'
    const scale=Math.min(1,Math.max(64,Math.min(1280,operation.maxEdge||1280))/Math.max(sw,sh))
    const width=Math.max(1,Math.round(sw*scale)), height=Math.max(1,Math.round(sh*scale))
    canvas.width=rotated ? height : width;canvas.height=rotated ? width : height
    const ctx=canvas.getContext('2d')
    if (rotated) {ctx.translate(canvas.width,0);ctx.rotate(Math.PI/2)}
    if (operation.type==='flip') {ctx.translate(width,0);ctx.scale(-1,1)}
    ctx.drawImage(image,sourceWidth*rect[0],sourceHeight*rect[1],sw,sh,0,0,width,height)
    return await exportCanvas(canvas,operation.fileType||'png')
  } finally { if(canvas){canvas.width=1;canvas.height=1}image=null }
}

// Both detection previews and explicit cutout responses use this bounded
// mask format. Original photo pixels stay on the device during composition.
export async function composeBackgroundMask(original,data,{rect}={}) {
  const native=typeof document==='undefined',mask=data.mask
  if(data.width!==320 || data.height!==320 || typeof mask!=='string' || mask.length>600000 || !/^[A-Za-z0-9+/]+={0,2}$/.test(mask))throw Error('去背景结果无效，请重试')
  let maskPath
  try{
    maskPath=native?registerTemporary(uni.env.USER_DATA_PATH+'/gensticker_edit_mask_'+Date.now()+'_'+Math.random().toString(36).slice(2)+'.png'):'data:image/png;base64,'+mask
    if(native)await writeOwnedFile(maskPath,mask,'base64')
    return await applyForegroundMask(original,maskPath,exportCanvas,{rect})
  }finally{if(native && maskPath)disposeEditedImage(maskPath)}
}

export async function removeImageBackground(path,{onProgress,rect,localOnly=false}={}) {
  const owner=uni.getStorageSync('gensticker.session.v1')?.profile?.id || '',headers=visitorHeaders()
  const current=()=>owner===(uni.getStorageSync('gensticker.session.v1')?.profile?.id || '')
  const original=path
  if(!current())throw Error('账号已切换，请重新选择图片')
  const prepared=await prepareForeground(original,exportCanvas,{rect,localOnly})
  if(prepared.path){if(!current()){disposeEditedImage(prepared.path);throw Error('账号已切换，请重新选择图片')}return prepared.path}
  if(localOnly)return null
  path=prepared.upload || original
  try {
    const native=typeof document==='undefined'
    let encoded
    if(!native) {
      const blob=await (await fetch(path)).blob()
      if(blob.size>8*1024*1024)throw new Error('图片不能超过 8 MB，请先裁剪')
      encoded=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=reject;reader.readAsDataURL(blob)})
    }
    if(!current())throw Error('账号已切换，请重新选择图片')
    // DownloadFile handles image delivery more reliably than large ArrayBuffer
    // request responses in the WeChat runtime. Tickets are visitor/account bound.
    const response=native?await uploadSubjectPreview(path,headers,current):await uni.request({url:`${API_BASE_URL}/images/subject`,method:'POST',data:{image:encoded,delivery:'mask'},header:{'Content-Type':'application/json',...headers},timeout:20000})
    if(!current())throw Error('账号已切换，请重新选择图片')
    if(response.statusCode!==200){
      const detail=responseDetail(response.data)
      if(detail)throw Error(detail)
      if(response.statusCode===403)throw requestError({statusCode:403})
      throw Error(response.statusCode===503?'抠图暂时繁忙，原图已保留，请稍后再试':'抠图服务暂不可用（'+response.statusCode+'），原图已保留，请重试')
    }
    if(response.data?.mask){
      const result=await composeBackgroundMask(original,response.data,{rect})
      if(!current()){disposeEditedImage(result);throw Error('账号已切换，请重新选择图片')}
      return result
    }
    if(native){
      const resultUrl=response.data?.image_url
      if(!/^\/images\/subject-results\/[a-f0-9]{40}$/.test(resultUrl||''))throw Error('抠图结果地址无效，请重试')
      const downloaded=await downloadSubjectPreview(resultUrl,headers,onProgress)
      try{
        if(!current())throw Error('账号已切换，请重新选择图片')
        const png=await editImage(downloaded,{type:'crop',rect:[0,0,1,1],fileType:'png'})
        if(!current()){disposeEditedImage(png);throw Error('账号已切换，请重新选择图片')}
        return png
      }finally{disposeEditedImage(downloaded)}
    }
    if(!(response.data instanceof ArrayBuffer) || !response.data.byteLength)throw Error('抠图结果暂时没送达，请重试')
    return registerTemporary(URL.createObjectURL(new Blob([response.data],{type:'image/png'})))
  } catch(error){throw imageEditError(error)} finally {if(path!==original)disposeEditedImage(path)}
}


function downloadSubjectPreview(path,headers,onProgress) {
 return new Promise((resolve,reject)=>{
  let task,done=false
  const timer=setTimeout(()=>{if(done)return;done=true;try{task?.abort()}catch(_){}reject(imageEditError({errMsg:'downloadFile:fail timeout'}))},45000)
  task=uni.downloadFile({url:API_BASE_URL+path,header:headers,timeout:45000,
   success:result=>{
    if(done){if(result.tempFilePath)disposeEditedImage(registerTemporary(result.tempFilePath));return}
    done=true;clearTimeout(timer)
    if(result.statusCode===200 && result.tempFilePath)resolve(registerTemporary(result.tempFilePath))
    else{if(result.tempFilePath)disposeEditedImage(registerTemporary(result.tempFilePath));reject(Error(result.statusCode===404?'处理结果已过期，请重新去背景':'抠图结果下载失败，请重试'))}
   },fail:error=>{if(done)return;done=true;clearTimeout(timer);reject(imageEditError(error))}})
  task?.onProgressUpdate?.(result=>{if(!done && Number.isFinite(result.progress)){try{onProgress?.(Math.max(0,Math.min(100,result.progress)))}catch(_){}}})
 })
}

async function uploadSubjectPreview(path,headers,current=()=>true) {
 const stat=await new Promise((resolve,reject)=>uni.getFileSystemManager().stat({path,success:resolve,fail:reject}))
 if(stat.stats.size>8*1024*1024)throw Error('图片不能超过 8 MB，请先裁剪')
 if(!current())throw Error('账号已切换，请重新选择图片')
 return new Promise((resolve,reject)=>uni.uploadFile({url:API_BASE_URL+'/images/subject-file',filePath:path,name:'file',formData:{delivery:'mask'},header:headers,timeout:20000,
  success:result=>{try{resolve({...result,data:JSON.parse(result.data)})}catch(_){if(result.statusCode!==200)resolve({...result,data:{}});else reject(Error('抠图服务返回异常，请重试'))}},fail:error=>reject(imageEditError(error))}))
}
