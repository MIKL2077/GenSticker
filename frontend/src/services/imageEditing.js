import { API_BASE_URL } from '@/constants'
import { visitorHeaders } from '@/services/popularityService'
import { prepareImage } from '@/services/imagePreparation'

import {registerTemporary,releaseTemporary,trimOwnedFiles} from '@/services/ownedFiles'
export const disposeEditedImage=releaseTemporary

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

async function exportCanvas(canvas) {
  if (typeof document !== 'undefined') {
    const blob = await new Promise(resolve=>canvas.toBlob(resolve, 'image/png'))
    if (!blob) throw new Error('图片导出失败，请重试')
    return registerTemporary(URL.createObjectURL(blob))
  }
  const temporary=await new Promise((resolve,reject)=>wx.canvasToTempFilePath({canvas,fileType:'png',success:r=>resolve(r.tempFilePath),fail:reject}))
  return registerTemporary(temporary)
}

export async function editImage(path, operation) {
  path = await prepareImage(path)
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
    let rect = ['crop','window'].includes(operation.type) ? operation.rect : [0,0,1,1]
    if (!Array.isArray(rect) || rect.length!==4 || rect.some(n=>!Number.isFinite(n)) || rect[0]<0 || rect[1]<0 || rect[2]<=0 || rect[3]<=0 || rect[0]+rect[2]>1.00001 || rect[1]+rect[3]>1.00001) throw new Error('裁剪区域无效')
    const sw=sourceWidth*rect[2], sh=sourceHeight*rect[3], rotated=operation.type==='rotate'
    const scale=Math.min(1,1280/Math.max(sw,sh))
    const width=Math.max(1,Math.round(sw*scale)), height=Math.max(1,Math.round(sh*scale))
    canvas.width=rotated ? height : width;canvas.height=rotated ? width : height
    const ctx=canvas.getContext('2d')
    if (rotated) {ctx.translate(canvas.width,0);ctx.rotate(Math.PI/2)}
    if (operation.type==='flip') {ctx.translate(width,0);ctx.scale(-1,1)}
    ctx.drawImage(image,sourceWidth*rect[0],sourceHeight*rect[1],sw,sh,0,0,width,height)
    return await exportCanvas(canvas)
  } finally { if(canvas){canvas.width=1;canvas.height=1}image=null }
}

export async function removeImageBackground(path) {
  path=await prepareImage(path)
  let encoded
  if(typeof document !== 'undefined') {
    const blob=await (await fetch(path)).blob()
    if(blob.size>8*1024*1024)throw new Error('图片不能超过 8 MB，请先裁剪')
    encoded=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=reject;reader.readAsDataURL(blob)})
  } else {
    const fs=uni.getFileSystemManager()
    const info=await new Promise((resolve,reject)=>fs.stat({path,success:resolve,fail:reject}))
    if(info.stats.size>8*1024*1024)throw new Error('图片不能超过 8 MB，请先裁剪')
    encoded=await new Promise((resolve,reject)=>fs.readFile({filePath:path,encoding:'base64',success:r=>resolve(r.data),fail:reject}))
  }
  await trimOwnedFiles()
  const response=await uni.request({url:`${API_BASE_URL}/images/subject`,method:'POST',data:{image:encoded,delivery:'url'},header:{'Content-Type':'application/json',...visitorHeaders()},timeout:60000})
  if(response.statusCode!==200)throw Error(typeof response.data?.detail==='string'?response.data.detail:'抠图暂时繁忙，原图已保留，请稍后再试')
  if(!response.data?.image_url)throw Error('抠图结果暂时没送达，点一下再试')
  if(typeof document!=='undefined'){
    const result=await fetch(`${API_BASE_URL}${response.data.image_url}`,{headers:visitorHeaders()});if(!result.ok)throw Error('抠图结果已过期，请重试')
    return registerTemporary(URL.createObjectURL(await result.blob()))
  }
  const result=await new Promise((resolve,reject)=>uni.downloadFile({url:`${API_BASE_URL}${response.data.image_url}`,header:visitorHeaders(),timeout:30000,success:r=>r.statusCode===200?resolve(r.tempFilePath):reject(Error('抠图结果已过期，请重试')),fail:reject}))
  return registerTemporary(result)
}
