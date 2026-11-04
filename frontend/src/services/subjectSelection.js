import {visitorHeaders} from '@/services/popularityService'
import {imageEditError,editImage,disposeEditedImage} from '@/services/imageEditing'
import {API_BASE_URL} from '@/constants'
const recent=new Map()
export function paddedFaceBox(rect,width,height){
 let x=Number(rect.originX??rect.x),y=Number(rect.originY??rect.y),w=Number(rect.width),h=Number(rect.height)
 if(![x,y,w,h].every(Number.isFinite)||w<=0||h<=0)return null
 if(w<=1&&h<=1&&Math.abs(x)<=1&&Math.abs(y)<=1){x*=width;y*=height;w*=width;h*=height}
 const size=Math.min(Math.max(w,h)*1.65,width,height),left=Math.max(0,Math.min(width-size,x+w/2-size/2)),top=Math.max(0,Math.min(height-size,y+h*.45-size/2))
 return [left/width,top/height,size/width,size/height]
}
export async function detectSubjects(path,{force=false,extended=false,withMask=false,isCurrent=()=>true,onTask=()=>{}}={}){
 const session=uni.getStorageSync('gensticker.session.v1'),owner=session?.profile?.id,headers=visitorHeaders()
 const current=()=>isCurrent() && owner===uni.getStorageSync('gensticker.session.v1')?.profile?.id
 const key=JSON.stringify([owner||'',path,extended,withMask]),hit=recent.get(key)
 if(!force && hit && Date.now()-hit.time<120000 && current())return hit.value
 const remember=value=>{if(current()){recent.set(key,{time:Date.now(),value});while(recent.size>12)recent.delete(recent.keys().next().value)}return value}
 if(!current())return {candidates:[],method:'manual'}
 // Native face-engine initialization can also block the UI thread. Use the
 // bounded server detector; manual framing remains available while it waits.
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
