<template>
 <subject-picker :show="true" :src="src" :initial-rect="canUndo ? [0,0,1,1] : null" :detect-enabled="!canUndo" :busy="busy" :external-error="error" file-type="png" @cancel="$emit('close')" @confirm="confirm">
  <template #tools="selection">
   <scroll-view v-if="images.length>1" class="editor-images" scroll-x><button v-for="(image,index) in images" :key="index" :class="{active:index===activeIndex}" :disabled="busy || selection.locked" @click="$emit('select',index)"><image :src="image" mode="aspectFill"/><text>{{index+1}}</text></button></scroll-view>
   <view class="editor-tools"><button :disabled="busy || selection.locked" @click="edit('flip',selection)"><ui-icon name="flip"/><text>左右翻转</text></button><button :disabled="busy || selection.locked" @click="edit('rotate',selection)"><ui-icon name="rotate"/><text>旋转 90°</text></button><button :disabled="busy || selection.locked" @click="edit('background',selection)"><ui-icon name="cutout"/><text>去除背景</text></button></view>
   <view class="editor-history"><button :disabled="busy || selection.locked || !canUndo" @click="$emit('undo')">撤销上一步</button><button :disabled="busy || selection.locked || !canUndo" @click="$emit('restore')">还原上传图</button></view>
  </template>
 </subject-picker>
</template>
<script setup>
import SubjectPicker from '@/components/SubjectPicker.vue'
import UiIcon from '@/components/UiIcon.vue'
import {warmLocalBackground} from '@/services/localBackground'
import {onMounted} from 'vue'
defineProps({src:String,images:{type:Array,default:()=>[]},activeIndex:{type:Number,default:0},busy:Boolean,error:String,canUndo:Boolean})
const emit=defineEmits(['close','select','edit','undo','restore'])
const edit=(type,selection)=>emit('edit',{type,...(selection.selected?{rect:[...selection.rect]}:{})})
const confirm=selection=>emit('edit',{type:'prepared',path:selection.path,complete:true})
onMounted(()=>{warmLocalBackground().catch(()=>{})})
</script>
<style scoped>
.editor-tools{display:flex;gap:12rpx;margin:18rpx 0 10rpx}.editor-tools button{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10rpx;min-height:100rpx;background:#fff;border:2rpx solid var(--line);border-radius:20rpx;font-size:22rpx;color:var(--ink)}.editor-tools button:last-child{background:var(--mint)}.editor-history{display:flex;gap:24rpx;margin-bottom:18rpx}.editor-history button{background:transparent;padding:10rpx 0;color:var(--muted);font-size:22rpx}.editor-images{white-space:nowrap;margin-top:16rpx}.editor-images button{display:inline-block;position:relative;width:74rpx;height:74rpx;margin-right:12rpx;border:3rpx solid transparent;border-radius:15rpx;overflow:hidden;padding:0}.editor-images button.active{border-color:var(--accent)}.editor-images image{width:100%;height:100%}.editor-images text{position:absolute;bottom:0;right:0;background:var(--paper);font-size:18rpx;padding:1rpx 7rpx}button[disabled]{opacity:.45}
</style>
