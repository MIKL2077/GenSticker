<template>
 <view class="live-workshop" :class="{editing:source,'keyboard-open':keyboardHeight>0}" :style="source && keyboardHeight?{bottom:keyboardHeight+'px'}:{}">
  <template v-if="!source">
   <view class="welcome-header"><button @click="back">‹</button><text>Live / 视频转 GIF</text></view>
   <view class="welcome"><ui-icon name="video" tone="accent" :size="100"/><text class="welcome-title">选一刻，留下快乐。</text><text class="welcome-copy">先在时间轴选取片段，再裁出主角。优先在本机制作 GIF，完成后自动收进队列。</text><button class="ui-primary" :loading="picking" :disabled="picking" @click="choose(false)">从相册选视频</button><button class="ui-secondary" :disabled="picking" @click="choose(true)">从相册选动态原图</button><text class="welcome-note">最长截取 9 秒 · 自动适配 GIF 大小</text><text class="live-note">保留了视频片段的动态原图可直接转换。iPhone 系统 Live 若只返回静态照片，当前微信接口无法读取其配对视频。</text></view>
   <text v-if="error" class="welcome-error">{{error}}</text><bottom-tabs active="home"/>
  </template>
  <template v-else>
   <view class="editor-header"><button class="header-cancel" :disabled="working" @click="close">取消</button><view><text>{{phase==='trim'?'选取片段':'编辑动图'}}</text><text>{{phase==='trim'?'拖动时间轴，保留喜欢的一段':clip.duration.toFixed(1)+' 秒 · 框内画面会成为 GIF'}}</text></view><button class="header-action" :disabled="working" @click="phase==='trim'?confirmClip():generate()">{{phase==='trim'?'下一步':'生成'}}</button></view>
   <view v-if="phase==='trim'" class="trim-panel"><video-timeline :src="mediaPath" :poster="poster" :total="source.duration" v-model="clip"/><button class="confirm-clip" @click="confirmClip">选好这段，调整画面 →</button></view>
   <view v-else class="edit-panel" :class="{busy:working}">
    <view class="preview-area"><video-cropper :src="mediaPath" :poster="poster" :width="source.width" :height="source.height" v-model="crop" :start="clip.start" :duration="clip.duration" :rotation="rotation" :flip="flip" :caption="caption" v-model:captionStyle="captionStyle" :max-height="previewHeight" compact/><text class="edit-tip">拖动框移动主角 · 拖动两角自由调整宽高</text></view>
    <view class="edit-dock">
     <view v-if="tool==='crop'" class="crop-tools"><button class="crop-tool" @click="setRatio(1)">1:1</button><button class="crop-tool" @click="setRatio(.75)">3:4</button><button class="crop-tool" @click="setRatio(4/3)">4:3</button><button class="crop-tool" @click="rotation=(rotation+90)%360;crop=[0,0,1,1]">↻ 旋转</button><button class="crop-tool" @click="flip=!flip">⇆ 翻转</button><button class="crop-tool" @click="crop=[0,0,1,1];rotation=0;flip=false">复位</button></view>
     <view v-if="tool==='text'" class="text-tools"><input v-model="caption" maxlength="60" placeholder="加一句自己的梗，再拖动文字摆位置" :adjust-position="false" :hold-keyboard="true" confirm-type="done" @confirm="hideTextKeyboard"/><view class="text-palette"><button v-for="color in textColors" :key="color" :class="{chosen:captionStyle.color===color}" :style="{background:color}" :aria-label="'文字颜色 '+color" @click="captionStyle.color=color"/><button class="text-format" @click="captionStyle.bold=!captionStyle.bold">{{captionStyle.bold?'粗体':'常规'}}</button><button class="text-format" @click="cycleBackground">T 背景</button></view><view class="text-size"><text>字号</text><slider :value="Math.round(captionStyle.size*100)" :min="5" :max="25" :step="1" :block-size="16" activeColor="#f37557" @changing="captionStyle.size=$event.detail.value/100" @change="captionStyle.size=$event.detail.value/100"/><button @click="captionStyle.x=.5;captionStyle.y=.82">归位</button></view></view>
     <view class="tool-tabs"><button class="dock-tab" @click="changeClip"><ui-icon name="video" tone="accent"/><text>片段</text></button><button class="dock-tab" :class="{active:tool==='crop'}" @click="setTool('crop')"><ui-icon name="crop" tone="accent"/><text>裁剪</text></button><button class="dock-tab" :class="{active:tool==='text'}" @click="setTool('text')"><text class="text-icon">T</text><text>文字</text></button></view>
     <button class="generate-button" :disabled="working||picking" :loading="working" @click="generate">{{working?progressText:'生成我的 GIF'}}</button><text class="export-hint">保留完整片段 · 自动压缩至 500 KB 内</text>
    </view>
   </view>
   <view v-if="error" class="editor-error"><text>{{error}}</text><button @click="error=''">×</button></view>

  </template>
  <preview-modal :show="showPreview" :is-generating="working" :image="resultPath" :allow-edit="false" @close="closeResult" @save="saveResult" @share="shareResult"/>
 </view>
</template>
<script setup>
import {ref,watch,nextTick,computed} from 'vue'
import {onUnload} from '@dcloudio/uni-app'
import {useLibrary} from '@/composables/useLibrary'
import {uniqueKey,beginLocalLive,updateLocalResult,linkLocalResult,syncLocalLiveResults,getStudioJob,privateImage,viewStudioJob} from '@/services/studioService'
import {chooseAlbumVideo,nativeTrim,mediaInfo,isCancelled,uploadLiveSource,submitVideoJob,prepareLocalSource} from '@/services/videoWorkflow'
import {clipWindow,renderLocalGif,supportsLocalGif} from '@/services/liveGifService'
import VideoTimeline from '@/components/VideoTimeline.vue'
import VideoCropper from '@/components/VideoCropper.vue'
import BottomTabs from '@/components/BottomTabs.vue'
import UiIcon from '@/components/UiIcon.vue'
import PreviewModal from '@/components/PreviewModal.vue'
import {shareOriginalImage} from '@/services/wechatSharing'
const keyboardHeight=ref(0),showPreview=ref(false),resultPath=ref(''),captionStyle=ref({x:.5,y:.82,size:.1,color:'#ffffff',background:'none',bold:true})
const textColors=['#ffffff','#263f48','#ff4b55','#ffb52e','#00b578','#1890ff']
const win=uni.getWindowInfo?.()||uni.getSystemInfoSync()
const previewHeight=computed(()=>keyboardHeight.value?Math.max(80,Math.min(250,win.windowHeight-keyboardHeight.value-320)):Math.max(90,Math.min(300,win.windowHeight-(tool.value==='text'?560:430))))
const hideTextKeyboard=()=>{keyboardHeight.value=0;try{const task=uni.hideKeyboard?.();task?.catch?.(()=>{})}catch(_){}}
const setTool=value=>{if(value!=='text')hideTextKeyboard();tool.value=value}
const cycleBackground=()=>{const values=['none','dark','light','color'];captionStyle.value.background=values[(values.indexOf(captionStyle.value.background)+1)%values.length]}
const {session,loginWeChat}=useLibrary(),source=ref(null),mediaPath=ref(''),poster=ref(''),phase=ref('trim'),clip=ref({start:0,duration:3}),crop=ref([0,0,1,1]),rotation=ref(0),flip=ref(false),caption=ref(''),tool=ref('crop'),error=ref(''),working=ref(false),picking=ref(false),progressText=ref('')
let disposed=false,backgrounded=false,localJob=null,localJobKey='',originalFile=null,wasNativeTrim=false,epoch=0,asset=null,assetOwner='',requestKey='',upload=null,postedJob=null
const keyboardChanged=event=>{keyboardHeight.value=!disposed&&source.value&&tool.value==='text'&&!working.value?Math.max(0,event.height||0):0}
uni.onKeyboardHeightChange?.(keyboardChanged)
const invalidate=()=>{requestKey='';postedJob=null}
watch([clip,crop,rotation,flip,caption,captionStyle],invalidate,{deep:true})
const release=()=>{if(working.value&&localJob&&!postedJob)updateLocalResult(localJob.id,{status:'failed',message:'本地制作已中断，请重新选择片段'});epoch++;upload?.abort();upload=null}
onUnload(()=>{uni.offKeyboardHeightChange?.(keyboardChanged);disposed=true;showPreview.value=false;if(working.value)backgrounded=true;else release()})
watch(()=>session.value?.profile?.id,(id,previous)=>{if(previous&&id!==previous){release();showPreview.value=false;resultPath.value='';source.value=null;asset=null;working.value=false;error.value='';picking.value=false}})
const showEditor=async()=>{phase.value='edit';tool.value='crop';await nextTick();uni.pageScrollTo({scrollTop:0,duration:0})}
const accept=async(file,trimmed,preserveText=false)=>{
 const info=await mediaInfo(file)
 if(!Number.isFinite(info.duration)||info.duration<.2||!info.width||!info.height)throw Error('没有读取到动态画面，请换一个视频')
 if(info.duration>1800)throw Error('请选择 30 分钟以内的视频')
 if((info.size||file.size)>60*1024*1024)throw Error('视频超过 60 MB，请在系统时间轴先选出 9 秒内片段')
 source.value=info;mediaPath.value=file.tempFilePath;poster.value=file.thumbTempFilePath||'';clip.value=clipWindow(info.duration,0,Math.min(trimmed?9:3,info.duration));crop.value=[0,0,1,1];rotation.value=0;flip.value=false;if(!preserveText){caption.value='';captionStyle.value={x:.5,y:.82,size:.1,color:'#ffffff',background:'none',bold:true}}asset=null;assetOwner='';invalidate();wasNativeTrim=trimmed
 if(trimmed)await showEditor();else phase.value='trim'
}
const choose=async live=>{
 if(picking.value||working.value)return;picking.value=true;error.value='';const request=++epoch
 try{const file=await chooseAlbumVideo(live);if(request!==epoch)return;originalFile=file;const selected=await nativeTrim(file);if(request!==epoch)return;await accept(selected.file,selected.trimmed)}catch(e){if(request===epoch&&!isCancelled(e)){error.value=e.message||e.errMsg||'相册没有打开，请检查权限'}}finally{if(request===epoch)picking.value=false}
}
const confirmClip=()=>{clip.value=clipWindow(source.value.duration,clip.value.start,clip.value.duration);showEditor()}
const changeClip=async()=>{
 if(working.value||picking.value)return
 hideTextKeyboard()
 if(wasNativeTrim&&originalFile){picking.value=true;const request=epoch;try{const selected=await nativeTrim(originalFile);if(request===epoch)await accept(selected.file,selected.trimmed,true)}catch(e){if(!isCancelled(e))error.value=e.message||'视频编辑器没有打开'}finally{picking.value=false}}
 else phase.value='trim'
}
const setRatio=ratio=>{const aspect=rotation.value%180?source.value.height/source.value.width:source.value.width/source.value.height;let w=.85,h=w*aspect/ratio;if(h>.9){h=.9;w=h*ratio/aspect}crop.value=[(1-w)/2,(1-h)/2,w,h]}
const generate=async()=>{
 if(working.value||picking.value||!source.value)return
 hideTextKeyboard()
 const activeRequest=epoch;let pendingLocal
 working.value=true;showPreview.value=true;resultPath.value='';backgrounded=false;error.value='';progressText.value='正在准备任务…'
 try{
  if(!session.value)await loginWeChat()
  const request=epoch,owner=session.value?.profile?.id,token=session.value?.access_token
  if(!owner||!token)throw Error('登录尚未完成，请重试')
  if(postedJob){if(postedJob.resultPath){resultPath.value=postedJob.resultPath;return}showPreview.value=false;uni.showToast({title:'任务仍在队列中继续制作',icon:'none'});return}
  if(!requestKey)requestKey=uniqueKey()
  const key=requestKey,options={...clip.value,crop:crop.value,rotation:rotation.value,flip:flip.value,text:caption.value,caption_style:{...captionStyle.value}}
  const alive=()=>request===epoch&&owner===session.value?.profile?.id
  if(!localJob||localJobKey!==requestKey){localJob=beginLocalLive(owner);localJobKey=requestKey}else updateLocalResult(localJob.id,{status:'running',message:'正在这台设备制作 GIF'},owner)
  pendingLocal=localJob
  progressText.value='正在本机准备动态画面…'
  const preparedSource=await prepareLocalSource(mediaPath.value,source.value,crop.value)
  if(!alive())return
  if(supportsLocalGif()){
   if(!preparedSource.nativeUnavailable)try{
    const result=await renderLocalGif(preparedSource.path,{...options,sequential:preparedSource.sequential},value=>{if(alive())progressText.value='本机制作 '+value+'%'},()=>!alive())
    if(!alive())return
    updateLocalResult(localJob.id,{status:'completed',localPath:result.path,message:'本机已完成，可保存分享；正在同步'},owner)
    postedJob={...localJob,resultPath:result.path};finishResult(result.path,{id:localJob.id,localPath:result.path});syncLocalLiveResults().catch(()=>{});return
   }catch(e){if(!alive())return;progressText.value='正在切换后台制作…'}
  }
  if(!alive())return
  if(!asset||assetOwner!==owner){
   progressText.value='正在上传压缩片段…';upload=uploadLiveSource(preparedSource.path,token,value=>{if(alive())progressText.value='上传片段 '+value+'%'})
   const prepared=await upload.promise;upload=null;if(!alive())return;asset=prepared;assetOwner=owner
  }
  progressText.value='正在加入生成队列…'
  const job=await submitVideoJob(asset,options,key,token)
  if(request!==epoch||owner!==session.value?.profile?.id)return
  linkLocalResult(localJob.id,job.id,owner);updateLocalResult(localJob.id,{status:'queued',message:'后台正在制作'},owner);postedJob=job
  if(backgrounded||disposed)return
  let completed=job
  for(let count=0;count<120&&['queued','running'].includes(completed.status);count++){
   await new Promise(resolve=>setTimeout(resolve,1000));if(!alive()||backgrounded||disposed)return;completed=await getStudioJob(job.id)
  }
  if(!alive()||backgrounded||disposed)return
  if(completed.status==='completed'){const path=await privateImage(completed.result_url);if(!alive())return;postedJob={...job,resultPath:path};finishResult(path,completed)}
  else if(['queued','running'].includes(completed.status)){showPreview.value=false;uni.showToast({title:'任务继续制作，可到我的生成队列查看',icon:'none'})}
  else{postedJob=null;requestKey='';throw Error(completed.message||'这段视频暂未生成，请重试')}
 }catch(e){if(activeRequest!==epoch)return;showPreview.value=false;if(postedJob){if(!disposed)uni.showToast({title:'任务已在队列，稍后到我的查看',icon:'none'});return}if(pendingLocal)updateLocalResult(pendingLocal.id,{status:'failed',message:'提交未完成，返回编辑页可重试'});error.value=isCancelled(e)?'上传已取消，编辑内容已保留':(/timeout/i.test(e.errMsg||e.message||'')?'上传连接超时，编辑已保留；切换网络后点击生成重试':(e.message||e.errMsg||'任务没能提交，编辑内容已保留，请重试'))}
 finally{if(activeRequest===epoch)working.value=false}
}
const finishResult=(path,item)=>{
 if(!backgrounded&&!disposed){resultPath.value=path;showPreview.value=true;viewStudioJob(item).catch(()=>{})}
 else if(!disposed)uni.showToast({title:'动图已完成，去生成队列收图',icon:'none'})
}
const closeResult=()=>{if(working.value){backgrounded=true;uni.showToast({title:'已放入生成队列，继续制作中',icon:'none'})}showPreview.value=false}
const saveResult=async()=>{if(!resultPath.value)return;try{if(typeof document!=='undefined'){const link=document.createElement('a');link.href=resultPath.value;link.download='GenSticker.gif';link.click()}else await uni.saveImageToPhotosAlbum({filePath:resultPath.value});uni.showToast({title:'已保存',icon:'success'})}catch(_){uni.showToast({title:'请在设置中允许保存到相册',icon:'none'})}}
const shareResult=()=>shareOriginalImage(resultPath.value,title=>uni.showToast({title,icon:'none'}))
const close=()=>{if(working.value)return;hideTextKeyboard();release();source.value=null;asset=null;originalFile=null;error.value='';invalidate()}
const back=()=>uni.navigateBack()
</script>
<style scoped>
.live-workshop{min-height:100vh;background:var(--paper);padding:calc(85rpx + env(safe-area-inset-top)) 28rpx calc(165rpx + env(safe-area-inset-bottom))}.welcome-header{display:flex;align-items:center;gap:20rpx;font-size:30rpx;font-weight:750;color:var(--ink)}.welcome-header button{font-size:56rpx;width:48rpx}.welcome{display:flex;align-items:center;flex-direction:column;gap:28rpx;padding:70rpx 20rpx 20rpx}.welcome-title{font-size:40rpx;font-weight:800;color:var(--ink)}.welcome-copy{font-size:26rpx;line-height:1.9;color:#9e937c;text-align:center}.welcome button{width:100%;font-size:28rpx}.welcome-note,.live-note{font-size:22rpx;color:#a99980;text-align:center;line-height:1.8}.live-note{font-size:21rpx}.welcome-error{display:block;background:#ffe9d7;color:#a56d4f;border-radius:20rpx;padding:22rpx;font-size:24rpx;line-height:1.7}.editing{min-height:0;position:fixed;inset:0;z-index:1800;background:var(--paper);padding:calc(env(safe-area-inset-top) + 45px) 18px max(12px,env(safe-area-inset-bottom));display:flex;flex-direction:column;overflow:hidden}.editor-header{display:flex;align-items:center;justify-content:space-between;gap:14rpx;flex-shrink:0;height:65px}.editor-header>button{color:var(--ink);font-size:25rpx;min-width:78rpx;padding:12rpx 8rpx}.editor-header>view{flex:1;text-align:center;color:var(--ink);min-width:0}.editor-header>view text{display:block;font-size:27rpx;font-weight:700}.editor-header>view text:last-child{font-size:20rpx;color:var(--muted);font-weight:400;margin-top:8rpx}.editor-header .header-action{background:var(--accent);color:#fff;border-radius:32rpx;font-weight:750}.trim-panel{flex:1;min-height:0;display:flex;flex-direction:column;justify-content:space-between;padding-bottom:10px}.confirm-clip{width:100%;padding:23rpx;background:var(--accent);color:#fff;font-size:27rpx;border-radius:25rpx;margin-top:22rpx;font-weight:700}.edit-panel{flex:1;min-height:0;display:flex;flex-direction:column;justify-content:space-between}.preview-area{flex:1;min-height:0;overflow:hidden;display:flex;flex-direction:column;justify-content:center}.edit-tip{display:block;text-align:center;font-size:21rpx;color:var(--muted);margin:5rpx 0 15rpx}.edit-dock{flex-shrink:0;background:#fff;border:1px solid var(--line);box-shadow:0 5rpx 0 #efe5d9;border-radius:26px;padding:14px 12px 8px}.crop-tools{display:flex;gap:4rpx;align-items:center;justify-content:space-between;margin-bottom:12rpx}.crop-tools button{font-size:21rpx;color:var(--ink);padding:12rpx 6rpx}.tool-tabs{display:flex;justify-content:center;gap:38rpx;margin-bottom:16rpx}.tool-tabs button{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8rpx;width:100rpx;color:var(--muted);font-size:20rpx;padding:12rpx 0;border-radius:22rpx}.tool-tabs button.active{background:var(--peach);color:var(--accent-dark)}.text-icon{height:32rpx;line-height:32rpx;font-size:34rpx;font-weight:800;color:var(--accent-dark)}.generate-button{display:block;width:100%;font-size:27rpx;font-weight:750;background:linear-gradient(150deg,#ffa183,#f37557);box-shadow:0 5rpx 0 #c75f43;color:#fff;padding:24rpx 10rpx;border-radius:20rpx}.export-hint{display:block;text-align:center;color:var(--muted);font-size:19rpx;margin-top:12rpx}.text-tools{padding:6rpx 4rpx 18rpx}.text-tools input{background:#fff8e9;color:#253f35;border-radius:15rpx;font-size:26rpx;padding:18rpx;height:78rpx}.editor-error{position:absolute;bottom:calc(200px + env(safe-area-inset-bottom));left:20px;right:20px;background:#ffe8cf;color:#925e3b;border-radius:18rpx;padding:22rpx;display:flex;align-items:center;gap:10rpx;font-size:23rpx;line-height:1.6;z-index:2000}.editor-error text{flex:1}.editor-error button{color:#925e3b;font-size:35rpx}.working-mask{position:absolute;inset:0;background:#fffaf5f5;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:26rpx;color:var(--ink);z-index:2100;font-size:28rpx}.working-mask text:last-child{font-size:23rpx;color:var(--muted)}.working-ring{width:50rpx;height:50rpx;border:5rpx solid var(--line);border-top-color:var(--accent);border-radius:50%;animation:ui-spin .8s linear infinite}button[disabled]{opacity:.55}
.header-cancel{background:var(--peach);color:var(--accent-dark);font-size:24rpx;border-radius:28rpx;line-height:1.5;padding:14rpx 18rpx}.crop-tool{background:transparent;color:var(--ink);font-size:21rpx;padding:12rpx 6rpx;line-height:1.5}.dock-tab{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8rpx;width:100rpx;color:var(--muted);background:transparent;font-size:20rpx;padding:12rpx 0;border-radius:22rpx;line-height:1.4}.dock-tab.active{background:var(--peach);color:var(--accent-dark)}
.busy{pointer-events:none}.text-palette{display:flex;align-items:center;justify-content:space-between;gap:8rpx;margin-top:16rpx}.text-palette>button{width:35rpx;height:35rpx;border-radius:50%;border:2rpx solid #dccfc1;padding:0;flex-shrink:0}.text-palette>button.chosen{outline:4rpx solid #ffb292;outline-offset:3rpx}.text-palette .text-format{width:auto;height:auto;border:0;border-radius:10rpx;font-size:20rpx;padding:5rpx;color:var(--ink);background:var(--peach)}.text-size{display:flex;align-items:center;gap:8rpx;font-size:21rpx;color:var(--muted)}.text-size slider{flex:1;margin:14rpx 5rpx}.text-size button{padding:4rpx 10rpx;font-size:21rpx;color:var(--accent-dark)}
.keyboard-open .tool-tabs,.keyboard-open .generate-button,.keyboard-open .export-hint,.keyboard-open .text-size,.keyboard-open .edit-tip{display:none}.keyboard-open .edit-dock{padding-bottom:14px}
</style>
