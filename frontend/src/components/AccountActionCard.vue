<template>
 <button class="feature-card" @click="$emit('click')">
  <view class="feature-icon" :class="tone"><ui-icon :name="icon" :tone="tone==='peach'?'accent':'ink'"/></view>
  <text class="feature-title">{{title}}</text><text class="feature-desc">{{description}}</text>
  <text v-if="count!==undefined" class="count">{{count}} <text>个模板</text></text>
 </button>
</template>
<script setup>
import UiIcon from '@/components/UiIcon.vue'
defineProps({icon:String,title:String,description:String,tone:{type:String,default:'sage'},count:Number})
defineEmits(['click'])
</script>
<style scoped>
.feature-card{width:100%;height:100%;min-height:246rpx;min-width:0;text-align:left;padding:27rpx;line-height:1.5;background:linear-gradient(145deg,#fff,#fefdfb);border:3rpx solid white;border-radius:33rpx;box-shadow:0 7rpx 0 #f0e8df;color:var(--ink)}.feature-icon{width:72rpx;height:72rpx;border-radius:24rpx;display:flex;align-items:center;justify-content:center;margin-bottom:18rpx;transform:rotate(-7deg);border:2rpx solid #ffffff99;transition:transform .2s ease-out}.sage{background:linear-gradient(135deg,#e5eedc,#c8ddbd);box-shadow:inset 0 3rpx 0 #f8fff1,0 6rpx 0 #b9cba6}.peach{background:linear-gradient(135deg,#ffe1cc,#f4c3a6);box-shadow:inset 0 3rpx 0 #fff2e6,0 6rpx 0 #ddb296;transform:rotate(9deg)}.feature-title{display:block;font-size:28rpx;font-weight:700;word-break:keep-all}.feature-desc{display:block;font-size:22rpx;color:#a8a18f;margin-top:5rpx;line-height:1.7}.count{display:block;font-size:35rpx;color:#8b9c7a;font-weight:700;margin-top:22rpx}.count>text{font-size:20rpx;font-weight:400;color:#a4ab96}.feature-card:active .feature-icon{transform:translateY(-5rpx) rotate(9deg)}
</style>
