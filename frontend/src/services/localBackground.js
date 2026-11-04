import {yieldToUI} from '@/services/uiYield'

// Native inference session creation can compile synchronously and freeze the
// entire mini program, including GIFs. Keep segmentation on the prewarmed
// server; this module only composes bounded images and already supplied masks.
const EDGE=320
function deadline(task,ms){let timer;return Promise.race([task,new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('图片处理超时')),ms)})]).finally(()=>clearTimeout(timer))}
const call=(fn,options)=>new Promise((resolve,reject)=>fn({...options,success:resolve,fail:reject}))
function newCanvas(width,height){const canvas=typeof document!=='undefined'?document.createElement('canvas'):wx.createOffscreenCanvas?.({type:'2d',width,height});if(!canvas)throw Error('当前设备使用云端处理');canvas.width=width;canvas.height=height;return canvas}
async function drawSource(path,rect=[0,0,1,1]){
 const info=await call(uni.getImageInfo.bind(uni),{src:path})
 if(info.width*info.height>40000000)throw Error('图片过大，请先缩小')
 const scale=Math.min(1,1280/Math.max(info.width,info.height)),canvas=newCanvas(Math.max(1,Math.round(info.width*scale)),Math.max(1,Math.round(info.height*scale)))
 try{
  const image=typeof document!=='undefined'?new Image():canvas.createImage()
  await deadline(new Promise((resolve,reject)=>{image.onload=resolve;image.onerror=reject;image.src=path}),5000)
  // The decoded image is upright, unlike getImageInfo's EXIF sensor dimensions.
  if(!Array.isArray(rect)||rect.length!==4||rect.some(v=>!Number.isFinite(v))||rect[0]<0||rect[1]<0||rect[2]<=0||rect[3]<=0||rect[0]+rect[2]>1.00001||rect[1]+rect[3]>1.00001)throw Error('裁剪区域无效')
  const sw=image.width*rect[2],sh=image.height*rect[3],decodedScale=Math.min(1,1280/Math.max(sw,sh))
  canvas.width=Math.max(1,Math.round(sw*decodedScale));canvas.height=Math.max(1,Math.round(sh*decodedScale))
  canvas.getContext('2d').drawImage(image,image.width*rect[0],image.height*rect[1],sw,sh,0,0,canvas.width,canvas.height);return canvas
 }catch(error){canvas.width=canvas.height=1;throw error}
}
async function trimmedExport(canvas,exportCanvas){
 const ctx=canvas.getContext('2d'),pixels=ctx.getImageData(0,0,canvas.width,canvas.height).data
 let left=canvas.width,top=canvas.height,right=-1,bottom=-1
 for(let y=0;y<canvas.height;y++){
  for(let x=0;x<canvas.width;x++)if(pixels[(y*canvas.width+x)*4+3]>0){left=Math.min(left,x);right=Math.max(right,x);top=Math.min(top,y);bottom=Math.max(bottom,y)}
  if(y%32===31)await yieldToUI()
 }
 if(right<left)throw Error('图片主体为空，原图已保留')
 if(left===0 && top===0 && right===canvas.width-1 && bottom===canvas.height-1)return exportCanvas(canvas,'png')
 const cropped=newCanvas(right-left+1,bottom-top+1)
 try{cropped.getContext('2d').drawImage(canvas,left,top,cropped.width,cropped.height,0,0,cropped.width,cropped.height);return await exportCanvas(cropped,'png')}finally{cropped.width=cropped.height=1}
}
export async function applyForegroundMask(path,maskPath,exportCanvas,{rect}={}){
 let canvas
 try{
  canvas=await drawSource(path,rect)
  const ctx=canvas.getContext('2d'),pixels=ctx.getImageData(0,0,canvas.width,canvas.height).data
  let clear=0
  for(let i=3;i<pixels.length;i+=4){if(pixels[i]<240)clear++;if(i%131072===131071)await yieldToUI()}
  if(clear/(pixels.length/4)>=.02)return await trimmedExport(canvas,exportCanvas)
  const mask=typeof document!=='undefined'?new Image():canvas.createImage()
  await deadline(new Promise((resolve,reject)=>{mask.onload=resolve;mask.onerror=reject;mask.src=maskPath}),3000)
  if(mask.width!==EDGE || mask.height!==EDGE)throw Error('去背景结果尺寸无效')
  ctx.globalCompositeOperation='destination-in';ctx.drawImage(mask,0,0,canvas.width,canvas.height);ctx.globalCompositeOperation='source-over'
  return await trimmedExport(canvas,exportCanvas)
 }finally{if(canvas)canvas.width=canvas.height=1}
}

export async function prepareForeground(path,exportCanvas,{rect,localOnly=false}={}){
 let canvas,inputCanvas,hasTransparency=false
 try{
  // Speculative work must never decode a photo, load a model or upload it.
  if(localOnly)return {method:'unavailable'}
  canvas=await drawSource(path,rect)
  const ctx=canvas.getContext('2d'),pixels=ctx.getImageData(0,0,canvas.width,canvas.height).data
  let clear=0,visible=0
  for(let i=3;i<pixels.length;i+=4){if(pixels[i]<240)clear++;if(pixels[i]>20)visible++;if(pixels[i]<255)hasTransparency=true;if(i%131072===131071)await yieldToUI()}
  if(!visible)throw Error('图片主体为空，原图已保留')
  if(clear/(pixels.length/4)>=.02)return {path:await trimmedExport(canvas,exportCanvas),method:'alpha'}
  // The server model only needs a 320px tensor. A 640px upload preserves the
  // crop ratio; the returned mask is composited onto the original locally.
  if(inputCanvas)inputCanvas.width=inputCanvas.height=1
  inputCanvas=newCanvas(Math.max(1,Math.round(canvas.width*Math.min(1,640/Math.max(canvas.width,canvas.height)))),Math.max(1,Math.round(canvas.height*Math.min(1,640/Math.max(canvas.width,canvas.height)))))
  inputCanvas.getContext('2d').drawImage(canvas,0,0,inputCanvas.width,inputCanvas.height)
  return {upload:await exportCanvas(inputCanvas,hasTransparency?'png':'jpg'),method:'server'}
 }catch(error){if(/主体为空|裁剪区域/.test(error.message||''))throw error;if(localOnly)return {method:'unavailable'};throw error}
 finally{for(const item of [canvas,inputCanvas])if(item)item.width=item.height=1}
}
