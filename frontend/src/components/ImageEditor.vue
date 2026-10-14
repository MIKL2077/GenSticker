<template>
  <view class="editor-mask" @touchmove.stop>
    <view class="editor-sheet">
      <view class="editor-heading"><view><text class="editor-title">让图片更合适</text><text class="editor-sub">{{ cropMode ? '拖动图片、缩放，选择保留区域' : '修改会直接预览，完成后用于制作' }}</text></view><button class="editor-close" @click="$emit('close')">✕</button></view>
      <view v-if="!cropMode" class="editor-stage checker"><image :src="src" mode="aspectFit" class="editor-photo"/><view v-if="busy" class="processing"><view class="editor-spinner"/><text>正在处理图片…</text><text class="processing-sub">原图会保留</text></view></view>
      <view v-else class="crop-stage"><view class="crop-frame checker" :style="{width:frameWidth+'px',height:frameHeight+'px'}" @touchstart="startDrag" @touchmove.stop.prevent="moveDrag" @touchend="drag=null" @touchcancel="drag=null" @mousedown.stop.prevent="startDrag" @mousemove="moveDrag" @mouseup="drag=null" @mouseleave="drag=null"><image :src="src" :style="cropImageStyle" mode="scaleToFill"/><view class="crop-grid"><view/><view/></view></view></view>
      <template v-if="cropMode">
        <view class="ratios"><button v-for="item in ratios" :key="item.label" :class="{chosen:ratio===item.value}" @click="selectRatio(item.value)">{{ item.label }}</button></view>
        <view class="zoom-row"><text>缩放</text><slider :value="Math.round(zoom*100)" min="100" max="300" activeColor="#ff8656" @changing="changeZoom" @change="changeZoom"/><text>{{ zoom.toFixed(1) }}×</text></view>
        <view class="editor-footer"><button class="editor-secondary" @click="cropMode=false">取消裁剪</button><button class="editor-primary" @click="applyCrop">应用裁剪</button></view>
      </template>
      <template v-else>
        <view v-if="images.length>1" class="editor-thumbnails"><image v-for="(path,index) in images" :key="index" :src="path" mode="aspectFill" :class="{selected:index===activeIndex}" @click="!busy && $emit('select',index)"/></view>
        <view class="editor-tools"><button :disabled="busy || !info.width" @click="beginCrop"><text>⌗</text>裁剪</button><button :disabled="busy" @click="$emit('edit',{type:'flip'})"><text>↔</text>左右翻转</button><button :disabled="busy" @click="$emit('edit',{type:'rotate'})"><text>↻</text>旋转</button></view>
        <button class="background-tool" :disabled="busy" @click="$emit('edit',{type:'background'})"><text>✦</text><view><text>去背景 · 保留主体</text><text class="tool-sub">立即预览透明背景，保留主要人物或物体</text></view></button>
        <text v-if="error" class="editor-error">{{ error }}</text>
        <view class="editor-history"><button :disabled="busy || !canUndo" @click="$emit('undo')">↶ 撤销</button><button :disabled="busy || !canUndo" @click="$emit('restore')">还原原图</button><text>透明区域以格纹显示</text></view>
        <button class="editor-primary editor-done" :disabled="busy" @click="$emit('close')">完成编辑</button>
      </template>
    </view>
  </view>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { cropGeometry } from '@/services/imageEditing'
const props=defineProps({src:String,images:{type:Array,default:()=>[]},activeIndex:Number,busy:Boolean,error:String,canUndo:Boolean})
const emit=defineEmits(['close','select','edit','undo','restore'])
const info=ref({width:0,height:0}),cropMode=ref(false),ratio=ref(1),zoom=ref(1),offsetX=ref(0),offsetY=ref(0)
const windowWidth=uni.getWindowInfo ? uni.getWindowInfo().windowWidth : uni.getSystemInfoSync().windowWidth
const maxWidth=Math.min(windowWidth*.84,340),maxHeight=300
let drag=null,loadEpoch=0
watch(()=>props.src,path=>{const epoch=++loadEpoch;cropMode.value=false;info.value={width:0,height:0};if(path)uni.getImageInfo({src:path,success:r=>{if(epoch===loadEpoch)info.value=r},fail:()=>{}})},{immediate:true})
const frameWidth=computed(()=>Math.min(maxWidth,maxHeight*ratio.value))
const frameHeight=computed(()=>frameWidth.value/ratio.value)
const geometry=computed(()=>cropGeometry(info.value.width||1,info.value.height||1,frameWidth.value,frameHeight.value,zoom.value,offsetX.value,offsetY.value))
const cropImageStyle=computed(()=>({position:'absolute',pointerEvents:'none',width:geometry.value.width+'px',height:geometry.value.height+'px',left:((frameWidth.value-geometry.value.width)/2+geometry.value.x)+'px',top:((frameHeight.value-geometry.value.height)/2+geometry.value.y)+'px'}))
const ratios=computed(()=>[{label:'方形',value:1},{label:'头像',value:4/5},{label:'横图',value:4/3},{label:'原比例',value:(info.value.width||1)/(info.value.height||1)}])
const resetCrop=()=>{zoom.value=1;offsetX.value=0;offsetY.value=0}
const beginCrop=()=>{resetCrop();ratio.value=1;cropMode.value=true}
const selectRatio=value=>{ratio.value=value;resetCrop()}
const changeZoom=e=>{zoom.value=e.detail.value/100;offsetX.value=geometry.value.x;offsetY.value=geometry.value.y}
const startDrag=e=>{const t=e.touches?.[0] || e;if(Number.isFinite(t.clientX)&&Number.isFinite(t.clientY))drag={x:t.clientX,y:t.clientY,dx:geometry.value.x,dy:geometry.value.y}}
const moveDrag=e=>{const t=e.touches?.[0] || (e.buttons ? e : null);if(!drag||!t)return;offsetX.value=drag.dx+t.clientX-drag.x;offsetY.value=drag.dy+t.clientY-drag.y}
const applyCrop=()=>{emit('edit',{type:'crop',rect:geometry.value.rect});cropMode.value=false}
</script>

<style scoped>
.editor-mask{position:fixed;inset:0;z-index:2200;background:rgba(38,26,21,.68);display:flex;align-items:flex-end;justify-content:center}.editor-sheet{background:#fffaf5;border-radius:34rpx 34rpx 0 0;padding:30rpx 30rpx calc(28rpx + env(safe-area-inset-bottom));width:100%;box-sizing:border-box;max-height:94vh;overflow-y:auto;animation:editor-rise .25s ease-out}.editor-heading{display:flex;justify-content:space-between;align-items:center;margin-bottom:24rpx}.editor-title{display:block;font-size:34rpx;font-weight:700;color:#49352b}.editor-sub{display:block;font-size:23rpx;color:#a28676;margin-top:8rpx}.editor-close{margin:0;background:#f2e9e1;border-radius:50%;width:64rpx;height:64rpx;line-height:64rpx;padding:0;color:#81695a;font-size:30rpx}.checker{background-color:#fff;background-image:linear-gradient(45deg,#eee7df 25%,transparent 25%),linear-gradient(-45deg,#eee7df 25%,transparent 25%),linear-gradient(45deg,transparent 75%,#eee7df 75%),linear-gradient(-45deg,transparent 75%,#eee7df 75%);background-size:24px 24px;background-position:0 0,0 12px,12px -12px,-12px 0}.editor-stage{height:480rpx;max-height:34vh;border-radius:24rpx;overflow:hidden;position:relative}.editor-photo{width:100%;height:100%}.processing{position:absolute;inset:0;background:rgba(255,250,245,.9);display:flex;flex-direction:column;align-items:center;justify-content:center;gap:16rpx;color:#856858;font-size:27rpx}.processing-sub{font-size:22rpx;color:#a78b7b}.editor-spinner{width:42rpx;height:42rpx;border:5rpx solid #ffdec9;border-top-color:#ff8656;border-radius:50%;animation:spin .8s linear infinite}.editor-tools{display:flex;gap:12rpx;margin:24rpx 0 16rpx}.editor-tools button{flex:1;margin:0;padding:16rpx 0;border-radius:20rpx;font-size:24rpx;line-height:1.5;color:#715243;background:#fff;border:2rpx solid #f3e5d8}.editor-tools text{display:block;font-size:36rpx;line-height:1.25;margin-bottom:6rpx;color:#ee8c5b}.background-tool{display:flex;align-items:center;text-align:left;gap:22rpx;padding:20rpx 24rpx;border-radius:22rpx;background:#ffeedf;color:#83523c;font-size:27rpx;line-height:1.6}.background-tool>text{font-size:42rpx;color:#f58a56}.tool-sub{display:block;color:#b6876d;font-size:21rpx}.editor-history{display:flex;align-items:center;gap:14rpx;margin:18rpx 0}.editor-history button{font-size:23rpx;background:none;margin:0;padding:4rpx 10rpx;color:#927966;line-height:2}.editor-history>text{margin-left:auto;font-size:20rpx;color:#b8a391}.editor-primary{background:linear-gradient(110deg,#ff6c69,#ff9751);color:#fff;font-size:28rpx;border-radius:24rpx;padding:22rpx 10rpx;line-height:1.5;flex:1}.editor-secondary{background:#eee5dd;color:#886e5d;border-radius:24rpx;font-size:28rpx;line-height:1.5;padding:22rpx 10rpx;flex:1}.editor-footer{display:flex;gap:20rpx;margin-top:16rpx}.editor-error{display:block;color:#a55440;background:#ffede5;border-radius:16rpx;font-size:23rpx;line-height:1.6;padding:14rpx;margin-top:16rpx}.editor-thumbnails{display:flex;gap:14rpx;margin-top:18rpx;overflow-x:auto}.editor-thumbnails image{width:72rpx;height:72rpx;border-radius:14rpx;border:4rpx solid transparent;flex-shrink:0}.editor-thumbnails .selected{border-color:#ff9863}.crop-stage{display:flex;justify-content:center;background:#3b302a;padding:18rpx;border-radius:22rpx}.crop-frame{position:relative;overflow:hidden}.crop-grid{pointer-events:none;position:absolute;inset:0;border:2px solid #fff;box-sizing:border-box;background:linear-gradient(to right,transparent 33%,rgba(255,255,255,.55) 33%,rgba(255,255,255,.55) 33.3%,transparent 33.3%,transparent 66.6%,rgba(255,255,255,.55) 66.6%,rgba(255,255,255,.55) 66.9%,transparent 66.9%),linear-gradient(to bottom,transparent 33%,rgba(255,255,255,.55) 33%,rgba(255,255,255,.55) 33.3%,transparent 33.3%,transparent 66.6%,rgba(255,255,255,.55) 66.6%,rgba(255,255,255,.55) 66.9%,transparent 66.9%)}.ratios{display:flex;gap:12rpx;margin:20rpx 0}.ratios button{flex:1;background:#eee5dc;font-size:23rpx;color:#95735d;margin:0;padding:12rpx 0;line-height:1.5;border-radius:16rpx}.ratios .chosen{background:#ffddc4;color:#995738}.zoom-row{display:flex;align-items:center;color:#a08470;font-size:24rpx;gap:12rpx}.zoom-row slider{flex:1}button::after{border:0}button[disabled]{opacity:.4}.editor-tools button:active,.background-tool:active{transform:scale(.97)}@keyframes editor-rise{from{transform:translateY(50rpx);opacity:.3}to{transform:translateY(0);opacity:1}}@keyframes spin{to{transform:rotate(360deg)}}
</style>
