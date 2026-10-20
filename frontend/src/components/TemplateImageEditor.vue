<template>
 <subject-picker :show="true" :src="src" :initial-rect="canUndo ? [0,0,1,1] : null" :detect-enabled="!canUndo" editable :can-undo="canUndo" :busy="busy" :external-error="error" file-type="png" @cancel="$emit('close')" @confirm="confirm" @undo="$emit('undo')" @restore="$emit('restore')">
  <template #images="selection"><scroll-view v-if="images.length>1" class="editor-images" scroll-x><button v-for="(image,index) in images" :key="index" :class="{active:index===activeIndex}" :disabled="busy || selection.locked" @click="$emit('select',index)"><image :src="image" mode="aspectFill"/><text>{{index+1}}</text></button></scroll-view></template>
 </subject-picker>
</template>
<script setup>
import SubjectPicker from '@/components/SubjectPicker.vue'
defineProps({src:String,images:{type:Array,default:()=>[]},activeIndex:{type:Number,default:0},busy:Boolean,error:String,canUndo:Boolean})
const emit=defineEmits(['close','select','edit','undo','restore'])
const confirm=selection=>emit('edit',{type:'prepared',path:selection.path,complete:true})
</script>
<style scoped>
.editor-images{white-space:nowrap;margin:10rpx 0}.editor-images button{display:inline-block;position:relative;width:60rpx;height:60rpx;margin-right:12rpx;border:3rpx solid transparent;border-radius:15rpx;overflow:hidden;padding:0}.editor-images button.active{border-color:var(--accent)}.editor-images image{width:100%;height:100%}.editor-images text{position:absolute;bottom:0;right:0;background:var(--paper);font-size:18rpx;padding:1rpx 7rpx}button[disabled]{opacity:.45}
</style>
