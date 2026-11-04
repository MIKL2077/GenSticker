export function canDirectChatShare(){
 if(typeof wx==='undefined')return false
 try{return (wx.getEnterOptionsSync?.()||wx.getLaunchOptionsSync?.())?.apiCategory==='chatTool' && typeof wx.shareEmojiToGroup==='function'}catch(_){return false}
}
export function shareOriginalImage(path,onError){
 return new Promise(resolve=>{
  const finish=(message)=>{if(message)onError?.(message);resolve()}
  if(!path)return finish()
  if(typeof document!=='undefined')return finish('请在微信小程序中分享原图')
  const menu=()=>{
   const share=(typeof wx!=='undefined'&&wx.showShareImageMenu)||uni.showShareImageMenu
   if(typeof share!=='function')return finish('当前微信版本暂不支持分享原图，请先保存到相册再发送')
   try{share({path,needShowEntrance:false,success:()=>finish(),fail:e=>finish(/cancel/i.test(e.errMsg||'')?'':'微信暂不支持分享这张原图，请先保存到相册再发送')})}catch(_){finish('分享未完成，请重试')}
  }
  if(!canDirectChatShare())return menu()
  try{wx.shareEmojiToGroup({imagePath:path,needShowEntrance:false,success:()=>finish(),fail:e=>{
   if(/cancel/i.test(e.errMsg||''))return finish()
   if(typeof wx.shareImageToGroup==='function'){
    try{wx.shareImageToGroup({imagePath:path,needShowEntrance:false,success:()=>finish(),fail:e=>/cancel/i.test(e.errMsg||'')?finish():menu()})}catch(_){menu()}
   }else menu()
  }})}catch(_){menu()}
 })
}
export async function shareToMoments(path,caption,onError){
 if(!path)return
 const text=caption||'今天的快乐，由我亲手造梗。#GenSticker'
 await new Promise(resolve=>uni.setClipboardData({data:text,showToast:false,success:resolve,fail:resolve}))
 onError?.('配文已复制，可在微信图片菜单选择朋友圈；若未显示，请保存后到朋友圈选图')
 return shareOriginalImage(path,onError)
}
