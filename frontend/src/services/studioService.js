import {ref} from 'vue'
import { apiRequest } from '@/services/apiService'
import { API_BASE_URL } from '@/constants'
import { prepareImage } from '@/services/imagePreparation'
import { downloadResult } from '@/services/recommendService'
export const listStudioJobs=()=>apiRequest('/studio/jobs',{},1).then(items=>items.filter(item=>!(uni.getStorageSync(deletedLocalKey())||[]).includes(item.id)))
export const getStudioJob=id=>apiRequest(`/studio/jobs/${id}`,{},1)
export const listMyTemplates=()=>apiRequest('/studio/templates',{},1)
export const getMyTemplate=id=>apiRequest(`/studio/templates/${id}`,{},1)
export const createTemplate=data=>apiRequest('/studio/templates',{method:'POST',data,timeout:60000},1)
export const publishTemplate=id=>apiRequest(`/studio/templates/${id}/publish`,{method:'POST',data:{rights_attested:true}},1)
export const templateQuota=()=>apiRequest('/studio/quota',{},1)
export const deleteStudioJob=id=>apiRequest(`/studio/jobs/${id}`,{method:'DELETE'},1)
export const uniqueKey=()=>`${Date.now()}-${Math.random().toString(36).slice(2)}`
export async function encodePhoto(path){
 path=await prepareImage(path)
 if(typeof document!=='undefined'){
  const blob=await(await fetch(path)).blob()
  if(blob.size>4*1024*1024)throw Error('图片超过 4 MB，先裁剪一下吧')
  return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=reject;reader.readAsDataURL(blob)})
 }
 const fs=uni.getFileSystemManager(),info=await new Promise((resolve,reject)=>fs.stat({path,success:resolve,fail:reject}))
 if(info.stats.size>4*1024*1024)throw Error('图片超过 4 MB，先裁剪一下吧')
 return new Promise((resolve,reject)=>fs.readFile({filePath:path,encoding:'base64',success:r=>resolve(r.data),fail:reject}))
}
const pendingKey=()=>`gensticker.studio.pending.${uni.getStorageSync('gensticker.session.v1')?.profile?.id||'guest'}`
export function trackStudioJob(item,owner=uni.getStorageSync('gensticker.session.v1')?.profile?.id){if(owner!==uni.getStorageSync('gensticker.session.v1')?.profile?.id)return item;const pending=uni.getStorageSync(pendingKey())||[];uni.setStorageSync(pendingKey(),[...new Set([...pending,item.id])].slice(-50));return item}
export async function submitManual(template_key,paths,texts,args,options){
 const session=uni.getStorageSync('gensticker.session.v1'),owner=session?.profile?.id
 const images=[];for(const path of paths)images.push(await encodePhoto(path))
 if(owner!==uni.getStorageSync('gensticker.session.v1')?.profile?.id)throw Error('账号已切换，请重新制作')
 return trackStudioJob(await apiRequest('/studio/jobs',{method:'POST',timeout:60000,header:{Authorization:`Bearer ${session.access_token}`},data:{template_key,images,texts,args,extract_subject:!!options.extractSubject,idempotency_key:options.idempotencyKey||uniqueKey()}},1),owner)
}
export async function submitAITemplate(path,key,rights_attested=true){const session=uni.getStorageSync('gensticker.session.v1'),owner=session?.profile?.id,image=await encodePhoto(path);if(owner!==uni.getStorageSync('gensticker.session.v1')?.profile?.id)throw Error('账号已切换，请重新提交');return trackStudioJob(await apiRequest('/studio/templates/ai',{method:'POST',timeout:60000,header:{Authorization:`Bearer ${session.access_token}`},data:{image,idempotency_key:key,rights_attested}},1),owner)}
export const privateImage=downloadResult
let notificationTimer=null,checking=false
export function stopStudioNotifications(){clearInterval(notificationTimer);notificationTimer=null}
export function startStudioNotifications(){
 stopStudioNotifications()
 const check=async()=>{
  refreshUnread();syncLocalLiveResults().catch(()=>{});const session=uni.getStorageSync('gensticker.session.v1');if(!session || checking)return
  const owner=session.profile.id,key=pendingKey(),pending=uni.getStorageSync(key)||[];if(!pending.length)return
  checking=true
  try{const jobs=await listStudioJobs();if(uni.getStorageSync('gensticker.session.v1')?.profile?.id!==owner)return
   const finished=jobs.filter(j=>pending.includes(j.id)&&!['queued','running'].includes(j.status))
   if(finished.length){uni.setStorageSync(key,pending.filter(id=>!finished.some(j=>j.id===id)));uni.$emit('studio-completed',finished);uni.showToast({title:finished.some(j=>j.status==='completed')?'小窝喊你收图啦！':'有个任务需要看看',icon:'none',duration:3000})}
  }catch(_){}finally{checking=false}
 }
 check();notificationTimer=setInterval(check,5000)
}

const localOwner=()=>uni.getStorageSync('gensticker.session.v1')?.profile?.id||'guest'
const localResultsKey=(owner=localOwner())=>`gensticker.manual.local.${owner}.v1`
export function guestResults(owner=localOwner()){const now=Date.now()/1000;return (uni.getStorageSync(localResultsKey(owner))||[]).filter(r=>now-r.created_at<7*86400).map(r=>r.status==='running'&&now-r.created_at>120?{...r,status:'failed',message:'本地制作已中断，请重新选择片段'}:r)}
export function updateLocalResult(id,changes,owner=localOwner()){if(owner!==localOwner())return;uni.setStorageSync(localResultsKey(owner),guestResults(owner).map(item=>item.id===id?{...item,...changes}:item))}
export function beginLocalLive(owner=localOwner()){const item={id:uniqueKey(),local:true,kind:'livegif',status:'running',created_at:Date.now()/1000,message:'正在这台设备制作 GIF'};uni.setStorageSync(localResultsKey(owner),[item,...guestResults(owner)].slice(0,12));return item}
export function rememberGuestMeme(path,viewed=false,kind='manual'){const item={id:uniqueKey(),local:true,kind,status:'completed',created_at:Date.now()/1000,message:'只保存在这台设备，保留近 7 天',localPath:path,...(viewed?{viewedAt:Date.now()}:{})};try{uni.setStorageSync(localResultsKey(),[item,...guestResults()].slice(0,12))}catch(_){}return item}
export function linkLocalResult(id,serverId,owner=localOwner()){updateLocalResult(id,{serverId},owner)}
const deletedLocalKey=(owner=localOwner())=>`gensticker.live.deleted.${owner}`
const scheduleCloudDelete=(id,owner=localOwner())=>{const ids=uni.getStorageSync(deletedLocalKey(owner))||[];uni.setStorageSync(deletedLocalKey(owner),[...new Set([...ids,id])].slice(-50))}
export function removeGuestMeme(id){const items=guestResults();for(const item of items.filter(r=>r.id===id||r.serverId===id))if(item.serverId)scheduleCloudDelete(item.serverId);uni.setStorageSync(localResultsKey(),items.filter(r=>r.id!==id && r.serverId!==id))}
let syncing=false
// Local completion never waits for the network. Retry only small final GIFs,
// with stable idempotency and the captured account, when the app is active.
export async function syncLocalLiveResults(){
 const session=uni.getStorageSync('gensticker.session.v1'),owner=session?.profile?.id
 if(!owner||syncing)return;syncing=true
 try{
 for(const id of uni.getStorageSync(deletedLocalKey(owner))||[]){
  if(owner!==localOwner())return
  try{await deleteStudioJob(id)}catch(error){if(error.statusCode!==404)continue}
  if(owner!==localOwner())return
  uni.setStorageSync(deletedLocalKey(owner),(uni.getStorageSync(deletedLocalKey(owner))||[]).filter(value=>value!==id))
 }
 for(const item of guestResults(owner).filter(r=>r.kind==='livegif'&&r.serverId&&r.viewedAt&&!r.viewSynced)){
  if(owner!==localOwner())return
  try{await apiRequest(`/studio/jobs/${item.serverId}/view`,{method:'POST',header:{Authorization:'Bearer '+session.access_token}},1);updateLocalResult(item.id,{viewSynced:true},owner)}catch(_){}
 }
 for(const item of guestResults(owner).filter(r=>r.kind==='livegif'&&r.status==='completed'&&r.localPath&&!r.serverId&&Date.now()-(r.syncAttempt||0)>30000)){
  if(owner!==localOwner())return
  updateLocalResult(item.id,{syncAttempt:Date.now()},owner)
  try{
   const job=await new Promise((resolve,reject)=>uni.uploadFile({url:API_BASE_URL+'/studio/live/results',filePath:item.localPath,name:'file',formData:{idempotency_key:item.id},header:{Authorization:'Bearer '+session.access_token},timeout:20000,success:r=>{try{const data=JSON.parse(r.data);r.statusCode===201?resolve(data):reject(Error(data.detail||'同步稍后重试'))}catch(e){reject(e)}},fail:reject}))
   if(owner!==localOwner())return
   if(!guestResults(owner).some(value=>value.id===item.id)){scheduleCloudDelete(job.id,owner);continue}
   updateLocalResult(item.id,{serverId:job.id,message:'本机已完成，已同步到作品队列'},owner)
   if(guestResults(owner).find(value=>value.id===item.id)?.viewedAt){await apiRequest(`/studio/jobs/${job.id}/view`,{method:'POST',header:{Authorization:'Bearer '+session.access_token}},1);updateLocalResult(item.id,{viewSynced:true},owner)}
  }catch(_){updateLocalResult(item.id,{message:'本地已完成，可保存分享；联网后自动同步'},owner)}
 }}finally{syncing=false}
}

let supportPromise=null,supportTime=0
export function supportsStudio(){if(!supportPromise || Date.now()-supportTime>30000){supportTime=Date.now();supportPromise=apiRequest('/account/config',{},1).then(data=>data.features?.studio===true).catch(e=>{supportPromise=null;throw e})}return supportPromise}

export const unreadCount=ref(0)
export const refreshUnread=async()=>{const owner=uni.getStorageSync('gensticker.session.v1')?.profile?.id;if(!owner){unreadCount.value=guestResults().filter(r=>!r.viewedAt).length;return}try{const data=await apiRequest('/studio/unread',{},1);if(owner===uni.getStorageSync('gensticker.session.v1')?.profile?.id)unreadCount.value=data.count+guestResults().filter(r=>r.status==='completed'&&!r.serverId&&!r.viewedAt).length}catch(_){}}
export async function viewStudioJob(item){if(item.localPath){uni.setStorageSync(localResultsKey(),guestResults().map(r=>r.id===item.id?{...r,viewedAt:Date.now()}:r));if(item.serverId)try{await apiRequest(`/studio/jobs/${item.serverId}/view`,{method:'POST'},1);updateLocalResult(item.id,{viewSynced:true})}catch(_){}}else await apiRequest(`/studio/jobs/${item.id}/view`,{method:'POST'},1);await refreshUnread()}
export const regenerateStudioJob=id=>apiRequest(`/studio/jobs/${id}/regenerate`,{method:'POST',data:{idempotency_key:uniqueKey()}},1).then(trackStudioJob)
