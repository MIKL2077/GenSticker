import {paintCaption} from '@/services/captionLayout'
import { GIFEncoder, quantize, applyPalette } from 'gifenc'
import { writeOwnedFile, registerTemporary, releaseTemporary } from '@/services/ownedFiles'

export const MAX_CLIP_SECONDS = 9
export const MAX_GIF_BYTES = 500 * 1024
const pause = ms => new Promise(resolve => setTimeout(resolve, ms))
export const clipWindow = (total, start, duration) => {
  const length = Math.min(MAX_CLIP_SECONDS, Math.max(.2, Number(duration) || 3), total)
  return { start: Math.max(0, Math.min(Number(start) || 0, total - length)), duration: length }
}
export function clampCrop(rect) {
  const w = Math.max(.05, Math.min(1, Number(rect[2]) || 1)), h = Math.max(.05, Math.min(1, Number(rect[3]) || 1))
  return [Math.max(0, Math.min(1-w, Number(rect[0]) || 0)), Math.max(0, Math.min(1-h, Number(rect[1]) || 0)), w, h]
}
export function cropPixels(width, height, rect, edge = 240) {
  const [x,y,w,h] = clampCrop(rect), sw = width*w, sh = height*h, scale = Math.min(1, edge/Math.max(sw,sh))
  return {sx:width*x, sy:height*y, sw, sh, width:Math.max(2,Math.round(sw*scale)), height:Math.max(2,Math.round(sh*scale))}
}
export const supportsLocalGif = () => typeof document !== 'undefined' || (typeof wx !== 'undefined' && !!wx.createVideoDecoder && !!wx.createOffscreenCanvas)
function canvas(width,height) {
  const result = typeof document !== 'undefined' ? document.createElement('canvas') : wx.createOffscreenCanvas({type:'2d',width,height})
  result.width=width;result.height=height;return result
}
function checkCancelled(cancelled) { if(cancelled?.()) throw Error('制作已取消') }
function deadline(promise, ms=12000) {
  let timer
  return Promise.race([promise,new Promise((_,reject)=>timer=setTimeout(()=>reject(Error('本地读取暂时没有响应，将自动切换后台制作')),ms))]).finally(()=>clearTimeout(timer))
}
export function decoderEvent(decoder,name,action) {
  if(!decoder.on)return deadline(Promise.resolve().then(action))
  return new Promise((resolve,reject)=>{
    let settled=false
    const finish=(error)=>{if(settled)return;settled=true;clearTimeout(timer);decoder.off?.(name,ready);error?reject(error):resolve()}
    const ready=()=>finish(),timer=setTimeout(()=>finish(Error('本地解码没有响应')),5000)
    decoder.on(name,ready)
    try{const pending=action();pending?.then?.(()=>finish(),finish)}catch(error){finish(error)}
  })
}
// The browser seeks the selected window; WeChat uses its native local decoder.
// No video upload is needed on this path. Keep only downscaled output frames in memory.
async function frameReader(path, sequential=false, cancelled) {
  if(typeof document !== 'undefined') {
    const video=document.createElement('video');video.muted=true;video.playsInline=true;video.preload='auto';video.src=path
    try { await deadline(new Promise((resolve,reject)=>{video.onloadeddata=resolve;video.onerror=()=>reject(Error('这个视频暂时不能解码'))})) } catch(e){video.removeAttribute('src');video.load();throw e}
    return {async at(seconds){if(Math.abs(video.currentTime-seconds)>.015)await deadline(new Promise((resolve,reject)=>{video.onseeked=resolve;video.onerror=()=>reject(Error('视频定位失败'));video.currentTime=seconds}));return {image:video,width:video.videoWidth,height:video.videoHeight}},async close(){video.pause();video.removeAttribute('src');video.load()}}
  }
  const decoder=wx.createVideoDecoder(),rawCanvas=canvas(1,1)
  try { await decoderEvent(decoder,'start',()=>decoder.start({source:path,mode:1,abortAudio:true})) } catch(e){await deadline(Promise.resolve().then(()=>decoder.remove()),1000).catch(()=>{});throw e}
  let started=false,ended=false,lastFrame
  decoder.on?.('ended',()=>{ended=true})
  return {async at(seconds){
    checkCancelled(cancelled)
    if(!sequential||!started){if(seconds>0)await decoderEvent(decoder,'seek',()=>decoder.seek(Math.round(seconds*1000)));started=true}
    const end=Date.now()+3000;let frame
    while(!(frame=decoder.getFrameData())){checkCancelled(cancelled);if(ended&&lastFrame)return lastFrame;if(Date.now()>end)throw Error('本地解码暂时不可用');await pause(10)}
    if(frame.width*frame.height>12_000_000)throw Error('这段视频分辨率过高，请从相册导出 1080p 版本')
    rawCanvas.width=frame.width;rawCanvas.height=frame.height
    const ctx=rawCanvas.getContext('2d'),image=ctx.createImageData(frame.width,frame.height)
    image.data.set(new Uint8Array(frame.data));ctx.putImageData(image,0,0)
    lastFrame={image:rawCanvas,width:frame.width,height:frame.height};return lastFrame
  },async close(){rawCanvas.width=1;rawCanvas.height=1;try{await deadline(Promise.resolve().then(()=>decoder.stop()),1000).catch(()=>{})}finally{await deadline(Promise.resolve().then(()=>decoder.remove()),1000).catch(()=>{})}}}
}
export function drawFrame(ctx, image, width, height, options, edge=240) {
  const rotation=options.rotation||0, rotated=rotation%180!==0, rw=rotated?height:width, rh=rotated?width:height
  const geo=cropPixels(rw,rh,options.crop||[0,0,1,1],edge)
  ctx.canvas.width=geo.width;ctx.canvas.height=geo.height
  ctx.save();ctx.scale(geo.width/geo.sw,geo.height/geo.sh);ctx.translate(-geo.sx,-geo.sy)
  if(options.flip){ctx.translate(rw,0);ctx.scale(-1,1)}
  if(rotation===90){ctx.translate(height,0);ctx.rotate(Math.PI/2)}
  if(rotation===180){ctx.translate(width,height);ctx.rotate(Math.PI)}
  if(rotation===270){ctx.translate(0,width);ctx.rotate(-Math.PI/2)}
  ctx.drawImage(image,0,0,width,height);ctx.restore()
  if(options.text)paintCaption(ctx,options.text,geo.width,geo.height,options.caption_style)
  return geo
}
export function resizeRgba(input,width,height,outWidth,outHeight) {
  const output=new Uint8ClampedArray(outWidth*outHeight*4)
  for(let y=0;y<outHeight;y++)for(let x=0;x<outWidth;x++){
    const source=(Math.min(height-1,Math.floor(y*height/outHeight))*width+Math.min(width-1,Math.floor(x*width/outWidth)))*4
    output.set(input.subarray(source,source+4),(y*outWidth+x)*4)
  }
  return output
}
export async function encodeGifFrames(frames,width,height,onProgress=()=>{},cancelled) {
  // Start at 128 colors. Reduce fps, then palette, preserving the selected duration.
  for(const [stride,colors,edge] of [[1,128,240],[2,128,240],[2,64,180],[2,64,120],[3,32,96],[3,16,32]]) {
    const scale=Math.min(1,edge/Math.max(width,height)),outWidth=Math.max(2,Math.round(width*scale)),outHeight=Math.max(2,Math.round(height*scale))
    const encoder=GIFEncoder()
    for(let i=0;i<frames.length;i+=stride){
      checkCancelled(cancelled)
      const original=frames[i],rgba=outWidth===width&&outHeight===height?original:resizeRgba(original,width,height,outWidth,outHeight),palette=quantize(rgba,colors),indices=applyPalette(rgba,palette)
      encoder.writeFrame(indices,outWidth,outHeight,{palette,delay:Math.min(stride,frames.length-i)*100,repeat:0,dispose:1})
      onProgress(Math.round(65+30*Math.min(1,(i+stride)/frames.length)))
      if(i%4===0)await pause(0)
    }
    encoder.finish();const bytes=encoder.bytes()
    if(bytes.length<=MAX_GIF_BYTES)return {bytes,fps:10/stride,colors,width:outWidth,height:outHeight}
  }
  throw Error('本地编码未完成，将继续使用后台生成')
}
export async function renderLocalGif(path, options, onProgress=()=>{}, cancelled) {
  if(!supportsLocalGif())throw Error('当前设备需要后台制作')
  const expires=Date.now()+25000,isCancelled=()=>cancelled?.()||Date.now()>expires
  const reader=await frameReader(path,!!options.sequential,isCancelled),output=canvas(1,1),frames=[]
  try {
    const count=Math.max(2,Math.ceil(options.duration*10));let width,height
    for(let i=0;i<count;i++) {
      checkCancelled(cancelled)
      checkCancelled(isCancelled)
      const frame=await reader.at(options.start+i*options.duration/count)
      const geo=drawFrame(output.getContext('2d'),frame.image,frame.width,frame.height,options)
      width=geo.width;height=geo.height;frames.push(output.getContext('2d').getImageData(0,0,width,height).data)
      onProgress(Math.round(65*(i+1)/count));await pause(0)
    }
    const result=await encodeGifFrames(frames,width,height,onProgress,isCancelled)
    checkCancelled(cancelled)
    let resultPath
    if(typeof document !== 'undefined')resultPath=registerTemporary(URL.createObjectURL(new Blob([result.bytes],{type:'image/gif'})))
    else{resultPath=`${uni.env.USER_DATA_PATH}/generated_meme_live_${Date.now()}.gif`;await writeOwnedFile(resultPath,result.bytes.buffer.slice(result.bytes.byteOffset,result.bytes.byteOffset+result.bytes.byteLength))}
    onProgress(100);return {...result,path:resultPath}
  } finally {frames.length=0;output.width=1;output.height=1;await reader.close().catch(()=>{})}
}
// Read an original album image only to find an embedded motion stream. A static
// iPhone preview cannot reconstruct the paired MOV; never fabricate animation.
export async function albumMotion(path) {
  let bytes
  if(typeof document !== 'undefined')bytes=new Uint8Array(await(await fetch(path)).arrayBuffer())
  else {
    const fs=uni.getFileSystemManager(),stat=await new Promise((resolve,reject)=>fs.stat({path,success:r=>resolve(r.stats),fail:reject}))
    if(stat.size>30*1024*1024)throw Error('Live 原图最多 30 MB，请选择较小的动态原图或视频')
    bytes=new Uint8Array(await new Promise((resolve,reject)=>fs.readFile({filePath:path,success:r=>resolve(r.data),fail:reject})))
  }
  if(bytes.length>30*1024*1024)throw Error('Live 原图最多 30 MB，请选择较小的动态原图或视频')
  for(let i=4;i<bytes.length-8;i++)if(bytes[i]===102 && bytes[i+1]===116 && bytes[i+2]===121 && bytes[i+3]===112){
    const brand=String.fromCharCode(...bytes.slice(i+4,i+8)),size=new DataView(bytes.buffer,bytes.byteOffset+i-4,4).getUint32(0)
    if(['heic','heix','hevc','hevx','mif1','avif'].includes(brand)||size<8||size>256)continue
    const motion=bytes.slice(i-4)
    if(typeof document!=='undefined')return registerTemporary(URL.createObjectURL(new Blob([motion],{type:'video/mp4'})))
    const destination=`${uni.env.USER_DATA_PATH}/gensticker_edit_motion_${Date.now()}.mp4`
    await writeOwnedFile(destination,motion.buffer);return registerTemporary(destination)
  }
  throw Error('微信本次只提供了静态照片，未提供配对视频，暂时无法还原动态。可改选带视频片段的动态原图或相册视频。')
}
export const disposeLocalMedia=releaseTemporary

export async function localVideoInfo(path) {
  if(typeof document === 'undefined')return new Promise((resolve,reject)=>uni.getVideoInfo({src:path,success:resolve,fail:reject}))
  const video=document.createElement('video');video.preload='metadata';video.src=path
  try{await deadline(new Promise((resolve,reject)=>{video.onloadedmetadata=resolve;video.onerror=()=>reject(Error('这个视频格式暂时无法播放'))}));return {duration:video.duration,width:video.videoWidth,height:video.videoHeight}}
  finally{video.removeAttribute('src');video.load()}
}

export async function videoThumbnails(path,total) {
  if(typeof document==='undefined')return []
  const reader=await frameReader(path),output=canvas(80,80),images=[]
  try{for(let i=0;i<6;i++){
    const frame=await reader.at(Math.min(total-.05,total*(i+.5)/6));output.width=80;output.height=80
    const ctx=output.getContext('2d'),scale=Math.max(80/frame.width,80/frame.height),w=frame.width*scale,h=frame.height*scale
    ctx.drawImage(frame.image,(80-w)/2,(80-h)/2,w,h);images.push(output.toDataURL('image/jpeg',.6))
  }return images}finally{output.width=1;await reader.close().catch(()=>{})}
}
