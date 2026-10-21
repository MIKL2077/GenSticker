import {visitorHeaders} from '@/services/popularityService'
import {imageEditError} from '@/services/imageEditing'
import {API_BASE_URL} from '@/constants'
import {prepareImage} from '@/services/imagePreparation'
export function paddedFaceBox(rect,width,height){
 let x=Number(rect.originX??rect.x),y=Number(rect.originY??rect.y),w=Number(rect.width),h=Number(rect.height)
 if(![x,y,w,h].every(Number.isFinite)||w<=0||h<=0)return null
 if(w<=1&&h<=1&&Math.abs(x)<=1&&Math.abs(y)<=1){x*=width;y*=height;w*=width;h*=height}
 const size=Math.min(Math.max(w,h)*1.65,width,height),left=Math.max(0,Math.min(width-size,x+w/2-size/2)),top=Math.max(0,Math.min(height-size,y+h*.45-size/2))
 return [left/width,top/height,size/width,size/height]
}
function deadline(promise,ms=1800){let timer;return Promise.race([promise,new Promise((_,reject)=>timer=setTimeout(()=>reject(Error('本机检测暂不可用')),ms))]).finally(()=>clearTimeout(timer))}
const call=(api,options={})=>deadline(new Promise((resolve,reject)=>api({...options,success:resolve,fail:error=>reject(imageEditError(error))})))
async function nativeDetect(path){
 if(typeof document!=='undefined'||typeof wx==='undefined'||!wx.initFaceDetect||!wx.faceDetect||!wx.createOffscreenCanvas || (uni.getDeviceInfo?.().platform || uni.getSystemInfoSync?.().platform)==='devtools')throw Error('use server')
 let started=false
 const canvas=wx.createOffscreenCanvas({type:'2d',width:1,height:1}),image=canvas.createImage()
 try{
  await deadline(new Promise((resolve,reject)=>{image.onload=resolve;image.onerror=reject;image.src=path}))
  const scale=Math.min(1,640/Math.max(image.width,image.height));canvas.width=Math.max(1,Math.round(image.width*scale));canvas.height=Math.max(1,Math.round(image.height*scale))
  const ctx=canvas.getContext('2d');ctx.drawImage(image,0,0,canvas.width,canvas.height);const rgba=ctx.getImageData(0,0,canvas.width,canvas.height).data
  await call(wx.initFaceDetect.bind(wx));started=true;const result=await call(wx.faceDetect.bind(wx),{frameBuffer:rgba.buffer,width:canvas.width,height:canvas.height,enableMultiFace:true,enablePoint:false})
  const faces=result.faceInfo?.length?result.faceInfo:result.detectRect?[result]:[]
  const candidates=faces.map((face,index)=>({id:String(index),kind:'person',box:paddedFaceBox(face.detectRect||face,canvas.width,canvas.height)})).filter(item=>item.box)
  return {candidates,method:'device-wechat'}
 }finally{canvas.width=1;canvas.height=1;try{if(started)wx.stopFaceDetect?.({fail:()=>{}})}catch(_){}}
}
export async function detectSubjects(path){
 const session=uni.getStorageSync('gensticker.session.v1'),owner=session?.profile?.id,headers=visitorHeaders()
 path=await prepareImage(path)
 if(owner!==uni.getStorageSync('gensticker.session.v1')?.profile?.id)return {candidates:[],method:'manual'}
 try{const local=await nativeDetect(path);if(local.candidates.length)return local}catch(_){}
 if(owner!==uni.getStorageSync('gensticker.session.v1')?.profile?.id)return {candidates:[],method:'manual'}
 return new Promise((resolve,reject)=>uni.uploadFile({url:API_BASE_URL+'/recommend/subjects/detect',filePath:path,name:'file',header:headers,timeout:15000,success:response=>{try{const data=JSON.parse(response.data);if(response.statusCode===200)resolve(data);else reject(Error(typeof data.detail==='string'?data.detail:'自动检测服务暂不可用（'+response.statusCode+'）'))}catch(error){reject(error)}},fail:error=>reject(imageEditError(error))}))
}
