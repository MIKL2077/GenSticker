import {notifyGeneration} from '@/services/generationNotice'
import {ref} from 'vue'
import { apiRequest } from '@/services/apiService'
import { API_BASE_URL } from '@/constants'
import { prepareImage } from '@/services/imagePreparation'
import { encodeGenerationImages } from '@/services/generationUpload'
import { downloadResult } from '@/services/recommendService'
// Keep small metadata separate from full images. Account + session generation
// prevents late preloads from repopulating another account after a switch.
let queueOwner='',queueToken='',queueItems=[],queueAt=0,queueRequest=null,queueRevision=0
const queueImages=new Map(),queueImageRequests=new Map()
const queueStorage=owner=>`gensticker.studio.queue.${owner}.v1`
function queueIdentity(){
 const session=uni.getStorageSync('gensticker.session.v1'),owner=session?.profile?.id||'',token=session?.access_token||''
 if(owner!==queueOwner||token!==queueToken){
  queueOwner=owner;queueToken=token;queueItems=[];queueAt=0;queueRequest=null;queueRevision++;queueImages.clear();queueImageRequests.clear()
  if(owner)try{const saved=uni.getStorageSync(queueStorage(owner));if(saved?.savedAt>Date.now()-7*86400000 && Array.isArray(saved.items))queueItems=saved.items.filter(j=>j.created_at>Date.now()/1000-7*86400).slice(0,100)}catch(_){}
 }
 return {owner,token,revision:queueRevision}
}
const sameQueue=identity=>{queueIdentity();return identity.revision===queueRevision}
function saveQueue(){try{uni.setStorageSync(queueStorage(queueOwner),{savedAt:Date.now(),items:queueItems})}catch(_){} }
export function cachedStudioJobs(){queueIdentity();const deleted=uni.getStorageSync(deletedLocalKey())||[];return queueItems.filter(j=>!deleted.includes(j.id)).map(j=>({...j}))}
export async function listStudioJobs({force=false,maxAge=5000}={}){
 const identity=queueIdentity();if(!identity.owner)return []
 if(queueRequest)return queueRequest
 if(!force&&queueAt&&Date.now()-queueAt<maxAge)return cachedStudioJobs()
 const request=apiRequest('/studio/jobs',{header:{Authorization:'Bearer '+identity.token}},1).then(items=>{
  if(!sameQueue(identity))return []
  queueItems=(Array.isArray(items)?items:[]).slice(0,100).map(j=>Object.fromEntries(['id','kind','status','created_at','message','viewed','can_regenerate','result_url'].map(k=>[k,j[k]])))
  queueAt=Date.now();saveQueue();return cachedStudioJobs()
 }).finally(()=>{if(sameQueue(identity)&&queueRequest===request)queueRequest=null})
 queueRequest=request;return request
}
let thumbnailActive=0
const thumbnailTasks=[]
function scheduleThumbnail(task){return new Promise((resolve,reject)=>{thumbnailTasks.push({task,resolve,reject});drainThumbnails()})}
function drainThumbnails(){while(thumbnailActive<3&&thumbnailTasks.length){const next=thumbnailTasks.shift();thumbnailActive++;Promise.resolve().then(next.task).then(next.resolve,next.reject).finally(()=>{thumbnailActive--;drainThumbnails()})}}
export async function queueThumbnail(item){
 const identity=queueIdentity(),url=item.thumbnail_url||`/studio/jobs/${item.id}/thumbnail`,key='thumb:'+item.id
 if(item.localPath)return item.localPath
 if(queueImages.has(key))return queueImages.get(key)
 if(queueImageRequests.has(key))return queueImageRequests.get(key)
 const request=scheduleThumbnail(()=>{if(!sameQueue(identity))throw Error('账号已切换');return downloadResult(url)}).then(path=>{if(!sameQueue(identity))throw Error('账号已切换');queueImages.set(key,path);while(queueImages.size>40)queueImages.delete(queueImages.keys().next().value);return path}).finally(()=>{if(sameQueue(identity)&&queueImageRequests.get(key)===request)queueImageRequests.delete(key)})
 queueImageRequests.set(key,request);return request
}
export function cachedQueueThumbnail(item){queueIdentity();return item.localPath||queueImages.get('thumb:'+item.id)||''}
export async function preloadStudioQueue(){const items=await listStudioJobs({maxAge:15000});const first=items.filter(j=>j.result_url).slice(0,4);void warmQueueThumbnails(first);return items}
export async function warmQueueThumbnails(items,onImage=()=>{},isCurrent=()=>true){
 let next=0
 await Promise.all(Array.from({length:Math.min(3,items.length)},async()=>{
  while(isCurrent()&&next<items.length){const item=items[next++];try{const path=await queueThumbnail(item);if(isCurrent())onImage(item,path)}catch(_){} }
 }))
}
function invalidateQueue(){queueIdentity();queueAt=0}

export const getStudioJob=id=>apiRequest(`/studio/jobs/${id}`,{},1)
export const listMyTemplates=()=>apiRequest('/studio/templates',{},1)
export const getMyTemplate=id=>apiRequest(`/studio/templates/${id}`,{},1)
export const createTemplate=data=>apiRequest('/studio/templates',{method:'POST',data,timeout:60000},1)
export const publishTemplate=id=>apiRequest(`/studio/templates/${id}/publish`,{method:'POST',data:{rights_attested:true}},1)
export const templateQuota=()=>apiRequest('/studio/quota',{},1)
export const deleteStudioJob=async id=>{const identity=queueIdentity();await apiRequest(`/studio/jobs/${id}`,{method:'DELETE',header:{Authorization:'Bearer '+identity.token}},1);if(sameQueue(identity)){queueItems=queueItems.filter(j=>j.id!==id);queueImages.delete('thumb:'+id);queueAt=0;saveQueue()}}
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
export function trackStudioJob(item,owner=uni.getStorageSync('gensticker.session.v1')?.profile?.id){if(owner!==uni.getStorageSync('gensticker.session.v1')?.profile?.id)return item;invalidateQueue();const pending=uni.getStorageSync(pendingKey())||[];uni.setStorageSync(pendingKey(),[...new Set([...pending,item.id])].slice(-50));return item}
export async function submitManual(template_key,paths,texts,args,options){
 const session=uni.getStorageSync('gensticker.session.v1'),owner=session?.profile?.id
 const upload=await encodeGenerationImages(paths)
 if(owner!==uni.getStorageSync('gensticker.session.v1')?.profile?.id)throw Error('账号已切换，请重新制作')
 return trackStudioJob(await apiRequest('/studio/jobs',{method:'POST',timeout:60000,timeoutMessage:'图片上传超时，请重试；已自动压缩并保留原图',header:{Authorization:`Bearer ${session.access_token}`},data:{template_key,...upload,texts,args,extract_subject:!!options.extractSubject,idempotency_key:options.idempotencyKey||uniqueKey()}},1),owner)
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
   if(finished.length){uni.setStorageSync(key,pending.filter(id=>!finished.some(j=>j.id===id)));uni.$emit('studio-completed',finished);const ready=finished.find(j=>j.status==='completed'&&['manual','livegif'].includes(j.kind));if(ready)notifyGeneration({item:ready,message:ready.kind==='livegif'?'动图生成成功！':'表情生成成功！'});else if(finished.some(j=>j.status!=='completed'))uni.showToast({title:'有个任务需要看看',icon:'none',duration:5000})}
  }catch(_){}finally{checking=false}
 }
 preloadStudioQueue().catch(()=>{});check();notificationTimer=setInterval(check,5000)
}

const localOwner=()=>uni.getStorageSync('gensticker.session.v1')?.profile?.id||'guest'
const localResultsKey=(owner=localOwner())=>`gensticker.manual.local.${owner}.v1`
export function guestResults(owner=localOwner()){const now=Date.now()/1000;return (uni.getStorageSync(localResultsKey(owner))||[]).filter(r=>now-r.created_at<7*86400).map(r=>r.status==='running'&&now-r.created_at>120?{...r,status:'failed',message:'本地制作已中断，请重新选择片段'}:r)}
export function updateLocalResult(id,changes,owner=localOwner()){if(owner!==localOwner())return;uni.setStorageSync(localResultsKey(owner),guestResults(owner).map(item=>item.id===id?{...item,...changes}:item))}
export function beginLocalLive(owner=localOwner()){const item={id:uniqueKey(),local:true,kind:'livegif',status:'running',created_at:Date.now()/1000,message:'正在这台设备制作 GIF'};uni.setStorageSync(localResultsKey(owner),[item,...guestResults(owner)].slice(0,12));return item}
export function rememberGuestMeme(path,viewed=false,kind='manual',draft=null){const item={id:uniqueKey(),local:true,kind,status:'completed',created_at:Date.now()/1000,message:'只保存在这台设备，保留近 7 天',localPath:path,...(viewed?{viewedAt:Date.now()}:{})};if(draft){try{const copy=JSON.parse(JSON.stringify(draft));if(copy.paths && uni.getFileSystemManager && uni.env?.USER_DATA_PATH){const fs=uni.getFileSystemManager();copy.paths=copy.paths.map((source,index)=>{const target=uni.env.USER_DATA_PATH+'/gensticker_draft_'+item.id+'_'+index+'.png';fs.copyFileSync(source,target);return target})}item.editDraft=copy}catch(_){}}try{uni.setStorageSync(localResultsKey(),[item,...guestResults()].slice(0,12))}catch(_){}return item}
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
export async function viewStudioJob(item){const identity=queueIdentity();if(item.localPath){uni.setStorageSync(localResultsKey(),guestResults().map(r=>r.id===item.id?{...r,viewedAt:Date.now()}:r));if(item.serverId)try{await apiRequest(`/studio/jobs/${item.serverId}/view`,{method:'POST'},1);updateLocalResult(item.id,{viewSynced:true})}catch(_){}}else await apiRequest(`/studio/jobs/${item.id}/view`,{method:'POST'},1);if(sameQueue(identity)){queueItems=queueItems.map(j=>j.id===(item.serverId||item.id)?{...j,viewed:true}:j);saveQueue()}await refreshUnread()}
export const regenerateStudioJob=id=>apiRequest(`/studio/jobs/${id}/regenerate`,{method:'POST',data:{idempotency_key:uniqueKey()}},1).then(trackStudioJob)
