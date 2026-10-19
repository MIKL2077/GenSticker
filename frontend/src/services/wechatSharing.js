export function canDirectChatShare(){
 if(typeof wx==='undefined')return false
 try{return (wx.getEnterOptionsSync?.()||wx.getLaunchOptionsSync?.())?.apiCategory==='chatTool' && typeof wx.shareEmojiToGroup==='function'}catch(_){return false}
}
export function shareOriginalImage(path,onError){
 if(!path)return
 if(typeof document!=='undefined'){onError?.('请在微信小程序中分享原图');return}
 const menu=()=>{const share=(typeof wx!=='undefined'&&wx.showShareImageMenu)||uni.showShareImageMenu;if(typeof share!=='function'){onError?.('当前微信版本暂不支持分享原图，请先保存到相册再发送');return}share({path,needShowEntrance:false,fail:e=>{if(!/cancel/i.test(e.errMsg||''))onError?.('微信暂不支持分享这张原图，请先保存到相册再发送')}})}
 if(!canDirectChatShare())return menu()
 wx.shareEmojiToGroup({imagePath:path,needShowEntrance:false,fail:e=>{
  if(/cancel/i.test(e.errMsg||''))return
  if(typeof wx.shareImageToGroup==='function')wx.shareImageToGroup({imagePath:path,needShowEntrance:false,fail:e=>{if(!/cancel/i.test(e.errMsg||''))menu()}})
  else menu()
 }})
}
export async function shareToMoments(path,caption,onError){
 if(!path)return
 const text=caption||'今天的快乐，由我亲手造梗。#GenSticker'
 await new Promise(resolve=>uni.setClipboardData({data:text,showToast:false,success:resolve,fail:resolve}))
 onError?.('配文已复制，可在微信图片菜单选择朋友圈；若未显示，请保存后到朋友圈选图')
 return shareOriginalImage(path,onError)
}
