import {API_BASE_URL} from '@/constants'
import {downloadResult} from '@/services/recommendService'
import {registerTemporary,releaseTemporary,registerCacheFile} from '@/services/ownedFiles'

let latestExample=''

// Full examples are requested only after the user's tap, never while paging.
// A private template keeps its authenticated preview route.
export async function loadTemplateExample(detail,isCurrent=()=>true){
 if(!detail?.key)throw Error('请先选择模板')
 const check=()=>{if(!isCurrent())throw Error('示例分享已取消')}
 check()
 const url=detail.ownPreview||`/memes/${encodeURIComponent(detail.key)}/example?v=${encodeURIComponent(detail.version||1)}`
 if(typeof document!=='undefined')return API_BASE_URL+url
 let path=await downloadResult(url),copy=''
 try{
  check()
  const fs=uni.getFileSystemManager()
  const info=await new Promise((resolve,reject)=>fs.stat({path,success:r=>resolve(r.stats),fail:reject}))
  if(!info.size||info.size>12*1024*1024)throw Error('示例图片过大，暂时无法分享')
  const header=await new Promise((resolve,reject)=>fs.readFile({filePath:path,position:0,length:12,success:r=>resolve(new Uint8Array(r.data)),fail:reject}))
  const extension=header[0]===71&&header[1]===73&&header[2]===70?'gif':header[0]===137&&header[1]===80&&header[2]===78?'png':header[0]===255&&header[1]===216?'jpg':''
  if(!extension)throw Error('示例图片未完整送达，请重试')
  check()
  copy=registerTemporary(`${uni.env.USER_DATA_PATH}/gensticker_edit_example_${Date.now()}_${Math.random().toString(36).slice(2)}.${extension}`)
  await new Promise((resolve,reject)=>fs.copyFile({srcPath:path,destPath:copy,success:resolve,fail:reject}))
  check()
  // Native menu success can precede sending the image. Keep the latest file
  // protected in the bounded cache rather than deleting it at that callback.
  latestExample=copy
  registerCacheFile(copy,{bytes:info.size,protected:()=>latestExample===copy})
  return copy
 }catch(error){if(copy)releaseTemporary(copy);throw error}
 finally{releaseTemporary(path)}
}
