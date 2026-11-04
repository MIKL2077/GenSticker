<template>
 <view class="queue-page" :class="{'scene-enter':visible,'is-selecting':selecting}">
  <view class="heading"><button class="back" @click="back">‹</button><view><text class="ui-kicker">YOUR MEME WORKSHOP</text><text class="title">生成队列 <text v-if="unreadCount" class="unread-total">{{unreadCount}} 未查看</text></text></view><ui-icon name="queue" tone="accent" :size="52"/></view>
  <view class="intro"><text>小窝继续做，你先去玩～</text><text>点开整行领取成品，左滑可删除。作品和再次制作所需素材保留近 7 天。</text></view>
  <view v-if="jobs.length" class="selection-tools"><view><text class="selection-title">{{selecting?'选几张，一起拼起来':'把快乐拼在一起'}}</text><text class="selection-caption">{{selecting?'按点选顺序排列 · 最多 9 张':'支持静态图和动图混选'}}</text></view><button class="selection-toggle" :class="{'selection-cancel':selecting}" hover-class="selection-toggle-pressed" :disabled="!selecting&&!selectableJobs.length" @click="toggleSelection"><view v-if="!selecting" class="collage-grid" aria-hidden="true"><view/><view/><view/><view/></view><text v-else class="selection-cancel-icon" aria-hidden="true">×</text><text>{{selecting?'取消多选':'多选拼图'}}</text></button></view>
  <button v-if="!session" class="ui-secondary" @click="login" :loading="loggingIn">登录后，新作品可跨设备收好</button>
  <button v-if="error" class="error" @click="refresh">{{error}} · 点击重试</button>
  <view v-if="initialLoading && !jobs.length" class="queue-loading"><view v-for="n in 3" :key="n" class="queue-skeleton"><view/><view/></view><text>正在收好你的作品…</text></view>
  <view v-for="item in visibleJobs" :key="item.id" class="swipe-row" :class="{'row-leaving':leaving===item.id,'row-selected':selected.includes(item.id),'row-unavailable':selecting&&!canSelect(item)}">
   <button v-if="!selecting&&!['queued','running'].includes(item.status)" class="swipe-delete" @click.stop="remove(item)"><ui-icon name="trash" tone="white" :size="36"/><text>删除</text></button>
   <view class="job-card" :style="{transform:'translateX('+(opened===item.id?-86:0)+'px)'}" @click="openItem(item)" @touchstart="touchStart($event,item)" @touchmove="touchMove($event,item)" @touchend="touchEnd" @mousedown="touchStart($event,item)" @mousemove="touchMove($event,item)" @mouseup="touchEnd">
    <view v-if="selecting" class="selection-check" :class="{checked:selected.includes(item.id)}"><text v-if="selected.includes(item.id)">{{selected.indexOf(item.id)+1}}</text></view>
    <view class="job-cover"><image v-if="images[item.id]" :src="images[item.id]" mode="aspectFit"/><ui-icon v-else :name="item.status==='failed'?'image':'spark'" tone="accent" :size="52"/><view v-if="item.status==='completed' && !item.viewed && !item.viewedAt" class="unread-dot"/></view>
    <view class="job-copy"><text class="job-title">{{item.kind==='livegif' && item.status==='completed'?'动图活起来啦':labels[item.status]||'正在制作'}}</text><text>{{item.message || '小窝已经接单啦'}}</text><text>{{formatTime(item.created_at)}}</text></view>
    <view v-if="['queued','running'].includes(item.status)" class="working-ring"/><view v-else-if="!selecting" class="job-arrow"><ui-icon name="arrow" :size="30"/></view>
   </view>
  </view>
  <view v-if="!jobs.length && !error && !initialLoading" class="empty"><ui-icon name="image" :size="100" tone="accent"/><text>还没开工呢，去套个模板造梗吧。</text><button class="ui-primary" @click="goHome">去模板仓库</button></view>
  <text v-if="jobs.length" class="swipe-tip">{{selecting?'仅已完成的图片可参与拼图':'点整行看大图 · 左滑删除'}}</text>
  <view v-if="selecting" class="selection-bar"><button class="selection-all" @click="selectAll">{{allSelected?'清空':selectableJobs.length>9?'选前 9 张':'全选'}}</button><text>已选 {{selected.length}} / 9 张</text><button class="ui-primary make-collage" :disabled="selected.length<2||saving" @click="openCollage">拼图预览</button></view>
  <selected-results-modal class="selected-results-host" :show="collageOpen" :items="collageItems" :current-index="collageIndex" :busy="preparingCollage||saving" :error="collageError" :collage="showCollage?collage:null" :progress="collageProgress" @close="closeCollage" @change="changeCollageImage" @originals="showCollage=false;collageError=''" @collage="makeCollage" @share="shareCollage" @save="saveCollage"/>
  <preview-modal :show="!!activeItem" :is-generating="false" :image="activeImage" :allow-edit="!!(activeItem?.editDraft || activeItem?.can_regenerate)" @close="activeItem=null" @save="save" @share="share" @edit="editAgain"/>
  <bottom-tabs active="my"/><generation-notice/><first-use-guide/>
 </view>
</template>
<script setup>
import {shareCard} from '@/services/shareCard'
onShareAppMessage(()=>shareCard())
import {loadEditDraft,openEditDraft,disposeEditDraft} from '@/services/editSession'
import {takeCompletedResult} from '@/services/generationNotice'
import GenerationNotice from '@/components/GenerationNotice.vue'
import FirstUseGuide from '@/components/FirstUseGuide.vue'
import {ref,computed,watch} from 'vue'
import {onShow,onHide,onUnload,onReachBottom,onShareAppMessage} from '@dcloudio/uni-app'
import {useLibrary} from '@/composables/useLibrary'
import {listStudioJobs,cachedStudioJobs,cachedQueueThumbnail,warmQueueThumbnails,privateImage,deleteStudioJob,guestResults,removeGuestMeme,unreadCount,refreshUnread,viewStudioJob} from '@/services/studioService'
import SelectedResultsModal from '@/components/SelectedResultsModal.vue'
import {createResultCollage} from '@/services/resultCollage'
import {createStudioCollage} from '@/services/recommendService'
import {disposeEditedImage} from '@/services/imageEditing'
import {shareOriginalImage} from '@/services/wechatSharing'
import BottomTabs from '@/components/BottomTabs.vue'
import PreviewModal from '@/components/PreviewModal.vue'
import UiIcon from '@/components/UiIcon.vue'
const {session,loggingIn,loginWeChat}=useLibrary(),jobs=ref([]),images=ref({}),fullImages=ref({}),initialLoading=ref(false),pageSize=ref(20),error=ref(''),visible=ref(false),activeItem=ref(null),opened=ref(''),leaving=ref('')
const visibleJobs=computed(()=>jobs.value.slice(0,pageSize.value))
const activeImage=computed(()=>fullImages.value[activeItem.value?.id]||activeItem.value?.localPath||'')
const selecting=ref(false),selected=ref([]),collageOpen=ref(false),collageJobs=ref([]),collageIndex=ref(0),collage=ref(null),showCollage=ref(false),preparingCollage=ref(false),saving=ref(false),collageError=ref(''),collageProgress=ref('')
const canSelect=item=>item.status==='completed'&&!!(item.localPath||item.result_url)
const selectableJobs=computed(()=>jobs.value.filter(canSelect))
const allSelected=computed(()=>selected.value.length>0&&selectableJobs.value.slice(0,9).every(item=>selected.value.includes(item.id)))
const collageItems=computed(()=>collageJobs.value.map(item=>({slot:item.id,path:fullImages.value[item.id]||item.localPath||'',preview:images.value[item.id]||'',animated:item.kind==='livegif'||/\.gif(?:$|[?#])/i.test(item.localPath||'')})))
let collageEpoch=0,collageSavePath=''
const closeCollage=()=>{collageEpoch++;collageOpen.value=false;collageJobs.value=[];collageError.value='';collageProgress.value='';preparingCollage.value=false;showCollage.value=false;if(collage.value?.path&&collage.value.path!==collageSavePath)disposeEditedImage(collage.value.path);collage.value=null}
const toggleSelection=()=>{closeCollage();selecting.value=!selecting.value;selected.value=[];opened.value='';lastSwipe=null;gesture=null;activeItem.value=null}
const toggleItem=item=>{if(!canSelect(item))return;const index=selected.value.indexOf(item.id);if(index>=0){selected.value.splice(index,1);return}if(selected.value.length===9){uni.showToast({title:'一次最多拼 9 张表情',icon:'none'});return}selected.value.push(item.id)}
const selectAll=()=>{selected.value=allSelected.value?[]:selectableJobs.value.slice(0,9).map(item=>item.id)}
const originalTasks=new Map()
const ensureOriginal=async item=>{
 if(item.localPath)return item.localPath
 if(fullImages.value[item.id])return fullImages.value[item.id]
 const owner=session.value?.profile?.id,request=originalRevision,key=request+':'+item.id
 if(originalTasks.has(key))return originalTasks.get(key)
 const task=privateImage(item.result_url).then(path=>{if(request!==originalRevision||owner!==session.value?.profile?.id){disposeEditedImage(path);throw Error('账号或页面已切换，请重新选择')}fullImages.value[item.id]=path;return path}).finally(()=>originalTasks.delete(key))
 originalTasks.set(key,task);return task
}
const makeCollage=async()=>{
 if(preparingCollage.value||saving.value||collageJobs.value.length<2)return
 const request=collageEpoch,items=[...collageJobs.value];preparingCollage.value=true;collageError.value=''
 try{
  if(!collage.value){const paths=[];for(const [index,item] of items.entries()){collageProgress.value=`正在读取原图 · ${index+1} / ${items.length}`;paths.push(await ensureOriginal(item));if(request!==collageEpoch)return}
   const serverIds=items.map(item=>item.serverId||(!item.localPath?item.id:''))
   const result=await createResultCollage(paths,{cancelled:()=>request!==collageEpoch,onProgress:title=>{if(request===collageEpoch)collageProgress.value=title},remote:session.value&&serverIds.every(Boolean)?()=>createStudioCollage(serverIds,()=>request!==collageEpoch):undefined})
   if(request!==collageEpoch){disposeEditedImage(result.path);return}collage.value=result}
  showCollage.value=true
 }catch(e){if(request===collageEpoch)collageError.value=e.message||'拼图未完成，请重试'}finally{if(request===collageEpoch){preparingCollage.value=false;collageProgress.value=''}}
}
const openCollage=async()=>{if(selected.value.length<2||saving.value)return;closeCollage();collageJobs.value=selected.value.map(id=>jobs.value.find(item=>item.id===id)).filter(item=>item&&canSelect(item));collageIndex.value=0;collageOpen.value=true;await makeCollage()}
const changeCollageImage=async index=>{if(preparingCollage.value||saving.value||!collageJobs.value[index])return;collageIndex.value=index;collageError.value='';const request=collageEpoch;try{await ensureOriginal(collageJobs.value[index])}catch(e){if(request===collageEpoch)collageError.value=e.message}}
const shareCollage=()=>{const request=collageEpoch,path=showCollage.value?collage.value?.path:collageItems.value[collageIndex.value]?.path;shareOriginalImage(path,title=>{if(request===collageEpoch){collageError.value=title;uni.showToast({title,icon:'none'})}})}
const saveCollage=async()=>{
 if(saving.value||preparingCollage.value)return
 const request=collageEpoch,result=showCollage.value?collage.value:null,items=[...collageJobs.value];saving.value=true;collageError.value='';collageSavePath=result?.path||''
 try{
  const paths=result?[result.path]:await Promise.all(items.map(ensureOriginal))
  for(const path of paths){if(request!==collageEpoch)return;if(typeof document!=='undefined'){const a=document.createElement('a');a.href=path;a.download='GenSticker'+(result?(result.animated?'.gif':'.jpg'):'');a.click()}else await uni.saveImageToPhotosAlbum({filePath:path})}
  if(request===collageEpoch)uni.showToast({title:result?'拼图已保存':`已保存${paths.length}张`,icon:'success'})
 }catch(e){if(request===collageEpoch){const raw=String(e.errMsg||e.message||'');collageError.value=/auth|deny|denied|权限/.test(raw)?'请在小程序设置中允许保存到相册':raw||'保存失败，请重试'}}finally{collageSavePath='';if(result&&collage.value?.path!==result.path)disposeEditedImage(result.path);saving.value=false}
}
let originalRevision=0
let timer,loading=null,epoch=0,gesture=null,lastSwipe=null,restoring=false
watch(()=>session.value?.profile?.id,()=>{epoch++;originalRevision++;closeCollage();selecting.value=false;selected.value=[];jobs.value=[];images.value={};fullImages.value={};loading=null;activeItem.value=null;opened.value='';error.value='';refreshUnread();if(visible.value)refresh()})
const labels={queued:'排队等魔法',running:'正在认真造梗',completed:'损图出炉啦',failed:'这次没出炉'}
const showJobs=all=>{const local=guestResults().filter(item=>item.status==='completed'||!all.some(job=>job.id===item.serverId));jobs.value=[...local,...all.filter(j=>['manual','livegif'].includes(j.kind)&&!local.some(item=>item.serverId===j.id))].sort((a,b)=>b.created_at-a.created_at);selected.value=selected.value.filter(id=>jobs.value.some(item=>item.id===id&&canSelect(item)));for(const j of jobs.value){const path=cachedQueueThumbnail(j);if(path)images.value[j.id]=path}}
const thumbnails=()=>{const request=epoch;void warmQueueThumbnails(visibleJobs.value.filter(j=>j.result_url&&!images.value[j.id]),(j,path)=>{images.value[j.id]=path},()=>request===epoch&&visible.value)}
const refresh=async()=>{
 const request=epoch,owner=session.value?.profile?.id
 if(!owner){showJobs([]);initialLoading.value=false;refreshUnread();return}
 if(loading?.epoch===request)return loading.promise
 initialLoading.value=!jobs.value.length
 const task=(async()=>{try{const all=await listStudioJobs();if(owner!==session.value?.profile?.id||request!==epoch)return;showJobs(all);error.value='';refreshUnread();thumbnails()}catch(e){if(request===epoch&&owner===session.value?.profile?.id)error.value=e.message}finally{if(request===epoch)initialLoading.value=false;if(loading?.epoch===request)loading=null}})()
 loading={epoch:request,promise:task};return task
}
const login=async()=>{try{await loginWeChat();refresh()}catch(e){error.value=e.message}}
const openItem=async item=>{
 if(selecting.value){toggleItem(item);return}
 if(lastSwipe?.id===item.id && Date.now()-lastSwipe.time<300)return
 if(opened.value){opened.value='';return}
 if(item.status!=='completed'){uni.showToast({title:item.message||'还在认真制作中',icon:'none'});return}
 const request=originalRevision
 try{
  if(!fullImages.value[item.id]&&!item.localPath){uni.showLoading({title:'正在打开原图',mask:false});try{await ensureOriginal(item)}finally{uni.hideLoading()}}
  if(request!==originalRevision||selecting.value||collageOpen.value)return
  activeItem.value=item;await viewStudioJob(item);item.viewed=true;item.viewedAt=Date.now()
 }catch(e){if(request===originalRevision)error.value=e.message}
}
const save=async()=>{if(!activeImage.value)return;try{if(typeof document!=='undefined'){const a=document.createElement('a');a.href=activeImage.value;a.download='GenSticker'+(activeItem.value?.kind==='livegif'?'.gif':'.png');a.click();return}await uni.saveImageToPhotosAlbum({filePath:activeImage.value});uni.showToast({title:'已保存',icon:'success'})}catch(e){error.value='请在设置中允许保存到相册'}}
const share=()=>shareOriginalImage(activeImage.value,title=>uni.showToast({title,icon:'none'}))
const editAgain=async()=>{const item=activeItem.value;if(!item||restoring)return;restoring=true;const owner=session.value?.profile?.id;try{uni.showLoading({title:'恢复编辑内容',mask:true});const draft=await loadEditDraft(item);if(owner!==session.value?.profile?.id||!visible.value||activeItem.value?.id!==item.id){disposeEditDraft(draft);return}activeItem.value=null;openEditDraft(draft)}catch(e){const message=e.message||'编辑素材已过期，无法恢复';error.value=message;uni.showModal({title:'暂时无法重新编辑',content:message,showCancel:false})}finally{restoring=false;uni.hideLoading()}}
const touchStart=(e,item)=>{if(selecting.value)return;const p=e.touches?.[0]||e;gesture={id:item.id,x:p.clientX,y:p.clientY}}
const touchMove=(e,item)=>{if(selecting.value||!gesture||gesture.id!==item.id||(!e.touches&&!e.buttons)||['queued','running'].includes(item.status))return;const p=e.touches?.[0]||e,dx=p.clientX-gesture.x,dy=p.clientY-gesture.y;if(Math.abs(dx)>35&&Math.abs(dx)>Math.abs(dy)*1.4){opened.value=dx<0?item.id:'';lastSwipe={id:item.id,time:Date.now()}}}
const touchEnd=()=>{gesture=null}
const remove=async item=>{if(selecting.value||leaving.value)return;leaving.value=item.id;try{if(item.local||item.localPath)removeGuestMeme(item.id);else{await deleteStudioJob(item.id);removeGuestMeme(item.id)}await new Promise(resolve=>setTimeout(resolve,180));jobs.value=jobs.value.filter(j=>j.id!==item.id);delete images.value[item.id];delete fullImages.value[item.id];opened.value='';refreshUnread()}catch(e){error.value=e.message}finally{leaving.value=''}}
const formatTime=t=>new Date(t*1000).toLocaleString('zh-CN',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'})
const goHome=()=>uni.switchTab({url:'/pages/index/index'}),back=()=>getCurrentPages().length>1?uni.navigateBack():goHome()
onReachBottom(()=>{pageSize.value+=20;thumbnails()})
const openCompleted=()=>{if(!visible.value||selecting.value||collageOpen.value)return;const notice=takeCompletedResult('studio');if(!notice?.item)return;const cached=jobs.value.find(item=>item.id===notice.item.id||item.serverId===notice.item.id);const item=cached?.localPath?{...cached,status:'completed'}:{...cached,...notice.item,status:'completed'};if(notice.image)fullImages.value[item.id]=notice.image;void openItem(item)}
uni.$on('gensticker:open-result',openCompleted);onUnload(()=>uni.$off('gensticker:open-result',openCompleted))
onShow(()=>{visible.value=true;epoch++;showJobs(cachedStudioJobs());openCompleted();thumbnails();refresh();timer=setInterval(()=>{if(visible.value)refresh()},5000)})
const stop=()=>{visible.value=false;epoch++;originalRevision++;closeCollage();clearInterval(timer)};onHide(stop);onUnload(stop)
</script>
<style scoped>
.queue-page{min-height:100vh;background:var(--paper);padding:calc(110rpx + env(safe-area-inset-top)) 28rpx calc(160rpx + env(safe-area-inset-bottom))}.heading{display:flex;align-items:center;gap:20rpx;margin-bottom:28rpx}.heading>view{flex:1}.back{font-size:56rpx;width:60rpx;color:var(--ink)}.title{display:block;font-size:37rpx;font-weight:800}.unread-total{font-size:20rpx;color:#fff;background:#ee6a58;padding:3rpx 12rpx;border-radius:20rpx;vertical-align:middle;margin-left:8rpx}.intro{background:#f6ecd9;border:3rpx solid white;border-radius:30rpx;padding:28rpx;margin-bottom:30rpx}.intro text{display:block;font-size:23rpx;line-height:1.8;color:#968972}.intro text:first-child{font-weight:700;font-size:29rpx;color:var(--ink);margin-bottom:8rpx}.swipe-row{position:relative;margin-bottom:22rpx;border-radius:28rpx;background:#ed7e65;overflow:hidden;box-shadow:0 6rpx 0 #efe5da;transition:opacity .2s,transform .2s}.swipe-delete{position:absolute;right:0;top:0;bottom:0;width:86px;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:10rpx;font-size:24rpx;color:white}.job-card{position:relative;display:flex;align-items:center;gap:18rpx;padding:24rpx;background:white;border-radius:28rpx;transition:transform .22s cubic-bezier(.2,.8,.2,1);touch-action:pan-y}.job-cover{width:112rpx;height:112rpx;border-radius:22rpx;flex-shrink:0;background:#fff2da;position:relative;display:flex;align-items:center;justify-content:center}.job-cover image{width:100%;height:100%;border-radius:22rpx}.unread-dot{position:absolute;right:-6rpx;top:-6rpx;width:20rpx;height:20rpx;background:#ef6658;border:4rpx solid white;border-radius:50%;animation:ui-pop .3s ease-out}.job-copy{flex:1;min-width:0}.job-copy text{display:block;font-size:21rpx;color:#a29a89;line-height:1.7}.job-copy .job-title{font-weight:700;font-size:28rpx;color:var(--ink)}.job-arrow{display:flex;align-items:center;flex-shrink:0;transform:rotate(180deg)}.working-ring{width:30rpx;height:30rpx;border:3rpx solid #f5dac0;border-top-color:#e68e62;border-radius:50%;animation:ui-spin .9s linear infinite}.row-leaving{transform:translateX(-100%);opacity:0}.empty{display:flex;align-items:center;flex-direction:column;gap:30rpx;text-align:center;padding:60rpx 25rpx;color:#9d9788;font-size:24rpx}.empty button{width:100%}.error{width:100%;background:#fff0e5;color:#b36f52;border-radius:20rpx;font-size:23rpx;padding:20rpx;margin:18rpx 0}.swipe-tip{display:block;text-align:center;color:#b3a48f;font-size:21rpx;margin-top:25rpx}
</style>

<style scoped>.queue-loading{color:var(--muted);font-size:23rpx;text-align:center}.queue-skeleton{display:flex;gap:20rpx;padding:24rpx;margin-bottom:22rpx;background:white;border:3rpx solid white;border-radius:28rpx}.queue-skeleton>view:first-child{width:112rpx;height:112rpx;border-radius:22rpx;background:#f8f0e2}.queue-skeleton>view:last-child{flex:1;height:62rpx;margin-top:20rpx;border-radius:14rpx;background:linear-gradient(#f5efe5 45%,white 45%,white 65%,#faf5ed 65%)}</style>

<style scoped>
.selection-tools{display:flex;align-items:center;gap:18rpx;margin-bottom:24rpx}.selection-tools>view{flex:1;min-width:0}.selection-title,.selection-caption{display:block}.selection-title{font-size:27rpx;font-weight:700;color:var(--ink)}.selection-caption{font-size:21rpx;color:var(--muted);margin-top:6rpx}.selection-toggle{display:flex;align-items:center;justify-content:center;gap:12rpx;flex-shrink:0;min-height:76rpx;margin:0;padding:18rpx 24rpx;border:2rpx solid #f4c7ac;border-radius:25rpx;background:linear-gradient(145deg,#fff1df,#ffe4cf);color:#bf704c;font-size:25rpx;font-weight:700;line-height:1.4;white-space:nowrap;box-shadow:inset 0 2rpx 0 #fffaf3,0 5rpx 0 #ead2bd;transition:transform .16s ease,box-shadow .16s ease}.selection-toggle::after{border:0}.collage-grid{width:30rpx;height:30rpx;display:flex;flex-wrap:wrap;gap:4rpx;flex-shrink:0;transform:rotate(-6deg)}.collage-grid>view{width:13rpx;height:13rpx;border:2rpx solid currentColor;border-radius:4rpx;box-sizing:border-box;background:#bf704c12}.collage-grid>view:first-child{background:#bf704c33}.collage-grid>view:last-child{background:#bf704c55}.selection-toggle.selection-cancel{background:linear-gradient(145deg,#fffdf8,#f7f0e5);border-color:#e9ddcb;color:#8f806d;box-shadow:inset 0 2rpx 0 #fff,0 5rpx 0 #e9dfd0}.selection-cancel-icon{width:30rpx;font-size:33rpx;font-weight:400;line-height:28rpx;text-align:center}.selection-toggle-pressed{transform:translateY(3rpx);box-shadow:inset 0 2rpx 0 #fff8ee,0 2rpx 0 #ead2bd}.selection-toggle[disabled]{color:#b7ac9c;background:#f2ece3;border-color:#e9e0d4;box-shadow:0 3rpx 0 #e6ddd1}.selection-toggle[disabled] .collage-grid>view{background:transparent}@media(max-width:350px){.selection-toggle{gap:9rpx;padding:16rpx 18rpx;font-size:24rpx}.selection-title{font-size:25rpx}.selection-caption{font-size:20rpx}}@media(prefers-reduced-motion:reduce){.selection-toggle{transition:none}}.is-selecting{padding-bottom:calc(290rpx + env(safe-area-inset-bottom))}.selection-check{width:38rpx;height:38rpx;flex-shrink:0;border:3rpx solid #d9cdbb;border-radius:50%;display:flex;align-items:center;justify-content:center;color:white;font-size:23rpx;font-weight:700}.selection-check.checked{background:var(--accent);border-color:var(--accent)}.row-selected .job-card{background:#fff3e7}.row-selected{box-shadow:0 0 0 3rpx var(--accent),0 6rpx 0 #efe5da}.row-unavailable{opacity:.55}.is-selecting .job-card{gap:14rpx}.selection-bar{position:fixed;z-index:99;left:20rpx;right:20rpx;bottom:calc(142rpx + env(safe-area-inset-bottom));display:flex;align-items:center;gap:14rpx;padding:18rpx 20rpx;background:var(--paper);border:3rpx solid white;border-radius:28rpx;box-shadow:0 5rpx 26rpx #57463322}.selection-bar>text{flex:1;font-size:24rpx;color:var(--ink);white-space:nowrap}.selection-all{font-size:23rpx;color:var(--accent-dark);padding:12rpx 6rpx;line-height:1.5}.make-collage{font-size:25rpx;line-height:1.5;min-height:72rpx;padding:16rpx 26rpx}
</style>
