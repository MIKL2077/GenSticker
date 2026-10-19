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
  return Promise.race([promise,new Promise((_,reject)=>timer=setTimeout(()=>reject(Error('这台设备读取视频超时，请缩短片段或使用兼容模式')),ms))]).finally(()=>clearTimeout(timer))
}
// The browser seeks the selected window; WeChat uses its native local decoder.
// No video upload is needed on this path. Keep only downscaled output frames in memory.
async function frameReader(path) {
  if(typeof document !== 'undefined') {
    const video=document.createElement('video');video.muted=true;video.playsInline=true;video.preload='auto';video.src=path
    try { await deadline(new Promise((resolve,reject)=>{video.onloadeddata=resolve;video.onerror=()=>reject(Error('这个视频暂时不能解码'))})) } catch(e){video.removeAttribute('src');video.load();throw e}
    return {async at(seconds){if(Math.abs(video.currentTime-seconds)>.015)await deadline(new Promise((resolve,reject)=>{video.onseeked=resolve;video.onerror=()=>reject(Error('视频定位失败'));video.currentTime=seconds}));return {image:video,width:video.videoWidth,height:video.videoHeight}},async close(){video.pause();video.removeAttribute('src');video.load()}}
  }
  const decoder=wx.createVideoDecoder(),rawCanvas=canvas(1,1)
  try { await deadline(decoder.start({source:path,mode:1,abortAudio:true})) } catch(e){await decoder.remove().catch(()=>{});throw e}
  return {async at(seconds){
    await deadline(decoder.seek(Math.round(seconds*1000)))
    const end=Date.now()+3000;let frame
    while(!(frame=decoder.getFrameData())){if(Date.now()>end)throw Error('没有读到动态画面，请换一段视频');await pause(10)}
    if(frame.width*frame.height>12_000_000)throw Error('这段视频分辨率过高，请从相册导出 1080p 版本')
    rawCanvas.width=frame.width;rawCanvas.height=frame.height
    const ctx=rawCanvas.getContext('2d'),image=ctx.createImageData(frame.width,frame.height)
    image.data.set(new Uint8Array(frame.data));ctx.putImageData(image,0,0)
    return {image:rawCanvas,width:frame.width,height:frame.height}
  },async close(){rawCanvas.width=1;rawCanvas.height=1;try{await decoder.stop()}finally{await decoder.remove()}}}
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
  if(options.text){
    const size=Math.max(11,Math.min(20,Math.round(geo.width/12)));ctx.font=`bold ${size}px sans-serif`;ctx.textAlign='center';ctx.textBaseline='top'
    const lines=[];let line=''
    for(const char of options.text){if(ctx.measureText(line+char).width>geo.width-12 && line){lines.push(line);line=char}else line+=char}
    if(line)lines.push(line)
    const visible=lines.slice(0,3),top=Math.max(0,geo.height-visible.length*(size+3)-8)
    ctx.fillStyle='#fff5df';ctx.fillRect(0,top,geo.width,geo.height-top);ctx.fillStyle='#253f45'
    visible.forEach((value,i)=>ctx.fillText(value,geo.width/2,top+4+i*(size+3)))
  }
  return geo
}
export async function encodeGifFrames(frames,width,height,onProgress=()=>{},cancelled) {
  // Start at 128 colors. Reduce fps, then palette, preserving the selected duration.
  for(const [stride,colors] of [[1,128],[2,128],[2,64],[3,64],[3,32]]) {
    const encoder=GIFEncoder()
    for(let i=0;i<frames.length;i+=stride){
      checkCancelled(cancelled)
      const rgba=frames[i],palette=quantize(rgba,colors),indices=applyPalette(rgba,palette)
      encoder.writeFrame(indices,width,height,{palette,delay:Math.min(stride,frames.length-i)*100,repeat:0,dispose:1})
      onProgress(Math.round(65+30*Math.min(1,(i+stride)/frames.length)))
      if(i%4===0)await pause(0)
    }
    encoder.finish();const bytes=encoder.bytes()
    if(bytes.length<=MAX_GIF_BYTES)return {bytes,fps:10/stride,colors}
  }
  throw Error('这段画面变化太多，500 KB 内会明显失真，请缩短到 3 秒或缩小裁剪范围')
}
export async function renderLocalGif(path, options, onProgress=()=>{}, cancelled) {
  if(!supportsLocalGif())throw Error('当前微信不支持本地制作，请更新微信或使用兼容模式')
  const reader=await frameReader(path),output=canvas(1,1),frames=[]
  try {
    const count=Math.max(2,Math.ceil(options.duration*10));let width,height
    for(let i=0;i<count;i++) {
      checkCancelled(cancelled)
      const frame=await reader.at(options.start+i*options.duration/count)
      const geo=drawFrame(output.getContext('2d'),frame.image,frame.width,frame.height,options)
      width=geo.width;height=geo.height;frames.push(output.getContext('2d').getImageData(0,0,width,height).data)
      onProgress(Math.round(65*(i+1)/count));await pause(0)
    }
    const result=await encodeGifFrames(frames,width,height,onProgress,cancelled)
    checkCancelled(cancelled)
    let resultPath
    if(typeof document !== 'undefined')resultPath=registerTemporary(URL.createObjectURL(new Blob([result.bytes],{type:'image/gif'})))
    else{resultPath=`${uni.env.USER_DATA_PATH}/generated_meme_live_${Date.now()}.gif`;await writeOwnedFile(resultPath,result.bytes.buffer.slice(result.bytes.byteOffset,result.bytes.byteOffset+result.bytes.byteLength))}
    onProgress(100);return {...result,path:resultPath,width,height}
  } finally {frames.length=0;output.width=1;output.height=1;await reader.close().catch(()=>{})}
}
// Read an original album image only to find an embedded motion stream. A static
// iPhone preview cannot reconstruct the paired MOV; never fabricate animation.
export async function albumMotion(path) {
  let bytes
  if(typeof document !== 'undefined')bytes=new Uint8Array(await(await fetch(path)).arrayBuffer())
  else {
    const fs=uni.getFileSystemManager(),stat=await new Promise((resolve,reject)=>fs.stat({path,success:r=>resolve(r.stats),fail:reject}))
    if(stat.size>30*1024*1024)throw Error('Live 原图最多 30 MB，请在相册存储为视频后选择')
    bytes=new Uint8Array(await new Promise((resolve,reject)=>fs.readFile({filePath:path,success:r=>resolve(r.data),fail:reject})))
  }
  if(bytes.length>30*1024*1024)throw Error('Live 原图最多 30 MB，请在相册存储为视频后选择')
  for(let i=4;i<bytes.length-8;i++)if(bytes[i]===102 && bytes[i+1]===116 && bytes[i+2]===121 && bytes[i+3]===112){
    const brand=String.fromCharCode(...bytes.slice(i+4,i+8)),size=new DataView(bytes.buffer,bytes.byteOffset+i-4,4).getUint32(0)
    if(['heic','heix','hevc','hevx','mif1','avif'].includes(brand)||size<8||size>256)continue
    const motion=bytes.slice(i-4)
    if(typeof document!=='undefined')return registerTemporary(URL.createObjectURL(new Blob([motion],{type:'video/mp4'})))
    const destination=`${uni.env.USER_DATA_PATH}/gensticker_edit_motion_${Date.now()}.mp4`
    await writeOwnedFile(destination,motion.buffer);return registerTemporary(destination)
  }
  throw Error('微信只返回了静态照片。请在手机相册打开这张 Live 图，选择“存储为视频”，再点“从相册选视频”；无需发送到聊天。')
}
export const disposeLocalMedia=releaseTemporary

export async function localVideoInfo(path) {
  if(typeof document === 'undefined')return new Promise((resolve,reject)=>uni.getVideoInfo({src:path,success:resolve,fail:reject}))
  const video=document.createElement('video');video.preload='metadata';video.src=path
  try{await deadline(new Promise((resolve,reject)=>{video.onloadedmetadata=resolve;video.onerror=()=>reject(Error('这个视频格式暂时无法播放'))}));return {duration:video.duration,width:video.videoWidth,height:video.videoHeight}}
  finally{video.removeAttribute('src');video.load()}
}
