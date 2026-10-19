// Cleanup only our named caches/exports, never picker originals or account avatars.
const active=new Set()
export const registerTemporary=path=>{active.add(path);return path}
export function releaseTemporary(path){if(!active.delete(path))return;if(path.startsWith('blob:'))URL.revokeObjectURL(path);else uni.getFileSystemManager?.().unlink({filePath:path,fail:()=>{}})}
export async function trimOwnedFiles({materials=false}={}){
 if(!uni.getFileSystemManager || !uni.env?.USER_DATA_PATH)return
 const fs=uni.getFileSystemManager(),base=uni.env.USER_DATA_PATH
 const protectedPaths=new Set(active)
 try{for(const key of uni.getStorageInfoSync?.().keys||[])if(key.startsWith('gensticker.manual.local.'))for(const item of uni.getStorageSync(key)||[])if(Date.now()/1000-item.created_at<7*86400)protectedPaths.add(item.localPath)}catch(_){}
 const names=await new Promise(resolve=>fs.readdir({dirPath:base,success:r=>resolve(r.files||[]),fail:()=>resolve([])}))
 const files=[]
 for(const name of names){if(!/^(gensticker_(edit_|material_)|generated_meme_|meme_\d)/.test(name))continue;if(name.startsWith('gensticker_material_')&&!materials)continue;const path=base+'/'+name;if(protectedPaths.has(path))continue;const stat=await new Promise(resolve=>fs.stat({path,success:r=>resolve(r.stats),fail:()=>resolve(null)}));if(stat)files.push({path,bytes:stat.size,time:stat.lastModifiedTime||0})}
 files.sort((a,b)=>a.time-b.time)
 // Old material files can always be fetched again; keep persistent cache well below quota.
 for(const file of files)await new Promise(resolve=>fs.unlink({filePath:file.path,success:resolve,fail:resolve}))
}
export async function writeOwnedFile(path,data,encoding){
 const fs=uni.getFileSystemManager(),write=()=>new Promise((resolve,reject)=>fs.writeFile({filePath:path,data,...(encoding?{encoding}:{}),success:resolve,fail:reject}))
 try{await write()}catch(e){if(!/storage|space|quota|limit/i.test(e.errMsg||e.message||''))throw Error('图片暂时没能保存，请重试');await trimOwnedFiles();try{await write()}catch(_){throw Error('微信存储空间不足，旧缓存已清理，请重新打开小程序再试；原图不会丢失')}}
 return path
}
