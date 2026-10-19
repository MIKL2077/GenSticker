<template>
 <view class="live-workshop" :class="{editing:source}">
  <template v-if="!source">
   <view class="welcome-header"><button @click="back">‹</button><text>Live / 视频转 GIF</text></view>
   <view class="welcome"><ui-icon name="video" tone="accent" :size="100"/><text class="welcome-title">选一刻，留下快乐。</text><text class="welcome-copy">先在时间轴选取片段，再裁出主角。生成后会自动收进队列，离开页面也能继续制作。</text><button class="ui-primary" :loading="picking" :disabled="picking" @click="choose(false)">从相册选视频</button><button class="ui-secondary" :disabled="picking" @click="choose(true)">从相册选 Live / 动态图</button><text class="welcome-note">最长截取 9 秒 · 自动适配 GIF 大小</text><text class="live-note">能读取到 Live 动态片段时会自动转换；若微信仅提供静态照片，需要从相册选择其视频版本。</text></view>
   <text v-if="error" class="welcome-error">{{error}}</text><bottom-tabs active="home"/>
  </template>
  <template v-else>
   <view class="editor-header"><button class="header-cancel" :disabled="working" @click="close">取消</button><view><text>{{phase==='trim'?'选取片段':'编辑动图'}}</text><text>{{phase==='trim'?'拖动时间轴，保留喜欢的一段':clip.duration.toFixed(1)+' 秒 · 框内画面会成为 GIF'}}</text></view><button class="header-action" :disabled="working" @click="phase==='trim'?confirmClip():generate()">{{phase==='trim'?'下一步':'生成'}}</button></view>
   <view v-if="phase==='trim'" class="trim-panel"><video-timeline :src="mediaPath" :poster="poster" :total="source.duration" v-model="clip"/><button class="confirm-clip" @click="confirmClip">选好这段，调整画面 →</button></view>
   <view v-else class="edit-panel">
    <view class="preview-area"><video-cropper :src="mediaPath" :poster="poster" :width="source.width" :height="source.height" v-model="crop" :start="clip.start" :duration="clip.duration" :rotation="rotation" :flip="flip" :caption="caption" compact/><text class="edit-tip">拖动框移动主角 · 拖动两角自由调整宽高</text></view>
    <view class="edit-dock">
     <view v-if="tool==='crop'" class="crop-tools"><button class="crop-tool" @click="setRatio(1)">1:1</button><button class="crop-tool" @click="setRatio(.75)">3:4</button><button class="crop-tool" @click="setRatio(4/3)">4:3</button><button class="crop-tool" @click="rotation=(rotation+90)%360;crop=[0,0,1,1]">↻ 旋转</button><button class="crop-tool" @click="flip=!flip">⇆ 翻转</button><button class="crop-tool" @click="crop=[0,0,1,1];rotation=0;flip=false">复位</button></view>
     <view v-if="tool==='text'" class="text-tools"><input v-model="caption" maxlength="60" placeholder="加一句自己的梗" :adjust-position="true" confirm-type="done"/></view>
     <view class="tool-tabs"><button class="dock-tab" @click="changeClip"><ui-icon name="video" tone="white"/><text>片段</text></button><button class="dock-tab" :class="{active:tool==='crop'}" @click="tool='crop'"><ui-icon name="crop" tone="white"/><text>裁剪</text></button><button class="dock-tab" :class="{active:tool==='text'}" @click="tool='text'"><text class="text-icon">T</text><text>文字</text></button></view>
     <button class="generate-button" :disabled="working||picking" :loading="working" @click="generate">{{working?progressText:'开始生成，加入队列'}}</button><text class="export-hint">保留完整片段 · 自动压缩至 500 KB 内</text>
    </view>
   </view>
   <view v-if="error" class="editor-error"><text>{{error}}</text><button @click="error=''">×</button></view>
   <view v-if="working" class="working-mask"><view class="working-ring"/><text>{{progressText}}</text><text>提交成功后会自动打开生成队列</text></view>
  </template>
 </view>
</template>
<script setup>
import {ref,watch,nextTick} from 'vue'
import {onUnload} from '@dcloudio/uni-app'
import {useLibrary} from '@/composables/useLibrary'
import {uniqueKey} from '@/services/studioService'
import {chooseAlbumVideo,nativeTrim,mediaInfo,isCancelled,uploadLiveSource,submitVideoJob} from '@/services/videoWorkflow'
import {clipWindow} from '@/services/liveGifService'
import VideoTimeline from '@/components/VideoTimeline.vue'
import VideoCropper from '@/components/VideoCropper.vue'
import BottomTabs from '@/components/BottomTabs.vue'
import UiIcon from '@/components/UiIcon.vue'
const {session,loginWeChat}=useLibrary(),source=ref(null),mediaPath=ref(''),poster=ref(''),phase=ref('trim'),clip=ref({start:0,duration:3}),crop=ref([0,0,1,1]),rotation=ref(0),flip=ref(false),caption=ref(''),tool=ref('crop'),error=ref(''),working=ref(false),picking=ref(false),progressText=ref('')
let originalFile=null,wasNativeTrim=false,epoch=0,asset=null,assetOwner='',requestKey='',upload=null,postedJob=null
const invalidate=()=>{requestKey='';postedJob=null}
watch([clip,crop,rotation,flip,caption],invalidate,{deep:true})
const release=()=>{epoch++;upload?.abort();upload=null}
onUnload(release)
watch(()=>session.value?.profile?.id,(id,previous)=>{if(previous&&id!==previous){release();source.value=null;asset=null;working.value=false;error.value='';picking.value=false}})
const showEditor=async()=>{phase.value='edit';tool.value='crop';await nextTick();uni.pageScrollTo({scrollTop:0,duration:0})}
const accept=async(file,trimmed)=>{
 const info=await mediaInfo(file)
 if(!Number.isFinite(info.duration)||info.duration<.2||!info.width||!info.height)throw Error('没有读取到动态画面，请换一个视频')
 if(info.duration>1800)throw Error('请选择 30 分钟以内的视频')
 if((info.size||file.size)>60*1024*1024)throw Error('视频超过 60 MB，请在系统时间轴先选出 9 秒内片段')
 source.value=info;mediaPath.value=file.tempFilePath;poster.value=file.thumbTempFilePath||'';clip.value=clipWindow(info.duration,0,Math.min(trimmed?9:3,info.duration));crop.value=[0,0,1,1];rotation.value=0;flip.value=false;asset=null;assetOwner='';invalidate();wasNativeTrim=trimmed
 if(trimmed)await showEditor();else phase.value='trim'
}
const choose=async live=>{
 if(picking.value||working.value)return;picking.value=true;error.value='';const request=++epoch
 try{const file=await chooseAlbumVideo(live);if(request!==epoch)return;originalFile=file;const selected=await nativeTrim(file);if(request!==epoch)return;await accept(selected.file,selected.trimmed)}catch(e){if(request===epoch&&!isCancelled(e))error.value=e.message||e.errMsg||'相册没有打开，请检查权限'}finally{if(request===epoch)picking.value=false}
}
const confirmClip=()=>{clip.value=clipWindow(source.value.duration,clip.value.start,clip.value.duration);showEditor()}
const changeClip=async()=>{
 if(working.value||picking.value)return
 if(wasNativeTrim&&originalFile){picking.value=true;const request=epoch;try{const selected=await nativeTrim(originalFile);if(request===epoch)await accept(selected.file,selected.trimmed)}catch(e){if(!isCancelled(e))error.value=e.message||'视频编辑器没有打开'}finally{picking.value=false}}
 else phase.value='trim'
}
const setRatio=ratio=>{const aspect=rotation.value%180?source.value.height/source.value.width:source.value.width/source.value.height;let w=.85,h=w*aspect/ratio;if(h>.9){h=.9;w=h*ratio/aspect}crop.value=[(1-w)/2,(1-h)/2,w,h]}
const generate=async()=>{
 if(working.value||picking.value||!source.value)return
 working.value=true;error.value='';progressText.value='正在准备任务…'
 try{
  if(!session.value)await loginWeChat()
  const request=epoch,owner=session.value?.profile?.id,token=session.value?.access_token
  if(!owner||!token)throw Error('登录尚未完成，请重试')
  if(postedJob){uni.navigateTo({url:'/pages/queue/index'});return}
  if(!requestKey)requestKey=uniqueKey()
  if(!asset||assetOwner!==owner){
   progressText.value='正在上传所选片段…';upload=uploadLiveSource(mediaPath.value,token,value=>{if(request===epoch)progressText.value='上传片段 '+value+'%'})
   const prepared=await upload.promise;upload=null;if(request!==epoch||owner!==session.value?.profile?.id)return;asset=prepared;assetOwner=owner
  }
  progressText.value='正在加入生成队列…'
  const job=await submitVideoJob(asset,{...clip.value,crop:crop.value,rotation:rotation.value,flip:flip.value,text:caption.value},requestKey,token)
  if(request!==epoch||owner!==session.value?.profile?.id)return
  postedJob=job;uni.showToast({title:'已加入队列，后台继续制作',icon:'none'});uni.navigateTo({url:'/pages/queue/index'})
 }catch(e){error.value=isCancelled(e)?'上传已取消，编辑内容已保留':(e.message||e.errMsg||'任务没能提交，编辑内容已保留，请重试')}
 finally{working.value=false}
}
const close=()=>{if(working.value)return;release();source.value=null;asset=null;originalFile=null;error.value='';invalidate()}
const back=()=>uni.navigateBack()
</script>
<style scoped>
.live-workshop{min-height:100vh;background:var(--paper);padding:calc(85rpx + env(safe-area-inset-top)) 28rpx calc(165rpx + env(safe-area-inset-bottom))}.welcome-header{display:flex;align-items:center;gap:20rpx;font-size:30rpx;font-weight:750;color:var(--ink)}.welcome-header button{font-size:56rpx;width:48rpx}.welcome{display:flex;align-items:center;flex-direction:column;gap:28rpx;padding:70rpx 20rpx 20rpx}.welcome-title{font-size:40rpx;font-weight:800;color:var(--ink)}.welcome-copy{font-size:26rpx;line-height:1.9;color:#9e937c;text-align:center}.welcome button{width:100%;font-size:28rpx}.welcome-note,.live-note{font-size:22rpx;color:#a99980;text-align:center;line-height:1.8}.live-note{font-size:21rpx}.welcome-error{display:block;background:#ffe9d7;color:#a56d4f;border-radius:20rpx;padding:22rpx;font-size:24rpx;line-height:1.7}.editing{position:fixed;inset:0;z-index:1800;background:#111613;padding:calc(env(safe-area-inset-top) + 45px) 18px max(12px,env(safe-area-inset-bottom));display:flex;flex-direction:column;overflow:hidden}.editor-header{display:flex;align-items:center;justify-content:space-between;gap:14rpx;flex-shrink:0;height:65px}.editor-header>button{color:#f4eee3;font-size:25rpx;min-width:78rpx;padding:12rpx 8rpx}.editor-header>view{flex:1;text-align:center;color:white;min-width:0}.editor-header>view text{display:block;font-size:27rpx;font-weight:700}.editor-header>view text:last-child{font-size:20rpx;color:#a9b5aa;font-weight:400;margin-top:8rpx}.editor-header .header-action{background:#ffd583;color:#263d31;border-radius:32rpx;font-weight:750}.trim-panel{flex:1;min-height:0;display:flex;flex-direction:column;justify-content:space-between;padding-bottom:10px}.confirm-clip{width:100%;padding:23rpx;background:#ffd583;color:#253e30;font-size:27rpx;border-radius:25rpx;margin-top:22rpx;font-weight:700}.edit-panel{flex:1;min-height:0;display:flex;flex-direction:column;justify-content:space-between}.preview-area{flex:1;min-height:0;overflow:hidden;display:flex;flex-direction:column;justify-content:center}.edit-tip{display:block;text-align:center;font-size:21rpx;color:#a0b09f;margin:5rpx 0 15rpx}.edit-dock{flex-shrink:0;background:#1e2922;border:1px solid #ffffff15;border-radius:26px;padding:14px 12px 8px}.crop-tools{display:flex;gap:4rpx;align-items:center;justify-content:space-between;margin-bottom:12rpx}.crop-tools button{font-size:21rpx;color:#e4dccb;padding:12rpx 6rpx}.tool-tabs{display:flex;justify-content:center;gap:38rpx;margin-bottom:16rpx}.tool-tabs button{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8rpx;width:100rpx;color:#bdc5b9;font-size:20rpx;padding:12rpx 0;border-radius:22rpx}.tool-tabs button.active{background:#ffffff12;color:#ffda8e}.text-icon{height:32rpx;line-height:32rpx;font-size:34rpx;font-weight:800;color:white}.generate-button{display:block;width:100%;font-size:27rpx;font-weight:750;background:#ffd583;color:#253d2f;padding:24rpx 10rpx;border-radius:20rpx}.export-hint{display:block;text-align:center;color:#a6b19e;font-size:19rpx;margin-top:12rpx}.text-tools{padding:6rpx 4rpx 18rpx}.text-tools input{background:#fff8e9;color:#253f35;border-radius:15rpx;font-size:26rpx;padding:18rpx;height:78rpx}.editor-error{position:absolute;bottom:calc(200px + env(safe-area-inset-bottom));left:20px;right:20px;background:#ffe8cf;color:#925e3b;border-radius:18rpx;padding:22rpx;display:flex;align-items:center;gap:10rpx;font-size:23rpx;line-height:1.6;z-index:2000}.editor-error text{flex:1}.editor-error button{color:#925e3b;font-size:35rpx}.working-mask{position:absolute;inset:0;background:#0d1711e8;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:26rpx;color:#fff0cf;z-index:2100;font-size:28rpx}.working-mask text:last-child{font-size:23rpx;color:#a6b29c}.working-ring{width:50rpx;height:50rpx;border:5rpx solid #566347;border-top-color:#ffd583;border-radius:50%;animation:ui-spin .8s linear infinite}button[disabled]{opacity:.55}
.header-cancel{background:#ffffff12;color:#f9edd5;font-size:24rpx;border-radius:28rpx;line-height:1.5;padding:14rpx 18rpx}.crop-tool{background:transparent;color:#e4dccb;font-size:21rpx;padding:12rpx 6rpx;line-height:1.5}.dock-tab{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8rpx;width:100rpx;color:#bdc5b9;background:transparent;font-size:20rpx;padding:12rpx 0;border-radius:22rpx;line-height:1.4}.dock-tab.active{background:#ffffff12;color:#ffda8e}
</style>
