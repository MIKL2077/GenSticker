// Cleanup only our named caches/exports, never picker originals or account avatars.
const active=new Set()
const caches=new Map()
let cleanup=null
export function registerCacheFile(path,{bytes=0,onEvict=()=>{},protected:protectedFile=()=>false}={}){
 caches.delete(path);caches.set(path,{bytes,onEvict,protectedFile})
 if(caches.size>64 || [...caches.values()].reduce((sum,item)=>sum+item.bytes,0)>16*1024*1024)void trimOwnedFiles({cacheOnly:true}).catch(()=>{})
 return path
}
export const isStorageFull=error=>/storage|disk.*full|no space|quota|maximum.*size|limit.*exceed|exceed.*limit|ENOSPC/i.test(error?.errMsg||error?.message||'')
export const registerTemporary=path=>{active.add(path);return path}
export function releaseTemporary(path){if(!active.delete(path))return;if(path.startsWith('blob:'))URL.revokeObjectURL(path);else uni.getFileSystemManager?.().unlink({filePath:path,fail:()=>{}})}
export async function trimOwnedFiles(options={}){
 if(cleanup){await cleanup;return trimOwnedFiles(options)}
 cleanup=cleanOwnedFiles(options)
 try{await cleanup}finally{cleanup=null}
}
async function cleanOwnedFiles({materials=false,cacheOnly=false}={}){
 if(!uni.getFileSystemManager || !uni.env?.USER_DATA_PATH)return
 const fs=uni.getFileSystemManager(),base=uni.env.USER_DATA_PATH
 const protectedPaths=new Set(active)
 try{for(const key of uni.getStorageInfoSync?.().keys||[])if(key.startsWith('gensticker.manual.local.'))for(const item of uni.getStorageSync(key)||[])if(Date.now()/1000-item.created_at<7*86400){protectedPaths.add(item.localPath);for(const path of item.editDraft?.paths||[])protectedPaths.add(path)}}catch(_){}
 const remove=path=>new Promise(resolve=>fs.unlink({filePath:path,success:()=>resolve(true),fail:()=>resolve(false)}))
 for(const [path,item] of [...caches]){
  if(protectedPaths.has(path)||active.has(path)||item.protectedFile())continue
  if(!materials&&!cacheOnly && caches.size<=64 && [...caches.values()].reduce((sum,item)=>sum+item.bytes,0)<=16*1024*1024)break
  if(cacheOnly && caches.size<=48 && [...caches.values()].reduce((sum,item)=>sum+item.bytes,0)<=12*1024*1024)break
  if(await remove(path)){caches.delete(path);item.onEvict()}
 }
 if(cacheOnly)return
 const names=await new Promise(resolve=>{if(!fs.readdir)return resolve([]);fs.readdir({dirPath:base,success:r=>resolve(r.files||[]),fail:()=>resolve([])})})
 const files=[]
 for(const name of names){if(!/^(gensticker_(edit_|material_|draft_)|generated_meme_|meme_\d)/.test(name))continue;if(name.startsWith('gensticker_material_')&&!materials)continue;const path=base+'/'+name;if(protectedPaths.has(path))continue;const stat=await new Promise(resolve=>fs.stat({path,success:r=>resolve(r.stats),fail:()=>resolve(null)}));if(stat){const raw=stat.lastModifiedTime||0,time=raw<1e12?raw*1000:raw;if(!name.startsWith('gensticker_material_')&&time>Date.now()-60000)continue;files.push({path,bytes:stat.size,time})}}
 files.sort((a,b)=>a.time-b.time)
 // Old material files can always be fetched again; keep persistent cache well below quota.
 for(const file of files)if(!active.has(file.path)&&!caches.get(file.path)?.protectedFile()){
  if(await remove(file.path)){const cache=caches.get(file.path);caches.delete(file.path);cache?.onEvict()}
 }
}
export async function withStorageRecovery(operation){
 try{return await operation()}catch(error){
  if(!isStorageFull(error))throw error
  await trimOwnedFiles({materials:true})
  try{return await operation()}catch(retry){
   if(!isStorageFull(retry))throw retry
   const failure=Error('图片处理暂未完成，请稍后重试；原图已保留')
   failure.code='LOCAL_STORAGE_FULL';failure.cause=retry;throw failure
  }
 }
}
export async function writeOwnedFile(path,data,encoding){
 const fs=uni.getFileSystemManager(),write=()=>new Promise((resolve,reject)=>fs.writeFile({filePath:path,data,...(encoding?{encoding}:{}),success:resolve,fail:reject}))
 await withStorageRecovery(write)
 return path
}
