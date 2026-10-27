// Only files explicitly created/downloaded by GenSticker are owned. Picker
// originals, avatars, model weights and unknown files are never swept from tmp.
const INDEX='gensticker.files.v1',GRACE=60000
const active=new Set(),caches=new Map(),owned=new Map(),deleting=new Map(),leases=new Map()
let loaded=false,cleanup=null
const localPath=path=>{
 if(typeof path!=='string'||!path||path.includes('/../'))return false
 const base=typeof uni!=='undefined'&&uni.env?.USER_DATA_PATH
 return path.startsWith('blob:') || path.startsWith('/') || !!(base&&path.startsWith(base+'/')) || /^(wxfile:\/\/(usr\/|tmp[\/_])|http:\/\/(usr|tmp)\/)/.test(path)
}
function loadIndex(){
 if(loaded)return
 loaded=true
 try{const value=uni.getStorageSync?.(INDEX);if(value?.version===1&&Array.isArray(value.files))for(const item of value.files)if(localPath(item.path)&&!item.path.startsWith('blob:')&&['temporary','cache','result'].includes(item.kind)&&Number.isFinite(item.at))owned.set(item.path,{path:item.path,kind:item.kind,at:item.at,bytes:Number(item.bytes)||0})}catch(_){}
}
function saveIndex(){
 try{uni.setStorageSync?.(INDEX,{version:1,files:[...owned.values()].filter(item=>!item.path.startsWith('blob:'))})}catch(_){}
}
function remember(path,kind='temporary',bytes=0){
 loadIndex()
 if(localPath(path)){owned.set(path,{path,kind,at:Date.now(),bytes});saveIndex()}
 return path
}
// Include every account: switching accounts must not erase another account's
// seven-day local works or the image copies needed to reopen them for editing.
function savedPaths(){
 const paths=new Set()
 try{for(const key of uni.getStorageInfoSync?.().keys||[])if(key.startsWith('gensticker.manual.local.'))for(const item of uni.getStorageSync(key)||[])if(Date.now()/1000-item.created_at<7*86400){
  for(const path of [item.localPath,item.mediaPath,...(item.editDraft?.paths||[]),item.editDraft?.mediaPath])if(typeof path==='string')paths.add(path)
 }}catch(_){return null} // An unreadable result index is not permission to delete.
 return paths
}
function protectedFile(path,paths=savedPaths()){
 return active.has(path)||leases.has(path)||!paths||paths.has(path)||!!caches.get(path)?.protectedFile()
}
async function remove(path){
 if(!localPath(path))return false
 if(deleting.has(path))return deleting.get(path)
 if(protectedFile(path))return false
 const item=owned.get(path),cache=caches.get(path)
 const task=(async()=>{
  const ok=path.startsWith('blob:')?(URL.revokeObjectURL(path),'removed'):await new Promise(resolve=>{
   const fs=uni.getFileSystemManager?.()
   if(!fs?.unlink)return resolve(false)
   fs.unlink({filePath:path,success:()=>resolve('removed'),fail:error=>resolve(/no such file|not exist|ENOENT/i.test(error?.errMsg||'')?'missing':false)})
  })
  if(ok){if(owned.get(path)===item)owned.delete(path);if(caches.get(path)===cache){caches.delete(path);cache?.onEvict()}saveIndex()}
  return ok
 })().finally(()=>deleting.delete(path))
 deleting.set(path,task);return task
}
export function registerCacheFile(path,{bytes=0,onEvict=()=>{},protected:protectedFile=()=>false}={}){
 active.delete(path);remember(path,'cache',bytes)
 caches.delete(path);caches.set(path,{bytes,onEvict,protectedFile})
 if(caches.size>64||[...caches.values()].reduce((sum,item)=>sum+item.bytes,0)>16*1024*1024)void trimOwnedFiles({cacheOnly:true}).catch(()=>{})
 return path
}
export const isStorageFull=error=>/ENOSPC|no space(?: left)?|disk (?:is )?full|storage (?:is )?full|(?:quota|storage limit|file storage|maximum size).*(?:exceed|full)|exceed.*(?:quota|storage|maximum size)/i.test(error?.errMsg||error?.message||'')
export function registerTemporary(path){active.add(path);return remember(path)}
// Reading an existing queue/edit source never transfers ownership of it.
export function retainFile(path){
 if(!localPath(path))return()=>{}
 leases.set(path,(leases.get(path)||0)+1);let released=false
 return()=>{if(released)return;released=true;const count=leases.get(path)||0;if(count>1)leases.set(path,count-1);else leases.delete(path)}
}
export function registerOwnedResult(path){active.delete(path);return remember(path,'result')}
export function releaseTemporary(path){
 if(!active.delete(path))return
 // A completed local result may still be registered by its editor/exporter.
 // Its queue reference takes priority over that producer releasing the file.
 void remove(path).catch(()=>{})
}
export async function trimOwnedFiles(options={}){
 if(cleanup){await cleanup;return trimOwnedFiles(options)}
 cleanup=cleanOwnedFiles(options)
 try{return await cleanup}finally{cleanup=null}
}
const ownedName=name=>/^(gensticker_(edit_|material_|draft_)|generated_meme_|meme_\d)/.test(name)
function adoptReferences(){
 try{for(const key of uni.getStorageInfoSync?.().keys||[]){
  if(/^gensticker\.public-previews\./.test(key))for(const item of Object.values(uni.getStorageSync(key)||{}))if(localPath(item?.path)&&!owned.has(item.path))owned.set(item.path,{path:item.path,kind:'cache',at:Number(item.at)||0,bytes:Number(item.bytes)||0})
  if(key.startsWith('gensticker.manual.local.'))for(const item of uni.getStorageSync(key)||[])for(const path of [item.localPath,...(item.editDraft?.paths||[])])if(localPath(path)&&!owned.has(path))owned.set(path,{path,kind:'result',at:item.created_at*1000||0,bytes:0})
 }}catch(_){}
}
async function cleanOwnedFiles({materials=false,cacheOnly=false,canContinue=()=>true}={}){
 if(!uni.getFileSystemManager||!uni.env?.USER_DATA_PATH)return {removed:0,bytes:0}
 loadIndex();adoptReferences()
 const fs=uni.getFileSystemManager(),base=uni.env.USER_DATA_PATH
 if(!cacheOnly&&canContinue()){
  // Migrate older named exports. Never enumerate/delete the anonymous tmp pool:
  // it can contain album originals and files that belong to the native runtime.
  const names=await new Promise(resolve=>{if(!fs.readdir)return resolve([]);fs.readdir({dirPath:base,success:r=>resolve(r.files||[]),fail:()=>resolve([])})})
  for(const name of names){
   if(!canContinue())break
   const path=base+'/'+name
   if(!ownedName(name)||owned.has(path))continue
   const stat=await new Promise(resolve=>fs.stat({path,success:r=>resolve(r.stats),fail:()=>resolve(null)}))
   if(stat){const raw=stat.lastModifiedTime||0;owned.set(path,{path,kind:name.startsWith('gensticker_material_')?'cache':/^(generated_meme_|meme_\d|gensticker_draft_)/.test(name)?'result':'temporary',at:raw<1e12?raw*1000:raw,bytes:stat.size})}
  }
 }
 saveIndex()
 const candidates=[...owned.values()].sort((a,b)=>a.at-b.at),report={removed:0,bytes:0,missing:0}
 let cacheCount=candidates.filter(item=>item.kind==='cache').length,cacheBytes=candidates.reduce((sum,item)=>sum+(item.kind==='cache'?item.bytes:0),0),processed=0
 for(const item of candidates){
  if(!canContinue())break
  const {path,kind,at,bytes}=item
  if(protectedFile(path))continue
  if(kind==='cache'){
   if(!materials&&cacheCount<=(cacheOnly?48:64)&&cacheBytes<=(cacheOnly?12:16)*1024*1024)continue
  }else if(cacheOnly||Date.now()-at<GRACE)continue
  // Re-check after previous asynchronous removals: a queue write or editor
  // activation may have started since the sweep began.
  if(owned.get(path)!==item||protectedFile(path)||!canContinue())continue
  const result=await remove(path)
  if(result){if(result==='missing')report.missing++;else{report.removed++;report.bytes+=bytes}if(kind==='cache'){cacheCount--;cacheBytes-=bytes}}
  if(++processed%20===0)await new Promise(resolve=>setTimeout(resolve,0))
 }
 return report
}
export async function withStorageRecovery(operation){
 try{return await operation()}catch(error){
  if(!isStorageFull(error))throw error
  await trimOwnedFiles({materials:true})
  try{return await operation()}catch(retry){
   if(!isStorageFull(retry))throw retry
   const failure=Error('图片处理暂未完成，请稍后重试；原图已保留')
   failure.code='LOCAL_STORAGE_FULL';failure.cause=retry
   console.warn('GenSticker 本地文件写入重试失败', {code:failure.code,errMsg:retry?.errMsg||retry?.message||''})
   throw failure
  }
 }
}
export async function writeOwnedFile(path,data,encoding){
 const fs=uni.getFileSystemManager(),write=()=>new Promise((resolve,reject)=>fs.writeFile({filePath:path,data,...(encoding?{encoding}:{}),success:resolve,fail:reject}))
 await withStorageRecovery(write)
 remember(path,owned.get(path)?.kind||(/\/(generated_meme_|meme_\d|gensticker_draft_)/.test(path)?'result':'temporary'))
 return path
}
