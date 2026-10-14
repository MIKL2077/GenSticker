import { API_BASE_URL } from '@/constants'
import { visitorHeaders } from '@/services/popularityService'
import { prepareImage } from '@/services/imagePreparation'

// Discard only this editor's leftovers from a previous app session.
if(typeof uni!=='undefined' && uni.env?.USER_DATA_PATH && uni.getFileSystemManager) {
  const fs=uni.getFileSystemManager()
  fs.readdir?.({dirPath:uni.env.USER_DATA_PATH,success:r=>{for(const name of r.files||[])if(/^gensticker_edit_[\w.-]+\.png$/.test(name))fs.unlink({filePath:`${uni.env.USER_DATA_PATH}/${name}`,fail:()=>{}})},fail:()=>{}})
}

export function disposeEditedImage(path) {
  if (typeof path !== 'string') return
  if (path.startsWith('blob:')) { URL.revokeObjectURL(path); return }
  if (/\/gensticker_edit_[\w.-]+\.png$/.test(path)) uni.getFileSystemManager?.().unlink({ filePath:path, fail:()=>{} })
}

export function cropGeometry(width, height, frameWidth, frameHeight, zoom = 1, offsetX = 0, offsetY = 0) {
  const scale = Math.max(frameWidth / width, frameHeight / height) * Math.max(1, zoom)
  const drawnWidth = width * scale, drawnHeight = height * scale
  const dx = Math.max(-(drawnWidth-frameWidth)/2, Math.min((drawnWidth-frameWidth)/2, offsetX))
  const dy = Math.max(-(drawnHeight-frameHeight)/2, Math.min((drawnHeight-frameHeight)/2, offsetY))
  return { width:drawnWidth, height:drawnHeight, x:dx, y:dy,
    rect:[((drawnWidth-frameWidth)/2-dx)/scale/width, ((drawnHeight-frameHeight)/2-dy)/scale/height, frameWidth/scale/width, frameHeight/scale/height] }
}

async function exportCanvas(canvas) {
  if (typeof document !== 'undefined') {
    const blob = await new Promise(resolve=>canvas.toBlob(resolve, 'image/png'))
    if (!blob) throw new Error('图片导出失败，请重试')
    return URL.createObjectURL(blob)
  }
  // Copy a temporary Canvas output into an explicitly owned path for cleanup.
  const temporary = await new Promise((resolve,reject)=>wx.canvasToTempFilePath({ canvas, fileType:'png', success:r=>resolve(r.tempFilePath), fail:reject }))
  const fs = uni.getFileSystemManager(), path = `${uni.env.USER_DATA_PATH}/gensticker_edit_${Date.now()}_${Math.random().toString(36).slice(2)}.png`
  await new Promise((resolve,reject)=>fs.copyFile({srcPath:temporary,destPath:path,success:resolve,fail:reject}))
  fs.unlink({filePath:temporary,fail:()=>{}})
  return path
}

export async function editImage(path, operation) {
  path = await prepareImage(path)
  const info = await new Promise((resolve,reject)=>uni.getImageInfo({src:path,success:resolve,fail:reject}))
  if (/gif|webp/i.test(info.type || '')) throw new Error('请先选择一张静态 JPG 或 PNG 图片进行编辑')
  if (info.width*info.height > 4_000_000) throw new Error('图片过大，请先在相册缩小后编辑')
  let canvas, image
  try {
    canvas = typeof document !== 'undefined' ? document.createElement('canvas') : wx.createOffscreenCanvas?.({type:'2d',width:1,height:1})
    if (!canvas) throw new Error('当前设备暂不支持图片编辑，请升级微信')
    image = typeof document !== 'undefined' ? new Image() : canvas.createImage()
    await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('图片读取超时')),10000);image.onload=()=>{clearTimeout(timer);resolve()};image.onerror=()=>{clearTimeout(timer);reject(new Error('图片读取失败'))};image.src=path})
    const sourceWidth=image.width, sourceHeight=image.height
    let rect = operation.type==='crop' ? operation.rect : [0,0,1,1]
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
    if(blob.size>4*1024*1024)throw new Error('图片不能超过 4 MB，请先裁剪')
    encoded=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=reject;reader.readAsDataURL(blob)})
  } else {
    const fs=uni.getFileSystemManager()
    const info=await new Promise((resolve,reject)=>fs.stat({path,success:resolve,fail:reject}))
    if(info.stats.size>4*1024*1024)throw new Error('图片不能超过 4 MB，请先裁剪')
    encoded=await new Promise((resolve,reject)=>fs.readFile({filePath:path,encoding:'base64',success:r=>resolve(r.data),fail:reject}))
  }
  const response=await uni.request({url:`${API_BASE_URL}/images/subject`,method:'POST',data:{image:encoded},header:{'Content-Type':'application/json',...visitorHeaders()},responseType:'arraybuffer',timeout:60000})
  if(response.statusCode!==200) {
    let message=response.statusCode===429 ? '处理太频繁，请稍后再试' : response.statusCode===404 ? '图片处理暂未准备好，请稍后再试' : '背景处理失败，请稍后重试'
    try {const detail=JSON.parse(decodeURIComponent(Array.from(new Uint8Array(response.data).slice(0,8192),b=>'%'+b.toString(16).padStart(2,'0')).join(''))).detail;if(typeof detail==='string' && response.statusCode!==404)message=detail} catch(_) {}
    throw new Error(message)
  }
  if(typeof document!=='undefined')return URL.createObjectURL(new Blob([response.data],{type:'image/png'}))
  const result=`${uni.env.USER_DATA_PATH}/gensticker_edit_${Date.now()}_${Math.random().toString(36).slice(2)}.png`
  await new Promise((resolve,reject)=>uni.getFileSystemManager().writeFile({filePath:result,data:response.data,success:resolve,fail:reject}))
  return result
}
