import {API_BASE_URL} from '@/constants'
import {writeOwnedFile} from '@/services/ownedFiles'
export async function exportWeChatImage(path){
 let image
 if(typeof document!=='undefined'){
  const blob=await(await fetch(path)).blob();if(blob.size>8*1024*1024)throw Error('原图超过 8 MB，请先缩小')
  image=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=reject;reader.readAsDataURL(blob)})
 }else{
  const fs=uni.getFileSystemManager(),stat=await new Promise((resolve,reject)=>fs.stat({path,success:r=>resolve(r.stats),fail:reject}))
  if(stat.size>8*1024*1024)throw Error('原图超过 8 MB，请先缩小')
  image=await new Promise((resolve,reject)=>fs.readFile({filePath:path,encoding:'base64',success:r=>resolve(r.data),fail:reject}))
 }
 const token=uni.getStorageSync('gensticker.session.v1')?.access_token
 const response=await uni.request({url:API_BASE_URL+'/images/wechat-export',method:'POST',data:{image},responseType:'arraybuffer',timeout:60000,header:{'Content-Type':'application/json',...(token?{Authorization:'Bearer '+token}:{})}})
 if(response.statusCode!==200)throw Error(response.statusCode===503?'导出繁忙，请稍后重试':'导出未完成，请缩小图片或缩短动画后重试')
 const bytes=new Uint8Array(response.data),gif=bytes[0]===71&&bytes[1]===73&&bytes[2]===70
 if(typeof document!=='undefined'){const url=URL.createObjectURL(new Blob([bytes],{type:gif?'image/gif':'image/png'}));const a=document.createElement('a');a.href=url;a.download='gensticker-wechat.'+(gif?'gif':'png');a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);return}
 const filePath=`${uni.env.USER_DATA_PATH}/generated_meme_wechat_${Date.now()}.${gif?'gif':'png'}`
 await writeOwnedFile(filePath,response.data)
 await new Promise((resolve,reject)=>uni.saveImageToPhotosAlbum({filePath,success:resolve,fail:reject}))
}
