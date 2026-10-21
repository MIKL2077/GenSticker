import {visitorHeaders} from '@/services/popularityService'
import {imageEditError,editImage,disposeEditedImage} from '@/services/imageEditing'
import {API_BASE_URL} from '@/constants'
const recent=new Map()
let nativeBusy=false,nativeUnavailableUntil=0
export function paddedFaceBox(rect,width,height){
 let x=Number(rect.originX??rect.x),y=Number(rect.originY??rect.y),w=Number(rect.width),h=Number(rect.height)
 if(![x,y,w,h].every(Number.isFinite)||w<=0||h<=0)return null
 if(w<=1&&h<=1&&Math.abs(x)<=1&&Math.abs(y)<=1){x*=width;y*=height;w*=width;h*=height}
 const size=Math.min(Math.max(w,h)*1.65,width,height),left=Math.max(0,Math.min(width-size,x+w/2-size/2)),top=Math.max(0,Math.min(height-size,y+h*.45-size/2))
 return [left/width,top/height,size/width,size/height]
}
function deadline(promise,ms){let timer;return Promise.race([promise,new Promise((_,reject)=>timer=setTimeout(()=>reject(Error('本机检测暂不可用')),ms))]).finally(()=>clearTimeout(timer))}
async function nativeDetect(path,current){
 if(typeof document!=='undefined'||typeof wx==='undefined'||!wx.initFaceDetect||!wx.faceDetect||!wx.createOffscreenCanvas || (uni.getDeviceInfo?.().platform || uni.getSystemInfoSync?.().platform)==='devtools')throw Error('use server')
 if(nativeBusy || Date.now()<nativeUnavailableUntil)throw Error('use server')
 const end=Date.now()+900
 const budget=task=>deadline(task,Math.max(1,end-Date.now()))
 const call=(api,options={})=>{if(!current() || Date.now()>=end)throw Error('detection canceled');return budget(new Promise((resolve,reject)=>api({...options,success:resolve,fail:reject})))}
 let started=false
 const stop=()=>{if(started){started=false;try{wx.stopFaceDetect?.({fail:()=>{}})}catch(_){}}}
 const canvas=wx.createOffscreenCanvas({type:'2d',width:1,height:1}),image=canvas.createImage()
 nativeBusy=true
 try{
  await budget(new Promise((resolve,reject)=>{image.onload=resolve;image.onerror=reject;image.src=path}))
  const scale=Math.min(1,640/Math.max(image.width,image.height));canvas.width=Math.max(1,Math.round(image.width*scale));canvas.height=Math.max(1,Math.round(image.height*scale))
  const ctx=canvas.getContext('2d');ctx.drawImage(image,0,0,canvas.width,canvas.height);const rgba=ctx.getImageData(0,0,canvas.width,canvas.height).data
  if(!current() || Date.now()>=end)throw Error('detection canceled')
  await budget(new Promise((resolve,reject)=>wx.initFaceDetect({success:result=>{started=true;if(Date.now()>=end || !current())stop();resolve(result)},fail:reject})))
  const result=await call(wx.faceDetect.bind(wx),{frameBuffer:rgba.buffer,width:canvas.width,height:canvas.height,enableMultiFace:true,enablePoint:false})
  const faces=result.faceInfo?.length?result.faceInfo:result.detectRect?[result]:[]
  const candidates=faces.map((face,index)=>({id:String(index),kind:'person',box:paddedFaceBox(face.detectRect||face,canvas.width,canvas.height)})).filter(item=>item.box)
  return {candidates,method:'device-wechat'}
 }catch(error){nativeUnavailableUntil=Date.now()+60000;throw error}
 finally{nativeBusy=false;canvas.width=1;canvas.height=1;stop()}
}
export async function detectSubjects(path,{force=false,extended=false,withMask=false,isCurrent=()=>true,onTask=()=>{}}={}){
 const session=uni.getStorageSync('gensticker.session.v1'),owner=session?.profile?.id,headers=visitorHeaders()
 const current=()=>isCurrent() && owner===uni.getStorageSync('gensticker.session.v1')?.profile?.id
 const key=JSON.stringify([owner||'',path,extended,withMask]),hit=recent.get(key)
 if(!force && hit && Date.now()-hit.time<120000 && current())return hit.value
 const remember=value=>{if(current()){recent.set(key,{time:Date.now(),value});while(recent.size>12)recent.delete(recent.keys().next().value)}return value}
 if(!current())return {candidates:[],method:'manual'}
 // Decode the original once at detection size; don't compress a large upload
 // before trying the device API, which never needs to upload the photo.
 try{const local=await nativeDetect(path,current);if(local.candidates.length && current())return remember(local)}catch(_){}
 if(!current())return {candidates:[],method:'manual'}
 let upload
 try{
  upload=await editImage(path,{type:'crop',rect:[0,0,1,1],fileType:'jpg',maxEdge:640,skipPrepare:true})
  if(!current())return {candidates:[],method:'manual'}
  const result=await new Promise((resolve,reject)=>{
   const task=uni.uploadFile({url:API_BASE_URL+'/recommend/subjects/detect',filePath:upload,name:'file',formData:{fast:extended?'false':'true',with_mask:withMask?'true':'false'},header:headers,timeout:12000,success:response=>{try{const data=JSON.parse(response.data);if(response.statusCode===200)resolve(data);else reject(Error(typeof data.detail==='string'?data.detail:'自动检测服务暂不可用（'+response.statusCode+'）'))}catch(error){reject(error)}},fail:error=>reject(imageEditError(error))})
   onTask(task)
  })
  return current()?remember(result):{candidates:[],method:'manual'}
 }finally{if(upload && upload!==path)disposeEditedImage(upload)}
}
