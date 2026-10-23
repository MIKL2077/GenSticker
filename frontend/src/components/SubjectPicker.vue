<template>
 <view v-if="show" class="subject-modal"><view class="subject-sheet">
  <view class="subject-heading"><view><text>选好主角，再开始造梗</text><text>{{locked?'正在处理图片，请稍等…':detecting?'可直接调整范围，正在自动找人':'选人物、调范围、改图片，在这里一次完成'}}</text></view><button class="ui-close" @click="$emit('cancel')">×</button></view>
  <view class="subject-workspace">
   <view class="subject-stage" :style="{width:stage.w+'px',height:stage.h+'px'}" @touchmove.stop.prevent="move" @touchend="drag=null" @touchcancel="drag=null" @mousemove="move" @mouseup="drag=null" @mouseleave="drag=null">
    <image :src="workingSrc" mode="aspectFit"/>
    <button v-for="(candidate,index) in (isOriginal?candidates:[])" :key="candidate.id" class="subject-candidate" :style="style(candidate.box)" :disabled="locked" @click.stop="select(candidate)">{{candidate.kind==='animal'?'宠物':candidate.kind==='subject'?'主体':'人物'}} {{index+1}}</button>
    <view v-if="selected" class="subject-box" :style="style(rect)" @touchstart.stop="begin($event,'move')" @mousedown.stop.prevent="begin($event,'move')"><view class="subject-handle top-left" @touchstart.stop="begin($event,'tl')" @mousedown.stop.prevent="begin($event,'tl')"/><view class="subject-handle bottom-right" @touchstart.stop="begin($event,'br')" @mousedown.stop.prevent="begin($event,'br')"/><text>{{isOriginal?(chosen==='manual'?'裁剪范围':'已选主角'):'主角预览'}}</text></view>
   </view>
  </view>
  <view class="subject-controls">
   <scroll-view class="subject-choices" scroll-x><button v-for="(candidate,index) in candidates" :key="candidate.id" :disabled="locked" :class="{active:chosen===candidate.id}" @click="select(candidate)">{{candidate.kind==='animal'?'宠物':candidate.kind==='subject'?'主体':'人物'}} {{index+1}}</button><button :disabled="locked" :class="{active:chosen==='manual'}" @click="manual">手动框选</button><button v-if="detectEnabled && !candidates.length" :disabled="locked || detecting" @click="retryDetection">{{detecting?'自动找人中…':'精细识别'}}</button></scroll-view>
   <slot name="images" :locked="locked"/>
   <view v-if="editable" class="editor-tools"><button :disabled="locked" @click="apply('flip')"><ui-icon name="flip"/><text>左右翻转</text></button><button :disabled="locked" @click="apply('rotate')"><ui-icon name="rotate"/><text>旋转 90°</text></button><button :disabled="locked" @click="apply('background')"><ui-icon name="cutout"/><text>去除背景</text></button></view>
   <view v-if="editable" class="editor-history"><button :disabled="locked || (!history.length && !canUndo)" @click="undo">撤销上一步</button><button :disabled="locked || (!history.length && !canUndo)" @click="restore">还原上传图</button></view>
   <slot name="tools" :rect="rect" :selected="selected" :locked="locked"/>
   <text class="subject-note">{{message || (backgroundHint + '点选后可拖动或缩放选框；识别必要时临时上传，不保存检测原图。')}}</text>
   <button class="ui-primary subject-confirm" :disabled="!selected||locked||!info.width" :loading="locked" @click="confirm">{{locked?'正在处理图片…':'就用这个主角'}}</button><text v-if="error || externalError" class="subject-error">{{error || externalError}}</text>
  </view>
 </view></view>
</template>
<script setup>
import {ref,computed,watch,onBeforeUnmount} from 'vue'
import {displayImageSize} from '@/services/imageGeometry'
import {imageEditError} from '@/services/imageEditing'
import {detectSubjects} from '@/services/subjectSelection'
import {editImage,removeImageBackground,composeBackgroundMask,disposeEditedImage} from '@/services/imageEditing'
import {holdBackgroundWork} from '@/services/backgroundActivity'
import {clampCrop} from '@/services/liveGifService'
import UiIcon from '@/components/UiIcon.vue'
const props=defineProps({show:Boolean,src:String,initialRect:Array,busy:Boolean,externalError:String,editable:Boolean,canUndo:Boolean,fileType:{type:String,default:'jpg'},detectEnabled:{type:Boolean,default:true}}),emit=defineEmits(['confirm','cancel','undo','restore'])
const info=ref({width:0,height:0}),originalInfo=ref({width:0,height:0}),workingSrc=ref(''),candidates=ref([]),rect=ref([0,0,1,1]),originRect=ref(null),chosen=ref(''),selected=ref(false),detecting=ref(false),processing=ref(false),error=ref(''),message=ref(''),backgroundHint=ref(''),history=ref([]),transparent=ref(false)
const locked=computed(()=>processing.value || props.busy),isOriginal=computed(()=>workingSrc.value===props.src)
const win=uni.getWindowInfo?.()||uni.getSystemInfoSync(),stage=computed(()=>{const ratio=(info.value.width||1)/(info.value.height||1),safe=win.safeAreaInsets?(win.safeAreaInsets.top||0)+(win.safeAreaInsets.bottom||0):(win.safeArea?.top||0)+Math.max(0,(win.screenHeight||win.windowHeight)-(win.safeArea?.bottom||win.screenHeight||win.windowHeight)),maxHeight=Math.max(120,Math.min(440,win.windowHeight-safe-(props.editable?420:280))),w=Math.min(win.windowWidth-64,520,maxHeight*ratio);return {w,h:w/ratio}})
const style=box=>({left:box[0]*100+'%',top:box[1]*100+'%',width:box[2]*100+'%',height:box[3]*100+'%'})
let version=0,drag=null,detectionTask=null,touched=false,backgroundTimer=null,backgroundJob=null
const owned=new Set()
let resumeWarmup=null
watch(()=>props.show,show=>{resumeWarmup?.();resumeWarmup=show?holdBackgroundWork():null},{immediate:true})
const dropBackground=()=>{clearTimeout(backgroundTimer);backgroundTimer=null;const job=backgroundJob;backgroundJob=null;if(job?.path)disposeEditedImage(job.path)}
const dispose=()=>{dropBackground();detectionTask?.abort?.();detectionTask=null;for(const path of owned)disposeEditedImage(path);owned.clear()}
const backgroundKey=()=>JSON.stringify([workingSrc.value,rect.value])
const scheduleBackground=()=>{
 if(backgroundJob?.key===backgroundKey() && (backgroundJob.path || !backgroundJob.done) && !processing.value && props.show)return
 dropBackground()
 if(!props.show || !props.editable || !selected.value || processing.value || !info.value.width || transparent.value || (detecting.value && !touched && chosen.value==='manual'))return
 // Speculation is device-only: no photo upload, and never queue another model
 // run while an earlier selection is still being processed.
 const key=backgroundKey(),request=version,src=workingSrc.value,box=[...rect.value]
 backgroundTimer=setTimeout(()=>{
  const job={key,path:null,promise:null};backgroundJob=job
  job.promise=removeImageBackground(src,{rect:box,localOnly:true}).catch(()=>null).then(path=>{
   if((backgroundJob!==job && !job.taken) || version!==request){if(path)disposeEditedImage(path);return null}
   job.done=true;job.path=path;return path
  })
 },250)
}
const dimensions=src=>new Promise((resolve,reject)=>uni.getImageInfo({src,success:result=>resolve(displayImageSize(result)),fail:reject}))
watch(()=>[props.show,props.src],async()=>{
 const request=++version;processing.value=false;dispose();history.value=[];touched=!!props.initialRect;if(!props.show||!props.src)return
 transparent.value=false;info.value={width:0,height:0};workingSrc.value=props.src;candidates.value=[];rect.value=props.initialRect?[...props.initialRect]:[0,0,1,1];originRect.value=null;selected.value=true;chosen.value='manual';error.value='';message.value='';detecting.value=true
 backgroundHint.value=''
 try{
  const size=await dimensions(props.src);if(request!==version)return;info.value=size;originalInfo.value=size
  if(!props.detectEnabled)return
  const result=await detectSubjects(props.src,{withMask:props.editable,isCurrent:()=>request===version,onTask:task=>{detectionTask=task}});if(request!==version)return;candidates.value=result.candidates||[]
  if(candidates.value.length && !touched && isOriginal.value && !locked.value){
   rect.value=clampCrop(candidates.value[0].box);chosen.value=candidates.value[0].id
  }
   if(result.preview && isOriginal.value && !locked.value && JSON.stringify(result.preview.box)===JSON.stringify(rect.value)){
    dropBackground();const job={key:backgroundKey(),path:null,promise:null};backgroundJob=job
    job.promise=composeBackgroundMask(props.src,result.preview,{rect:[...rect.value]}).catch(()=>null).then(path=>{
     if((backgroundJob!==job && !job.taken) || request!==version){if(path)disposeEditedImage(path);return null}
     job.done=true;job.path=path;return path
    })
  }
  if(!candidates.value.length)message.value='可直接调整选框，或点“精细识别”查找更多主体。'
 }catch(e){if(request===version)message.value='可继续调整选框，自动识别暂未完成。'}finally{if(request===version){detecting.value=false;scheduleBackground()}}
},{immediate:true})
watch(()=>[props.show,workingSrc.value,rect.value.join(','),processing.value,detecting.value],scheduleBackground)
const retryDetection=async()=>{
 if(detecting.value || locked.value)return
 const request=version;detecting.value=true;message.value='';error.value=''
 try{
  const result=await detectSubjects(props.src,{force:true,extended:true,isCurrent:()=>request===version,onTask:task=>{detectionTask=task}})
  if(request===version){candidates.value=result.candidates||[];if(!candidates.value.length)message.value='没有找到明确的候选框，点“手动框选”圈出想要的主角。'}
 }catch(e){if(request===version)message.value=imageEditError(e).message+'；仍可手动框选。'}
 finally{if(request===version)detecting.value=false}
}
const snapshot=()=>({src:workingSrc.value,info:info.value,transparent:transparent.value,rect:[...rect.value],origin:originRect.value?[...originRect.value]:null,chosen:chosen.value,selected:selected.value})
const remember=()=>{history.value=[...history.value,snapshot()].slice(-4)}
const chooseOriginal=()=>{if(!isOriginal.value)remember();workingSrc.value=props.src;info.value=originalInfo.value;transparent.value=false;originRect.value=null;error.value=''}
const select=candidate=>{if(locked.value)return;touched=true;chooseOriginal();rect.value=clampCrop(candidate.box);chosen.value=candidate.id;selected.value=true}
const manual=()=>{if(locked.value)return;touched=true;chooseOriginal();chosen.value='manual';selected.value=true;rect.value=[.1,.1,.8,.8]}
const point=e=>e.touches?.[0]||e
const begin=(e,kind)=>{if(locked.value)return;touched=true;const p=point(e);drag={kind,x:p.clientX,y:p.clientY,rect:[...rect.value]}}
const move=e=>{if(locked.value||!drag||(!e.touches&&!e.buttons))return;const p=point(e),dx=(p.clientX-drag.x)/stage.value.w,dy=(p.clientY-drag.y)/stage.value.h;let [x,y,w,h]=drag.rect
 if(drag.kind==='move'){x+=dx;y+=dy}
 if(drag.kind==='br'){w=Math.max(.05,Math.min(1-x,w+dx));h=Math.max(.05,Math.min(1-y,h+dy))}
 if(drag.kind==='tl'){const nx=Math.max(0,Math.min(x+w-.05,x+dx)),ny=Math.max(0,Math.min(y+h-.05,y+dy));w+=x-nx;h+=y-ny;x=nx;y=ny}
 rect.value=clampCrop([x,y,w,h]);chosen.value='manual'}
const apply=async type=>{
 if(locked.value)return
 touched=true
 const request=version,before=snapshot(),prepared=type==='background' && backgroundJob?.key===backgroundKey()?backgroundJob:null
 if(prepared){prepared.taken=true;backgroundJob=null;clearTimeout(backgroundTimer);backgroundTimer=null}
 processing.value=true;error.value='';let output=''
 try{
  let source=workingSrc.value
  if(request!==version)return
  if(type==='background'){
   output=prepared?.path || (prepared?await prepared.promise:null)
   if(request!==version){if(output)disposeEditedImage(output);return}
   if(!output)output=await removeImageBackground(source,{rect:selected.value?[...rect.value]:undefined,onProgress:progress=>{if(request===version)message.value='正在接收去背景结果（'+progress+'%）…'}})
  }else output=await editImage(source,{type,fileType:'png',rect:selected.value?[...rect.value]:undefined})
  const size=await dimensions(output)
  if(request!==version){disposeEditedImage(output);output='';return}
  owned.add(output);history.value=[...history.value,before].slice(-4)
  if(isOriginal.value)originRect.value=selected.value?[...rect.value]:[0,0,1,1]
  workingSrc.value=output;info.value=size;transparent.value=type==='background'||transparent.value;rect.value=[0,0,1,1];selected.value=true;message.value='预览已更新，可以继续编辑，也可以切换下方的其他人物。'
  const retained=new Set([workingSrc.value,...history.value.map(item=>item.src)])
  for(const path of owned)if(!retained.has(path)){owned.delete(path);disposeEditedImage(path)}
 }catch(e){if(output&&!owned.has(output))disposeEditedImage(output);if(request===version){message.value='';error.value=imageEditError(e).message}}finally{if(request===version)processing.value=false}
}
const undo=()=>{if(locked.value)return;const last=history.value.pop();if(!last){emit('undo');return}workingSrc.value=last.src;info.value=last.info;transparent.value=last.transparent;rect.value=last.rect;originRect.value=last.origin;chosen.value=last.chosen;selected.value=last.selected;error.value='';message.value=''}
const restore=()=>{if(locked.value)return;touched=true;dispose();history.value=[];transparent.value=false;workingSrc.value=props.src;info.value=originalInfo.value;rect.value=props.initialRect?[...props.initialRect]:[0,0,1,1];originRect.value=null;selected.value=true;chosen.value='manual';message.value='';error.value='';if(props.canUndo)emit('restore')}
const confirm=async()=>{if(locked.value||!selected.value)return;const request=version;processing.value=true;error.value='';try{const result=await editImage(workingSrc.value,{type:'crop',rect:[...rect.value],fileType:transparent.value?'png':props.fileType});if(request===version){emit('confirm',{path:result,rect:originRect.value?[...originRect.value]:[...rect.value]})}else disposeEditedImage(result)}catch(e){if(request===version){message.value='';error.value=imageEditError(e).message}}finally{if(request===version)processing.value=false}}
onBeforeUnmount(()=>{version++;dispose();resumeWarmup?.()})
</script>
<style scoped>
.subject-modal{position:fixed;inset:0;background:#263f4877;z-index:2600;display:flex;align-items:center;justify-content:center;padding:24rpx;padding-top:calc(24rpx + env(safe-area-inset-top));padding-bottom:calc(24rpx + env(safe-area-inset-bottom))}.subject-sheet{background:var(--paper);border:3rpx solid white;border-radius:34rpx;padding:24rpx;width:100%;max-width:600px;max-height:100%;display:flex;flex-direction:column;overflow-y:auto}.subject-heading{display:flex;align-items:center;gap:14rpx;margin-bottom:18rpx;flex-shrink:0}.subject-heading>view{flex:1}.subject-heading text{display:block;font-size:28rpx;font-weight:750}.subject-heading text:last-child{font-size:21rpx;font-weight:400;color:var(--muted);margin-top:8rpx}.subject-heading .ui-close{width:64rpx;height:64rpx;min-height:64rpx;flex-shrink:0}.subject-workspace{min-height:0;flex-shrink:0}.subject-stage{position:relative;margin:0 auto;overflow:hidden;background:repeating-conic-gradient(#f4f1e9 0% 25%,#fffaf5 0% 50%) 50%/20px 20px;border-radius:14rpx;touch-action:none}.subject-stage>image{position:absolute;inset:0;width:100%;height:100%}.subject-candidate{position:absolute;border:2px dashed #fff;border-radius:8px;background:#263f4822;color:#fff;font-size:11px;padding:3px;text-align:left;display:flex;align-items:flex-start;line-height:1.3}.subject-box{position:absolute;border:3px solid var(--accent);box-shadow:0 0 0 600px #263f4866;touch-action:none}.subject-box>text{position:absolute;left:4px;top:4px;background:var(--accent);color:white;font-size:11px;padding:2px 5px;border-radius:4px;pointer-events:none}.subject-handle{position:absolute;width:28px;height:28px;border-color:#fff;border-style:solid}.top-left{left:-5px;top:-5px;border-width:5px 0 0 5px}.bottom-right{right:-5px;bottom:-5px;border-width:0 5px 5px 0}.subject-controls{flex-shrink:0}.subject-choices{white-space:nowrap;margin:16rpx 0}.subject-choices button{display:inline-block;font-size:23rpx;padding:12rpx 20rpx;margin-right:14rpx;background:white;border:2rpx solid var(--line);border-radius:18rpx;color:var(--ink);line-height:1.5}.subject-choices button.active{background:var(--peach);color:var(--accent-dark);border-color:#ffb292}.subject-note{display:block;font-size:21rpx;line-height:1.6;color:var(--muted);margin:10rpx 0 16rpx}.subject-confirm{width:100%;min-height:82rpx}.subject-error{display:block;color:var(--accent-dark);font-size:23rpx;margin-top:12rpx}.editor-tools{display:flex;gap:12rpx;margin:14rpx 0 8rpx}.editor-tools button{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8rpx;min-height:96rpx;background:#fff;border:2rpx solid var(--line);border-radius:20rpx;font-size:22rpx;color:var(--ink)}.editor-tools button:last-child{background:var(--mint)}.editor-history{display:flex;gap:24rpx}.editor-history button{background:transparent;padding:10rpx 0;color:var(--muted);font-size:22rpx}button[disabled]{opacity:.45}
</style>
