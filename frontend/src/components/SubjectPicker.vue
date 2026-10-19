<template>
 <view v-if="show" class="subject-modal"><view class="subject-sheet"><view class="subject-heading"><view><text>选好主角，再开始造梗</text><text>{{detecting?'正在寻找画面中的主角…':'点选候选框，拖动选框移动，拖动两角调整范围'}}</text></view><button class="ui-close" :disabled="processing" @click="$emit('cancel')">×</button></view>
  <view class="subject-stage" :style="{width:stage.w+'px',height:stage.h+'px'}" @touchmove.stop.prevent="move" @touchend="drag=null" @touchcancel="drag=null" @mousemove="move" @mouseup="drag=null" @mouseleave="drag=null"><image :src="src" mode="scaleToFill"/><button v-for="(candidate,index) in candidates" :key="candidate.id" class="subject-candidate" :style="style(candidate.box)" @click.stop="select(candidate)">{{candidate.kind==='animal'?'宠物':'人物'}} {{index+1}}</button><view v-if="selected" class="subject-box" :style="style(rect)" @touchstart.stop="begin($event,'move')" @mousedown.stop.prevent="begin($event,'move')"><view class="subject-handle top-left" @touchstart.stop="begin($event,'tl')" @mousedown.stop.prevent="begin($event,'tl')"/><view class="subject-handle bottom-right" @touchstart.stop="begin($event,'br')" @mousedown.stop.prevent="begin($event,'br')"/><text>已选主角</text></view></view>
  <scroll-view class="subject-choices" scroll-x><button v-for="(candidate,index) in candidates" :key="candidate.id" :class="{active:chosen===candidate.id}" @click="select(candidate)">{{candidate.kind==='animal'?'宠物':'人物'}} {{index+1}}</button><button :class="{active:chosen==='manual'}" @click="manual">手动框选</button></scroll-view><text class="subject-note">{{message||'只处理确认后的区域。识别遗漏时，也可以手动框选人物、宠物或物体。'}}</text><button class="ui-primary subject-confirm" :disabled="!selected||processing||!info.width" :loading="processing" @click="confirm">{{processing?'正在截取主角…':'就用这个主角'}}</button><text v-if="error" class="subject-error">{{error}}</text>
 </view></view>
</template>
<script setup>
import {ref,computed,watch,onBeforeUnmount} from 'vue'
import {detectSubjects} from '@/services/subjectSelection'
import {editImage,disposeEditedImage} from '@/services/imageEditing'
import {clampCrop} from '@/services/liveGifService'
const props=defineProps({show:Boolean,src:String,initialRect:Array}),emit=defineEmits(['confirm','cancel'])
const info=ref({width:1,height:1}),candidates=ref([]),rect=ref([0,0,1,1]),chosen=ref(''),selected=ref(false),detecting=ref(false),processing=ref(false),error=ref(''),message=ref('')
const win=uni.getWindowInfo?.()||uni.getSystemInfoSync(),stage=computed(()=>{const ratio=info.value.width/info.value.height,maxHeight=Math.max(130,win.windowHeight-350),w=Math.min(win.windowWidth-64,520,maxHeight*ratio);return {w,h:w/ratio}})
const style=box=>({left:box[0]*100+'%',top:box[1]*100+'%',width:box[2]*100+'%',height:box[3]*100+'%'})
let version=0,drag=null
watch(()=>[props.show,props.src],async()=>{
 const request=++version;if(!props.show||!props.src)return
 info.value={width:1,height:1};candidates.value=[];rect.value=props.initialRect?[...props.initialRect]:[0,0,1,1];selected.value=!!props.initialRect;chosen.value=props.initialRect?'manual':'';error.value='';message.value='';detecting.value=true
 try{
  const dimensions=await new Promise((resolve,reject)=>uni.getImageInfo({src:props.src,success:resolve,fail:reject}));if(request!==version)return;info.value=dimensions
  const result=await detectSubjects(props.src);if(request!==version)return;candidates.value=result.candidates||[];if(!candidates.value.length)message.value='没有找到明确的候选框，点“手动框选”圈出想要的主角。'
 }catch(_){if(request===version)message.value='自动检测暂不可用，仍可点“手动框选”继续。'}finally{if(request===version)detecting.value=false}
},{immediate:true})
const select=candidate=>{if(processing.value)return;rect.value=clampCrop(candidate.box);chosen.value=candidate.id;selected.value=true}
const manual=()=>{if(processing.value)return;chosen.value='manual';selected.value=true;rect.value=[.1,.1,.8,.8]}
const point=e=>e.touches?.[0]||e
const begin=(e,kind)=>{if(processing.value)return;const p=point(e);drag={kind,x:p.clientX,y:p.clientY,rect:[...rect.value]}}
const move=e=>{if(!drag||(!e.touches&&!e.buttons))return;const p=point(e),dx=(p.clientX-drag.x)/stage.value.w,dy=(p.clientY-drag.y)/stage.value.h;let [x,y,w,h]=drag.rect
 if(drag.kind==='move'){x+=dx;y+=dy}
 if(drag.kind==='br'){w=Math.max(.05,Math.min(1-x,w+dx));h=Math.max(.05,Math.min(1-y,h+dy))}
 if(drag.kind==='tl'){const nx=Math.max(0,Math.min(x+w-.05,x+dx)),ny=Math.max(0,Math.min(y+h-.05,y+dy));w+=x-nx;h+=y-ny;x=nx;y=ny}
 rect.value=clampCrop([x,y,w,h]);chosen.value='manual'}
const confirm=async()=>{if(processing.value||!selected.value)return;const request=version;processing.value=true;error.value='';try{const result=await editImage(props.src,{type:'crop',rect:[...rect.value],fileType:'jpg'});if(request===version){emit('confirm',{path:result,rect:[...rect.value]})}else disposeEditedImage(result)}catch(e){if(request===version)error.value=e.message||'截取未完成，原图已保留，请重试'}finally{processing.value=false}}
onBeforeUnmount(()=>{version++})
</script>
<style scoped>
.subject-modal{position:fixed;inset:0;background:#263f4877;z-index:2600;display:flex;align-items:center;justify-content:center;padding:24rpx}.subject-sheet{background:var(--paper);border:3rpx solid white;border-radius:34rpx;padding:24rpx;width:100%;max-width:600px;max-height:calc(100vh - 40px - env(safe-area-inset-top) - env(safe-area-inset-bottom));overflow-y:auto}.subject-heading{display:flex;align-items:center;gap:14rpx;margin-bottom:22rpx}.subject-heading>view{flex:1}.subject-heading text{display:block;font-size:28rpx;font-weight:750}.subject-heading text:last-child{font-size:21rpx;font-weight:400;color:var(--muted);margin-top:8rpx}.subject-stage{position:relative;margin:0 auto;overflow:hidden;background:var(--mint);border-radius:14rpx;touch-action:none}.subject-stage>image{width:100%;height:100%}.subject-candidate{position:absolute;border:2px dashed #fff;border-radius:8px;background:#263f4822;color:#fff;font-size:11px;padding:3px;text-align:left;display:flex;align-items:flex-start;line-height:1.3}.subject-box{position:absolute;border:3px solid var(--accent);box-shadow:0 0 0 600px #263f4866;touch-action:none}.subject-box>text{position:absolute;left:4px;top:4px;background:var(--accent);color:white;font-size:11px;padding:2px 5px;border-radius:4px;pointer-events:none}.subject-handle{position:absolute;width:28px;height:28px;border-color:#fff;border-style:solid}.top-left{left:-5px;top:-5px;border-width:5px 0 0 5px}.bottom-right{right:-5px;bottom:-5px;border-width:0 5px 5px 0}.subject-choices{white-space:nowrap;margin:20rpx 0}.subject-choices button{display:inline-block;font-size:23rpx;padding:12rpx 20rpx;margin-right:14rpx;background:white;border:2rpx solid var(--line);border-radius:18rpx;color:var(--ink);line-height:1.5}.subject-choices button.active{background:var(--peach);color:var(--accent-dark);border-color:#ffb292}.subject-note{display:block;font-size:21rpx;line-height:1.7;color:var(--muted);margin-bottom:20rpx}.subject-confirm{width:100%}.subject-error{display:block;color:var(--accent-dark);font-size:23rpx;margin-top:15rpx}
</style>
