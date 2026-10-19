<template>
 <view class="video-cropper">
  <view class="stage" :style="{width:stage.w+'px',height:stage.h+'px'}" @touchstart="begin($event,'move')" @touchmove.stop.prevent="move" @touchend="drag=null" @touchcancel="drag=null" @mousedown.prevent="begin($event,'move')" @mousemove="move" @mouseup="drag=null" @mouseleave="drag=null">
   <video :id="videoId" :src="src" :poster="poster" :initial-time="start||0" :style="videoStyle" object-fit="fill" :controls="false" :show-center-play-btn="false" :show-play-btn="false" :show-fullscreen-btn="false" :muted="true" :enable-progress-gesture="false" @timeupdate="timeUpdate" @loadedmetadata="metadataReady"/>
   <view class="crop-box" :style="boxStyle"><view class="grid v1"/><view class="grid v2"/><view class="grid h1"/><view class="grid h2"/><view class="handle tl" @touchstart.stop="begin($event,'tl')" @mousedown.stop.prevent="begin($event,'tl')"/><view class="handle br" @touchstart.stop="begin($event,'br')" @mousedown.stop.prevent="begin($event,'br')"/><text class="crop-label">保留框内画面</text><text v-if="caption" class="crop-caption">{{caption}}</text></view>
  </view>
  <view v-if="!compact" class="controls"><button @click="preview">▶ 预览所选片段</button><button @click="$emit('update:modelValue',[0,0,1,1])">完整画面</button></view>
  <text v-if="!compact" class="hint">拖动框移动位置，拖动角点改变宽高；可单独截取人脸。</text>
  <view v-if="!compact" class="ratios"><button v-for="item in ratios" :key="item.label" @click="setRatio(item.value)">{{item.label}}</button></view>
  <view v-if="!compact" class="size-row"><text>框宽</text><slider :value="Math.round(modelValue[2]*100)" :min="5" :max="100" @changing="resize(2,$event)" @change="resize(2,$event)" activeColor="#d68d68"/></view>
  <view v-if="!compact" class="size-row"><text>框高</text><slider :value="Math.round(modelValue[3]*100)" :min="5" :max="100" @changing="resize(3,$event)" @change="resize(3,$event)" activeColor="#d68d68"/></view>
 </view>
</template>
<script setup>
import {computed,getCurrentInstance,onBeforeUnmount,watch} from 'vue'
import {clampCrop} from '@/services/liveGifService'
const props=defineProps({src:String,poster:String,caption:String,compact:Boolean,width:{type:Number,default:1},height:{type:Number,default:1},modelValue:{type:Array,default:()=>[0,0,1,1]},start:Number,duration:Number,rotation:Number,flip:Boolean})
const emit=defineEmits(['update:modelValue','metadata'])
const instance=getCurrentInstance(),videoId='clip-preview',win=uni.getWindowInfo?.()||uni.getSystemInfoSync()
const stage=computed(()=>{const ratio=props.rotation%180?props.height/props.width:props.width/props.height,maxHeight=props.compact?Math.max(140,Math.min(340,win.windowHeight-360-(win.safeAreaInsets?.top||0)-(win.safeAreaInsets?.bottom||0))):340,w=Math.min(win.windowWidth-56,420,maxHeight*ratio);return {w,h:w/ratio}})
const videoStyle=computed(()=>{const rotated=props.rotation%180!==0,w=rotated?stage.value.h:stage.value.w,h=rotated?stage.value.w:stage.value.h;return {position:'absolute',width:w+'px',height:h+'px',left:(stage.value.w-w)/2+'px',top:(stage.value.h-h)/2+'px',transform:`scaleX(${props.flip?-1:1}) rotate(${props.rotation||0}deg)`,pointerEvents:'none'}})
const boxStyle=computed(()=>{const [x,y,w,h]=props.modelValue;return {left:x*stage.value.w+'px',top:y*stage.value.h+'px',width:w*stage.value.w+'px',height:h*stage.value.h+'px'}})
let drag=null,playing=false
const player=()=>uni.createVideoContext(videoId,instance.proxy)
const p=e=>e.touches?.[0]||e
const begin=(e,kind)=>{const point=p(e);drag={kind,x:point.clientX,y:point.clientY,rect:[...props.modelValue]}}
const move=e=>{if(!drag||(!e.touches&&!e.buttons))return;const point=p(e),dx=(point.clientX-drag.x)/stage.value.w,dy=(point.clientY-drag.y)/stage.value.h;let [x,y,w,h]=drag.rect
 if(drag.kind==='move'){x+=dx;y+=dy}
 if(drag.kind==='br'){w=Math.max(.05,Math.min(1-x,w+dx));h=Math.max(.05,Math.min(1-y,h+dy))}
 if(drag.kind==='tl'){const nx=Math.max(0,Math.min(x+w-.05,x+dx)),ny=Math.max(0,Math.min(y+h-.05,y+dy));w+=x-nx;h+=y-ny;x=nx;y=ny}
 emit('update:modelValue',clampCrop([x,y,w,h]))}
const resize=(index,e)=>{const rect=[...props.modelValue];rect[index]=e.detail.value/100;emit('update:modelValue',clampCrop(rect))}
const ratios=[{label:'方形',value:1},{label:'竖版',value:.75},{label:'横版',value:4/3}]
const setRatio=ratio=>{const aspect=props.rotation%180?props.height/props.width:props.width/props.height;let w=.8,h=w*aspect/ratio;if(h>.9){h=.9;w=h*ratio/aspect}emit('update:modelValue',[(1-w)/2,(1-h)/2,w,h])}
const preview=()=>{const video=player();playing=true;video.seek(props.start||0);video.play()}
const metadataReady=e=>{emit('metadata',e.detail);player().seek(props.start||0)}
const timeUpdate=e=>{if(playing&&e.detail.currentTime>=props.start+props.duration){playing=false;player().pause();player().seek(props.start)}}
watch(()=>props.start,()=>{playing=false;player().pause();player().seek(props.start)})
onBeforeUnmount(()=>{playing=false;player().pause()})
</script>
<style scoped>
.stage{position:relative;margin:25rpx auto 20rpx;overflow:hidden;background:#253f45;touch-action:none;border-radius:12px}.crop-box{position:absolute;border:2px solid #ffbc84;box-shadow:0 0 0 600px #10282977;pointer-events:none}.grid{position:absolute;background:#ffffff55}.v1,.v2{top:0;bottom:0;width:1px}.v1{left:33.33%}.v2{left:66.66%}.h1,.h2{left:0;right:0;height:1px}.h1{top:33.33%}.h2{top:66.66%}.handle{position:absolute;width:32px;height:32px;pointer-events:auto}.tl{left:-12px;top:-12px;border-left:5px solid #fff4dc;border-top:5px solid #fff4dc}.br{right:-12px;bottom:-12px;border-right:5px solid #fff4dc;border-bottom:5px solid #fff4dc}.crop-label{position:absolute;top:8px;left:8px;background:#213e45aa;color:white;padding:3px 7px;border-radius:6px;font-size:10px}.controls,.ratios{display:flex;gap:14rpx;margin:18rpx 0}.controls button,.ratios button{flex:1;background:#fff;border-radius:16rpx;color:#ac785e;font-size:22rpx;padding:15rpx 5rpx}.hint{display:block;color:#9e9785;font-size:21rpx;line-height:1.7}.size-row{display:flex;align-items:center;color:#9d927e;font-size:22rpx}.size-row slider{flex:1;margin:14rpx}
.crop-caption{position:absolute;bottom:0;left:0;right:0;background:#fff5dfe8;color:#253f45;font-size:23rpx;line-height:1.4;text-align:center;padding:7rpx 6rpx;max-height:40%;overflow:hidden;word-break:break-all}
</style>
