<template>
 <view class="live-page">
  <view class="heading"><button class="back" @click="back">‹</button><view><text class="ui-kicker">LIVE TO LITTLE GIF</text><text class="title">把喜欢的一刻，做成动图</text></view><ui-icon name="video" tone="accent" :size="54"/></view>
  <view class="intro"><text>先选片段，再框住主角。</text><text>最长 9 秒，本地预览与制作；仅同步做好的小 GIF，长视频不用整段上传。</text></view>
  <view class="upload-options"><button class="upload-option" :disabled="busy" @click="chooseVideo"><ui-icon name="video" :size="60" tone="accent"/><text>{{source?'更换视频':'从相册选视频'}}</text></button><button class="upload-option" :disabled="busy" @click="chooseLive"><ui-icon name="image" :size="60"/><text>从相册选 Live 图</text></button></view>
  <text class="live-hint">Live 图请选择原图。若微信仅提供静态照片，请在手机相册将 Live 图“存储为视频”后选取，无需发到聊天。</text>
  <template v-if="source">
   <view class="source-info"><text>{{source.duration.toFixed(1)}} 秒素材 · 尚未上传</text><text>{{clip.duration.toFixed(1)}} 秒片段</text></view>
   <view class="timing-card"><text class="field-label">01 选取想要的时间段</text><view class="timing"><view><text>从第几秒开始</text><input type="digit" v-model="start" @blur="normalizeTime"/></view><view><text>截取几秒（最多 9 秒）</text><input type="digit" v-model="duration" @blur="normalizeTime"/></view></view>
    <slider :value="clip.start" :min="0" :max="Math.max(.1,source.duration-clip.duration)" :step=".1" :disabled="source.duration<=clip.duration || busy" activeColor="#d68d68" @changing="scrub" @change="scrub"/>
    <text class="live-hint">{{clip.start.toFixed(1)}} s — {{(clip.start+clip.duration).toFixed(1)}} s · 拖动时间条，可选长视频中间的片段</text><view class="presets"><button v-for="seconds in [3,6,9]" :key="seconds" :disabled="busy" @click="duration=String(Math.min(seconds,source.duration))">{{seconds}} 秒</button></view>
   </view>
   <view class="timing-card"><text class="field-label">02 自由框选画面</text><video-cropper v-if="!busy" :src="videoPath" :poster="sourcePoster" :width="source.width" :height="source.height" v-model="crop" :start="clip.start" :duration="clip.duration" :rotation="rotation" :flip="flip" @metadata="metadata"/><view class="direction-tools"><button :disabled="busy" @click="rotate">↻ 旋转</button><button :disabled="busy" @click="flip=!flip">⇆ 翻转</button><button :disabled="busy" @click="crop=[0,0,1,1];rotation=0;flip=false">复位</button></view></view>
   <text class="field-label">03 加一句自己的梗</text><textarea class="caption-input" :disabled="busy" v-model="caption" maxlength="100" placeholder="这一秒，建议反复欣赏" auto-height/>
   <button class="ui-primary generate" :disabled="busy || editing" :loading="busy" @click="generate">{{busy?'正在制作 '+progress+'%':'生成我的 GIF'}}</button>
   <button v-if="busy" class="cancel" @click="cancel">取消本次制作</button>
   <text class="fine-print">最长 9 秒 · 长边不超过 240 px · 成品不超过 500 KB · 先保留画质，再按需减少帧率</text>
   <button v-if="localFailed" class="ui-secondary" :disabled="busy" @click="serverGenerate">使用兼容模式（仅上传 9 秒内素材）</button>
  </template>
  <text v-if="error" class="error">{{error}}</text>
  <view v-if="result" class="success"><text>GIF 已完成 · {{Math.ceil(result.bytes.length/1024)}} KB</text><image :src="result.path" class="result-gif" mode="aspectFit"/><view class="presets"><button class="ui-secondary" @click="save">保存到相册</button><button class="ui-secondary" @click="share">分享动图</button></view><text class="live-hint">{{message}}</text><button v-if="session && !synced" class="ui-secondary" :disabled="syncing" @click="syncResult">{{syncing?'正在同步…':'同步到生成队列'}}</button><button class="ui-secondary" @click="queue">去生成队列</button></view>
  <view v-else-if="message" class="success"><text>{{message}}</text><button class="ui-secondary" @click="queue">去生成队列收动图</button></view>
  <bottom-tabs active="home"/>
 </view>
</template>
<script setup>
import {ref,watch,computed} from 'vue'
import {onUnload} from '@dcloudio/uni-app'
import {useLibrary} from '@/composables/useLibrary'
import {API_BASE_URL} from '@/constants'
import {apiRequest} from '@/services/apiService'
import {uniqueKey,trackStudioJob,rememberGuestMeme,refreshUnread,linkLocalResult} from '@/services/studioService'
import {clipWindow,albumMotion,renderLocalGif,disposeLocalMedia,localVideoInfo} from '@/services/liveGifService'
import {shareOriginalImage} from '@/services/wechatSharing'
import VideoCropper from '@/components/VideoCropper.vue'
import BottomTabs from '@/components/BottomTabs.vue'
import UiIcon from '@/components/UiIcon.vue'
const {session}=useLibrary(),source=ref(null),sourcePoster=ref(''),videoPath=ref(''),crop=ref([0,0,1,1]),start=ref('0'),duration=ref('3'),caption=ref(''),busy=ref(false),editing=ref(false),error=ref(''),message=ref(''),rotation=ref(0),flip=ref(false),progress=ref(0),result=ref(null),localFailed=ref(false),syncing=ref(false),synced=ref(false)
const clip=computed(()=>clipWindow(source.value?.duration||3,start.value,duration.value))
let epoch=0,requestKey='',motionPath='',lastGenerated=0,localItem=null
const cleanup=()=>{epoch++;if(motionPath)disposeLocalMedia(motionPath);motionPath=''}
onUnload(cleanup)
watch(()=>session.value?.profile?.id,()=>{cleanup();source.value=null;sourcePoster.value='';videoPath.value='';result.value=null;busy.value=false;syncing.value=false;message.value='';requestKey='';localItem=null})
const normalizeTime=()=>{start.value=clip.value.start.toFixed(1);duration.value=clip.value.duration.toFixed(1)}
const scrub=e=>{start.value=String(e.detail.value)}
const metadata=info=>{if(!source.value)return;if(info.width>0&&info.height>0){source.value.width=info.width;source.value.height=info.height}}
const rotate=()=>{rotation.value=(rotation.value+90)%360;crop.value=[0,0,1,1]}
const cancelled=e=>/cancel/i.test(e?.errMsg||e?.message||'')
const accept=async(file,isLive=false)=>{
 if(busy.value)return;const request=++epoch;busy.value=true;error.value='';message.value='';progress.value=0
 try{
  let path=file.tempFilePath||file.path
  if(isLive){path=await albumMotion(path);if(request!==epoch){disposeLocalMedia(path);return}if(motionPath)disposeLocalMedia(motionPath);motionPath=path}
  const info=!isLive&&file.duration>0&&file.width>0&&file.height>0?file:await localVideoInfo(path)
  if(request!==epoch)return
  if(!Number.isFinite(info.duration)||info.duration<.2)throw Error('没有读取到动态画面，请选择视频或包含动态片段的 Live 原图')
  if(info.duration>30*60)throw Error('请选择 30 分钟以内的视频，或先在相册剪出需要的一段')
  source.value={duration:info.duration,width:info.width||file.width||1,height:info.height||file.height||1,size:info.size||file.size||0};videoPath.value=path;sourcePoster.value=file.thumbTempFilePath||'';crop.value=[0,0,1,1];rotation.value=0;flip.value=false;duration.value=String(Math.min(3,info.duration));start.value='0';result.value=null;localFailed.value=false;synced.value=false;requestKey='';localItem=null
 }catch(e){if(request===epoch&&!cancelled(e))error.value=e.message||e.errMsg||'视频暂时没能打开，请换一段试试'}finally{if(request===epoch)busy.value=false}
}
const chooseVideo=()=>{if(busy.value)return;error.value='';const fail=e=>{if(!cancelled(e))error.value='相册没有打开，请检查微信相册权限'};if(typeof document==='undefined'&&typeof wx!=='undefined'&&wx.chooseMedia)wx.chooseMedia({count:1,mediaType:['video'],sourceType:['album'],sizeType:['original'],success:r=>accept(r.tempFiles[0]),fail});else uni.chooseVideo({sourceType:['album'],compressed:false,success:accept,fail})}
const chooseLive=()=>{if(busy.value)return;error.value='';const fail=e=>{if(!cancelled(e))error.value='相册没有打开，请检查微信相册权限'};if(typeof document==='undefined'&&typeof wx!=='undefined'&&wx.chooseMedia)wx.chooseMedia({count:1,mediaType:['image'],sourceType:['album'],sizeType:['original'],success:r=>accept(r.tempFiles[0],true),fail});else uni.chooseImage({count:1,sizeType:['original'],sourceType:['album'],success:r=>accept({tempFilePath:r.tempFilePaths[0]},true),fail})}
const cancel=()=>{epoch++;busy.value=false;progress.value=0;error.value='';message.value='已取消，素材仍然保留'}
const generate=async()=>{
 if(busy.value||!source.value)return
 if(Date.now()-lastGenerated<2000)return
 const request=++epoch,owner=session.value?.profile?.id;busy.value=true;error.value='';message.value='';localFailed.value=false;progress.value=0
 try{
  const output=await renderLocalGif(videoPath.value,{...clip.value,crop:crop.value,rotation:rotation.value,flip:flip.value,text:caption.value},value=>{if(request===epoch)progress.value=value},()=>request!==epoch)
  if(request!==epoch||owner!==session.value?.profile?.id){disposeLocalMedia(output.path);return}
  result.value=output;lastGenerated=Date.now();requestKey=uniqueKey();synced.value=false;localItem=rememberGuestMeme(output.path,true,'livegif');message.value='已收进本机队列，保留近 7 天';await refreshUnread()
  if(session.value)syncResult()
 }catch(e){if(request===epoch){error.value=/不支持|not support|ffmpeg|API 调试/i.test(e.message||e.errMsg||'')?'当前设备暂不能本地制作。可更新微信后重试，或使用下方兼容模式。':(e.message||'本地制作未成功，可以试试兼容模式');localFailed.value=true}}
 finally{if(request===epoch)busy.value=false}
}
const uploadFile=(path,url,formData={},token=session.value?.access_token)=>new Promise((resolve,reject)=>uni.uploadFile({url:API_BASE_URL+url,filePath:path,name:'file',formData,header:{Authorization:'Bearer '+token},timeout:60000,success:r=>{try{const data=JSON.parse(r.data);r.statusCode>=200&&r.statusCode<300?resolve(data):reject(Error(typeof data.detail==='string'?data.detail:'同步未成功，成品仍保存在本机'))}catch(e){reject(e)}},fail:reject}))
const syncResult=async()=>{
 if(syncing.value||synced.value||!session.value||!result.value)return
 const owner=session.value.profile.id,path=result.value.path,token=session.value.access_token;syncing.value=true
 try{const job=await uploadFile(path,'/studio/live/results',{idempotency_key:requestKey},token);if(owner!==session.value?.profile?.id||path!==result.value?.path)return;if(localItem)linkLocalResult(localItem.id,job.id);synced.value=true;message.value='已同步到账号队列，作品保留近 7 天'}catch(e){if(owner===session.value?.profile?.id&&path===result.value?.path)message.value='成品已保存在本机；联网后可点同步重试'}finally{syncing.value=false}
}
const serverGenerate=async()=>{
 if(busy.value||!source.value)return
 if(!session.value){error.value='兼容模式需要先在“我的”登录；也可更新微信使用本地制作';return}
 if(source.value.duration>9.1){error.value='当前设备的本地解码不可用。请先在手机相册剪出最长 9 秒的视频再选取；不会上传完整长视频。';return}
 const request=epoch,owner=session.value.profile.id;busy.value=true;error.value=''
 try{const asset=await uploadFile(videoPath.value,'/studio/live/assets');if(request!==epoch||owner!==session.value?.profile?.id)return;requestKey=uniqueKey();const job=await apiRequest('/studio/live/jobs',{method:'POST',data:{asset_id:asset.asset_id,idempotency_key:requestKey,...clip.value,crop:crop.value,text:caption.value,rotation:rotation.value,flip:flip.value}},1);if(request===epoch&&owner===session.value?.profile?.id){trackStudioJob(job,owner);message.value='兼容模式已开工，去生成队列收动图'}}catch(e){if(request===epoch)error.value=e.message||'上传失败，请重试'}finally{if(request===epoch)busy.value=false}
}
const save=async()=>{try{if(typeof document!=='undefined'){const a=document.createElement('a');a.href=result.value.path;a.download='GenSticker.gif';a.click();return}await uni.saveImageToPhotosAlbum({filePath:result.value.path});uni.showToast({title:'已保存',icon:'success'})}catch(_){error.value='请在小程序设置中允许保存到相册'}}
const share=()=>shareOriginalImage(result.value.path,title=>uni.showToast({title,icon:'none'}))
const queue=()=>uni.navigateTo({url:'/pages/queue/index'}),back=()=>uni.navigateBack()
</script>
<style scoped>
.live-page{min-height:100vh;background:var(--paper);padding:calc(110rpx + env(safe-area-inset-top)) 28rpx calc(170rpx + env(safe-area-inset-bottom))}.heading{display:flex;align-items:center;gap:18rpx;margin-bottom:30rpx}.heading>view{flex:1}.back{width:55rpx;font-size:54rpx;color:var(--ink)}.title{display:block;font-size:35rpx;font-weight:800}.intro{padding:28rpx;background:linear-gradient(130deg,#fff0d9,#f1e9d6);border:3rpx solid white;border-radius:30rpx;color:#a48f70;font-size:24rpx;line-height:1.8}.intro text{display:block}.intro text:first-child{font-size:30rpx;color:var(--ink);font-weight:750;margin-bottom:10rpx}.upload-options{display:flex;gap:18rpx;margin:30rpx 0 20rpx}.upload-option{flex:1;padding:30rpx 10rpx;background:white;border:2rpx dashed #e4d3bd;border-radius:28rpx;display:flex;align-items:center;flex-direction:column;gap:20rpx;font-size:24rpx;color:#a48b6e}.live-hint,.fine-print{display:block;font-size:21rpx;color:#a49b87;line-height:1.9}.video-preview{width:100%;height:400rpx;background:#d9e0d4;border-radius:26rpx;margin-top:28rpx}.source-info{display:flex;justify-content:space-between;font-size:23rpx;color:#9e9c83;align-items:center;padding:16rpx 0}.source-info button{font-size:24rpx;color:#c47d58}.crop-preview{width:100%;height:240rpx;border:2rpx solid white;background:#eeeadd;border-radius:20rpx}.timing{display:flex;gap:20rpx;margin:25rpx 0}.timing>view{flex:1;font-size:22rpx;color:#a39985}.timing input{height:80rpx;background:white;border-radius:18rpx;padding:0 20rpx;margin-top:10rpx;font-size:27rpx;color:var(--ink)}.field-label{display:block;font-size:25rpx;font-weight:650;margin:20rpx 0}.caption-input{width:100%;min-height:120rpx;padding:24rpx;background:white;border-radius:22rpx;font-size:26rpx;border:2rpx solid #f0e6d9}.generate{width:100%;margin:28rpx 0 20rpx}.error{display:block;background:#fff0df;padding:22rpx;border-radius:22rpx;color:#af7656;line-height:1.8;font-size:23rpx;margin:22rpx 0}.success{background:#e8efdf;padding:25rpx;border-radius:25rpx;font-size:24rpx;color:#8b9d70;line-height:1.8;margin-top:25rpx}.success button{margin-top:20rpx;width:100%}.login{margin-top:30rpx;font-size:25rpx;color:#a09078}.login button{width:100%;margin-top:20rpx}
</style>

<style scoped>
.timing-card{background:#fffaf0;padding:24rpx;border-radius:28rpx;margin:20rpx 0}.timing-card .timing{margin:14rpx 0}.presets,.direction-tools{display:flex;gap:16rpx;margin-top:16rpx}.presets button,.direction-tools button{flex:1;background:white;color:#b77f61;border-radius:18rpx;padding:14rpx 5rpx;font-size:23rpx}.result-gif{display:block;width:100%;height:380rpx;margin:20rpx 0}.cancel{font-size:24rpx;color:#a58d72;margin-bottom:20rpx}.field-label{color:var(--ink)}
</style>
