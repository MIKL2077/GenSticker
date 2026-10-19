<template>
 <view class="timeline-editor">
  <video :id="videoId" class="timeline-video" :style="{height:previewHeight+'px'}" :src="src" :poster="poster" :initial-time="range.start" :controls="false" :show-center-play-btn="false" :show-fullscreen-btn="false" :muted="true" object-fit="contain" @timeupdate="timeUpdate"/>
  <view class="range-description"><text>{{range.start.toFixed(1)}} s — {{(range.start+range.duration).toFixed(1)}} s</text><text>已选 {{range.duration.toFixed(1)}} 秒 / 最长 9 秒</text></view>
  <view class="filmstrip-row"><button class="play" @click="preview">{{playing?'Ⅱ':'▶'}}</button><view class="filmstrip" @touchmove.stop.prevent="move" @touchend="finish" @touchcancel="finish" @mousemove="move" @mouseup="finish" @mouseleave="finish">
   <view v-for="(thumb,index) in tiles" :key="index" class="tile"><image v-if="thumb" :src="thumb" mode="aspectFill"/><view v-else class="frame-placeholder"/></view>
   <view class="range-window" :style="rangeStyle" @touchstart.stop="begin($event,'window')" @mousedown.stop.prevent="begin($event,'window')"><view class="range-handle left" @touchstart.stop="begin($event,'left')" @mousedown.stop.prevent="begin($event,'left')">‹</view><view class="range-handle right" @touchstart.stop="begin($event,'right')" @mousedown.stop.prevent="begin($event,'right')">›</view></view>
   <view class="playhead" :style="{left:100*playhead/total+'%'}"/>
  </view></view>
  <text class="timeline-hint">拖动两侧选起止点，拖动中间选框移动整段。</text>
 </view>
</template>
<script setup>
import {ref,computed,getCurrentInstance,onBeforeUnmount,watch} from 'vue'
import {clipWindow,videoThumbnails} from '@/services/liveGifService'
const props=defineProps({src:String,poster:String,total:{type:Number,default:3},modelValue:{type:Object,default:()=>({start:0,duration:3})}})
const emit=defineEmits(['update:modelValue'])
const win=uni.getWindowInfo?.()||uni.getSystemInfoSync(),previewHeight=Math.max(180,Math.min(440,win.windowHeight-335)),instance=getCurrentInstance(),videoId='timeline-preview',playing=ref(false),playhead=ref(0),thumbs=ref([])
const range=computed(()=>clipWindow(props.total,props.modelValue.start,props.modelValue.duration)),rangeStyle=computed(()=>({left:100*range.value.start/props.total+'%',width:100*range.value.duration/props.total+'%'})),tiles=computed(()=>Array.from({length:6},(_,i)=>thumbs.value[i]||props.poster||''))
const stripWidth=Math.max(120,Math.min(640,win.windowWidth)-102)
const player=()=>uni.createVideoContext(videoId,instance.proxy)
let drag=null,epoch=0
watch(()=>props.src,async path=>{const version=++epoch;thumbs.value=[];if(path)try{const images=await videoThumbnails(path,props.total);if(version===epoch)thumbs.value=images}catch(_){}},{immediate:true})
const point=e=>e.touches?.[0]||e
const begin=(e,kind)=>{const p=point(e);drag={kind,x:p.clientX,start:range.value.start,end:range.value.start+range.value.duration};playing.value=false;player().pause()}
const move=e=>{if(!drag||(!e.touches&&!e.buttons))return;const delta=(point(e).clientX-drag.x)/stripWidth*props.total;let {start,end}=drag
 if(drag.kind==='window'){start=Math.max(0,Math.min(props.total-(end-start),start+delta));end=start+range.value.duration}
 else if(drag.kind==='left')start=Math.max(0,Math.min(end-.2,Math.max(end-9,start+delta)))
 else end=Math.min(props.total,Math.max(start+.2,Math.min(start+9,end+delta)))
 emit('update:modelValue',{start:Math.round(start*10)/10,duration:Math.round((end-start)*10)/10})}
const finish=()=>{if(drag){drag=null;player().seek(range.value.start);playhead.value=range.value.start}}
const preview=()=>{if(playing.value){playing.value=false;player().pause();return}playing.value=true;player().seek(range.value.start);player().play()}
const timeUpdate=e=>{playhead.value=e.detail.currentTime;if(playing.value&&playhead.value>=range.value.start+range.value.duration){playing.value=false;player().pause();player().seek(range.value.start)}}
onBeforeUnmount(()=>{epoch++;playing.value=false;player().pause()})
</script>
<style scoped>
.timeline-video{border-radius:24rpx;width:100%;background:#101211;display:block}.range-description{display:flex;justify-content:space-between;color:var(--ink);font-size:22rpx;margin:24rpx 0 18rpx}.range-description text:last-child{color:var(--muted)}.filmstrip-row{display:flex;gap:12rpx;height:108rpx;align-items:stretch}.play{color:var(--accent-dark);width:80rpx;flex-shrink:0;background:var(--peach);color:var(--accent-dark);font-size:32rpx;border-radius:14rpx;display:flex;align-items:center;justify-content:center}.filmstrip{flex:1;display:flex;position:relative;overflow:hidden;background:#353b38;border-radius:12rpx;touch-action:none}.tile{width:16.666%;height:100%;overflow:hidden}.tile image,.frame-placeholder{width:100%;height:100%}.frame-placeholder{background:linear-gradient(145deg,#354e42,#6d8975)}.range-window{position:absolute;top:0;bottom:0;border-top:5rpx solid var(--accent);border-bottom:5rpx solid var(--accent);box-shadow:0 0 0 800px #263f4866;touch-action:none;min-width:16px}.range-handle{position:absolute;top:-5rpx;bottom:-5rpx;background:var(--accent);width:24rpx;font-size:42rpx;color:#fff;display:flex;align-items:center;justify-content:center}.left{left:0}.right{right:0}.playhead{position:absolute;top:0;bottom:0;width:3rpx;background:white;pointer-events:none}.timeline-hint{display:block;text-align:center;color:var(--muted);font-size:21rpx;line-height:1.7;margin-top:18rpx}
</style>
