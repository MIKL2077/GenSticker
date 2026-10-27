import {registerTemporary,releaseTemporary,withStorageRecovery} from '@/services/ownedFiles'

// Editing keeps the original PNG. Only the generation upload uses JPEG colour
// plus a lossless grey PNG alpha plane; flattening a cutout would lose its edges.
const MAX_EDGE=1024,MAX_BYTES=4*1024*1024
async function readImage(path,maxBytes=MAX_BYTES) {
  if(typeof document!=='undefined') {
    const blob=await(await fetch(path)).blob()
    if(blob.size>maxBytes)throw Error(`图片超过 ${maxBytes/1024/1024} MB，先裁剪一下吧`)
    return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=reject;reader.readAsDataURL(blob)})
  }
  const fs=uni.getFileSystemManager(),stat=await new Promise((resolve,reject)=>fs.stat({path,success:resolve,fail:reject}))
  if(stat.stats.size>maxBytes)throw Error(`图片超过 ${maxBytes/1024/1024} MB，先裁剪一下吧`)
  return new Promise((resolve,reject)=>fs.readFile({filePath:path,encoding:'base64',success:r=>resolve(r.data),fail:reject}))
}
async function exportImage(canvas,fileType) {
  if(typeof document!=='undefined') {
    const blob=await new Promise(resolve=>canvas.toBlob(resolve,fileType==='jpg'?'image/jpeg':'image/png',.85))
    if(!blob)throw Error('图片压缩未完成，请重试；原图已保留')
    return registerTemporary(URL.createObjectURL(blob))
  }
  return registerTemporary(await withStorageRecovery(()=>new Promise((resolve,reject)=>wx.canvasToTempFilePath({canvas,fileType,quality:.85,success:r=>resolve(r.tempFilePath),fail:reject}))))
}
export async function encodeGenerationImage(path) {
  const info=await new Promise((resolve,reject)=>uni.getImageInfo({src:path,success:resolve,fail:reject}))
  // Preserve animated photo inputs in the existing direct-render API.
  if(/^(gif|webp)$/i.test(info.type||''))return {image:await readImage(path,10*1024*1024),mask:''}
  if(info.width*info.height>40000000)throw Error('图片超过 4000 万像素，请先缩小')
  let canvas,image,colourPath,maskPath
  try {
    canvas=typeof document!=='undefined'?document.createElement('canvas'):wx.createOffscreenCanvas({type:'2d',width:1,height:1})
    image=typeof document!=='undefined'?new Image():canvas.createImage()
    await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('图片读取超时，请重新选择')),10000);image.onload=()=>{clearTimeout(timer);resolve()};image.onerror=()=>{clearTimeout(timer);reject(Error('图片读取失败，请重新选择'))};image.src=path})
    // Canvas decoding applies EXIF, so use its displayed dimensions.
    const scale=Math.min(1,MAX_EDGE/Math.max(image.width,image.height))
    canvas.width=Math.max(1,Math.round(image.width*scale));canvas.height=Math.max(1,Math.round(image.height*scale))
    const ctx=canvas.getContext('2d',{willReadFrequently:true})
    ctx.drawImage(image,0,0,canvas.width,canvas.height)
    const pixels=ctx.getImageData(0,0,canvas.width,canvas.height),alpha=new Uint8Array(canvas.width*canvas.height)
    let transparent=false
    for(let i=0;i<alpha.length;i++){alpha[i]=pixels.data[i*4+3];if(alpha[i]!==255)transparent=true;pixels.data[i*4+3]=255}
    ctx.putImageData(pixels,0,0)
    colourPath=await exportImage(canvas,'jpg')
    const encoded=await readImage(colourPath)
    if(!transparent)return {image:encoded,mask:''}
    for(let i=0;i<alpha.length;i++)pixels.data[i*4]=pixels.data[i*4+1]=pixels.data[i*4+2]=alpha[i]
    ctx.putImageData(pixels,0,0)
    maskPath=await exportImage(canvas,'png')
    return {image:encoded,mask:await readImage(maskPath)}
  } finally {
    if(colourPath)releaseTemporary(colourPath)
    if(maskPath)releaseTemporary(maskPath)
    if(canvas)canvas.width=canvas.height=1
    image=null
  }
}
export async function encodeGenerationImages(paths) {
  const images=[],masks=[]
  let bytes=0
  for(const path of paths){const encoded=await encodeGenerationImage(path);images.push(encoded.image);masks.push(encoded.mask);bytes+=encoded.image.length+encoded.mask.length;if(bytes>14*1024*1024)throw Error('图片总大小不能超过 10 MB，请减少图片')}
  return {images,...(masks.some(Boolean)?{image_masks:masks}:{})}
}
