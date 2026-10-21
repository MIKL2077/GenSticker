import {API_BASE_URL} from '@/constants'

// The same pinned U2NetP model and normalization as the server. Only public
// weights are persisted; photos and their masks stay in transient canvases.
const MODEL_SHA='309c8469258dda742793dce0ebea8e6dd393174f89934733ecc8b14c76f4ddd8'
const MODEL_SHA1='0a99236f0d5c1916a99a8c401b23e5ef32038606',MODEL_BYTES=4574861,EDGE=320
let sessionTask=null,session=null,idleTimer=null,unavailableUntil=0,localBusy=false
function deadline(task,ms){let timer;return Promise.race([task,new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('本机处理超时')),ms)})]).finally(()=>clearTimeout(timer))}
const call=(fn,options)=>new Promise((resolve,reject)=>fn({...options,success:resolve,fail:reject}))
function supported(){return typeof document==='undefined' && typeof wx!=='undefined' && !!wx.createInferenceSession && !!wx.createOffscreenCanvas && !!uni.env?.USER_DATA_PATH && (uni.getDeviceInfo?.().platform || uni.getSystemInfoSync?.().platform)!=='devtools'}
function releaseSession(){clearTimeout(idleTimer);try{session?.destroy()}catch(_){}session=null;sessionTask=null}
function keepAlive(){clearTimeout(idleTimer);idleTimer=setTimeout(()=>{if(!localBusy)releaseSession();else keepAlive()},90000)}
async function modelFile(){
 const fs=uni.getFileSystemManager(),path=uni.env.USER_DATA_PATH+'/gensticker_u2netp_'+MODEL_SHA.slice(0,12)+'.onnx'
 const verify=async file=>{const info=await call(fs.getFileInfo.bind(fs),{filePath:file,digestAlgorithm:'sha1'});if(info.size!==MODEL_BYTES || info.digest!==MODEL_SHA1)throw Error('模型校验失败')}
 try{await verify(path);return path}catch(_){await call(fs.unlink.bind(fs),{filePath:path}).catch(()=>{})}
 let temporary=''
 try{
  const result=await call(uni.downloadFile.bind(uni),{url:API_BASE_URL+'/images/subject-model/'+MODEL_SHA+'.onnx',timeout:30000})
  temporary=result.tempFilePath;if(result.statusCode!==200)throw Error('本机模型暂不可用')
  await verify(temporary)
  await call(fs.saveFile.bind(fs),{tempFilePath:temporary,filePath:path});temporary=''
  return path
 }finally{if(temporary)fs.unlink({filePath:temporary,fail:()=>{}})}
}
export function warmLocalBackground(){
 if(!supported() || Date.now()<unavailableUntil)return Promise.reject(Error('使用云端处理'))
 if(sessionTask){keepAlive();return sessionTask}
 sessionTask=(async()=>{
  const model=await modelFile()
  // Some iOS devices expose NPU support but reject individual operators.
  // Retry the same verified model with NPU disabled before leaving the device.
  for(const allowNPU of [true,false]){
   let loading
   try{
    loading=wx.createInferenceSession({model,precisionLevel:2,allowNPU,allowQuantize:false,typicalShape:{'input.1':[1,3,EDGE,EDGE]}})
    await deadline(new Promise((resolve,reject)=>{loading.onLoad(resolve);loading.onError(reject)}),8000)
    session=loading;keepAlive();return session
   }catch(error){try{loading?.destroy()}catch(_){}if(!allowNPU)throw error}
  }
 })().catch(error=>{sessionTask=null;unavailableUntil=Date.now()+60000;throw error})
 return sessionTask
}
export function modelInput(rgba){
 const area=EDGE*EDGE;if(rgba.length!==area*4)throw Error('本机输入尺寸无效')
 let maximum=1
 for(let i=0;i<rgba.length;i+=4)maximum=Math.max(maximum,rgba[i],rgba[i+1],rgba[i+2])
 const means=[.485,.456,.406],std=[.229,.224,.225],input=new Float32Array(area*3)
 for(let i=0;i<area;i++)for(let channel=0;channel<3;channel++)input[channel*area+i]=(rgba[i*4+channel]/maximum-means[channel])/std[channel]
 return input
}
export function predictionMask(tensor){
 if(!tensor || tensor.type!=='float32' || String(tensor.shape)!=='1,1,320,320')throw Error('本机模型输出无效')
 const values=tensor.data instanceof ArrayBuffer ? new Float32Array(tensor.data) : tensor.data
 if(!values || values.length!==EDGE*EDGE)throw Error('本机模型输出尺寸无效')
 let low=Infinity,high=-Infinity
 for(const value of values){if(!Number.isFinite(value))throw Error('本机识别不明确');low=Math.min(low,value);high=Math.max(high,value)}
 if(high-low<1e-6)throw Error('本机识别不明确')
 const rgba=new Uint8ClampedArray(EDGE*EDGE*4);let foreground=0
 for(let i=0;i<values.length;i++){const alpha=Math.round((values[i]-low)/(high-low)*255);rgba[i*4]=rgba[i*4+1]=rgba[i*4+2]=255;rgba[i*4+3]=alpha;if(alpha>80)foreground++}
 if(foreground/values.length<.005 || foreground/values.length>.995)throw Error('本机识别不明确')
 return rgba
}
function newCanvas(width,height){const canvas=typeof document!=='undefined'?document.createElement('canvas'):wx.createOffscreenCanvas?.({type:'2d',width,height});if(!canvas)throw Error('当前设备使用云端处理');canvas.width=width;canvas.height=height;return canvas}
async function drawSource(path){
 const info=await call(uni.getImageInfo.bind(uni),{src:path})
 if(info.width*info.height>40000000)throw Error('图片过大，请先缩小')
 const scale=Math.min(1,1280/Math.max(info.width,info.height)),canvas=newCanvas(Math.max(1,Math.round(info.width*scale)),Math.max(1,Math.round(info.height*scale)))
 try{
  const image=typeof document!=='undefined'?new Image():canvas.createImage()
  await deadline(new Promise((resolve,reject)=>{image.onload=resolve;image.onerror=reject;image.src=path}),5000)
  // The decoded image is upright, unlike getImageInfo's EXIF sensor dimensions.
  const decodedScale=Math.min(1,1280/Math.max(image.width,image.height))
  canvas.width=Math.max(1,Math.round(image.width*decodedScale));canvas.height=Math.max(1,Math.round(image.height*decodedScale))
  canvas.getContext('2d').drawImage(image,0,0,canvas.width,canvas.height);return canvas
 }catch(error){canvas.width=canvas.height=1;throw error}
}
async function trimmedExport(canvas,exportCanvas){
 const ctx=canvas.getContext('2d'),pixels=ctx.getImageData(0,0,canvas.width,canvas.height).data
 let left=canvas.width,top=canvas.height,right=-1,bottom=-1
 for(let y=0;y<canvas.height;y++)for(let x=0;x<canvas.width;x++)if(pixels[(y*canvas.width+x)*4+3]>0){left=Math.min(left,x);right=Math.max(right,x);top=Math.min(top,y);bottom=Math.max(bottom,y)}
 if(right<left)throw Error('图片主体为空，原图已保留')
 if(left===0 && top===0 && right===canvas.width-1 && bottom===canvas.height-1)return exportCanvas(canvas,'png')
 const cropped=newCanvas(right-left+1,bottom-top+1)
 try{cropped.getContext('2d').drawImage(canvas,left,top,cropped.width,cropped.height,0,0,cropped.width,cropped.height);return await exportCanvas(cropped,'png')}finally{cropped.width=cropped.height=1}
}
export async function prepareForeground(path,exportCanvas){
 let canvas,inputCanvas,maskCanvas,hasTransparency=false
 try{
  canvas=await drawSource(path)
  const ctx=canvas.getContext('2d'),pixels=ctx.getImageData(0,0,canvas.width,canvas.height).data
  let clear=0,visible=0
  for(let i=3;i<pixels.length;i+=4){if(pixels[i]<240)clear++;if(pixels[i]>20)visible++;if(pixels[i]<255)hasTransparency=true}
  if(!visible)throw Error('图片主体为空，原图已保留')
  if(clear/(pixels.length/4)>=.02)return {path:await trimmedExport(canvas,exportCanvas),method:'alpha'}
  if(!localBusy && supported()){
   localBusy=true;clearTimeout(idleTimer)
   let inference
   try{
    inference=await deadline(warmLocalBackground(),1200)
    inputCanvas=newCanvas(EDGE,EDGE);const inputCtx=inputCanvas.getContext('2d');inputCtx.drawImage(canvas,0,0,EDGE,EDGE)
    const input=modelInput(inputCtx.getImageData(0,0,EDGE,EDGE).data)
    const output=await deadline(inference.run({'input.1':{type:'float32',shape:[1,3,EDGE,EDGE],data:input.buffer}}),4000)
    const mask=predictionMask(output['1959'])
    maskCanvas=newCanvas(EDGE,EDGE);const maskCtx=maskCanvas.getContext('2d'),image=maskCtx.createImageData(EDGE,EDGE);image.data.set(mask);maskCtx.putImageData(image,0,0)
    ctx.globalCompositeOperation='destination-in';ctx.drawImage(maskCanvas,0,0,canvas.width,canvas.height);ctx.globalCompositeOperation='source-over';hasTransparency=true
    return {path:await trimmedExport(canvas,exportCanvas),method:'device'}
   }catch(_){if(inference){releaseSession();unavailableUntil=Date.now()+60000}}
   finally{localBusy=false;if(session)keepAlive()}
  }
  // Bound PNG/camera inputs too, and avoid base64-uploading a multi-megapixel PNG.
  return {upload:await exportCanvas(canvas,hasTransparency?'png':'jpg'),method:'server'}
 }catch(error){if(/主体为空/.test(error.message||''))throw error;return {upload:path,method:'server'}}
 finally{for(const item of [canvas,inputCanvas,maskCanvas])if(item)item.width=item.height=1}
}
