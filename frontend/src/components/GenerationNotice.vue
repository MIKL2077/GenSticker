<template>
 <button v-if="pageActive && notice && accountMatches" :key="notice.sequence" class="generation-notice" :class="{visible}" aria-label="生成成功，点击查看成品" @click="open">
  <view class="generation-notice-icon">✓</view><view class="generation-notice-copy"><text>{{notice.message}}</text><text>点击查看，保存或分享</text></view><view class="generation-notice-link">查看成品 <text>→</text></view><view class="generation-notice-timer" aria-hidden="true"/>
 </button>
</template>
<script setup>
import {ref,computed,watch} from 'vue'
import {onShow,onHide,onUnload} from '@dcloudio/uni-app'
import {useLibrary} from '@/composables/useLibrary'
import {generationNotice as notice,generationNoticeVisible as visible,noticeBelongsToAccount,dismissGenerationNotice,openGenerationNotice as open} from '@/services/generationNotice'
const {session}=useLibrary(),pageActive=ref(false)
const accountMatches=computed(()=>{session.value;return noticeBelongsToAccount()})
watch(()=>session.value?.access_token,()=>{if(!noticeBelongsToAccount())dismissGenerationNotice()})
onShow(()=>{pageActive.value=true;if(!noticeBelongsToAccount())dismissGenerationNotice()})
onHide(()=>{pageActive.value=false});onUnload(()=>{pageActive.value=false})
</script>
<style scoped>
.generation-notice{position:fixed;z-index:7000;bottom:calc(185rpx + env(safe-area-inset-bottom));left:24rpx;right:24rpx;display:flex;align-items:center;gap:16rpx;padding:22rpx 20rpx;background:#fffaf2;color:var(--ink);border:2rpx solid #fff;border-radius:28rpx;box-shadow:0 5rpx 0 #e7d9c8,0 12rpx 32rpx #263f4826;overflow:hidden;opacity:0;transform:translateY(18rpx);transition:opacity .8s ease,transform .25s ease;pointer-events:auto;text-align:left;line-height:1.5}
.generation-notice.visible{opacity:1;transform:translateY(0)}
.generation-notice-icon{display:flex;align-items:center;justify-content:center;flex-shrink:0;width:60rpx;height:60rpx;border-radius:20rpx;background:#e5eee4;color:#61816c;font-size:34rpx;font-weight:750;box-shadow:inset 0 2rpx 0 #f8fff7}
.generation-notice-copy{flex:1;min-width:0}
.generation-notice-copy>text{display:block;font-size:27rpx;font-weight:750;overflow-wrap:break-word}
.generation-notice-copy>text:last-child{font-size:21rpx;color:#9b886f;font-weight:400;margin-top:4rpx}
.generation-notice-link{display:flex;align-items:center;gap:8rpx;flex-shrink:0;padding:12rpx 15rpx;background:#ffebe0;border:1rpx solid #ffddca;border-radius:18rpx;font-size:23rpx;line-height:1.5;color:var(--accent-dark);font-weight:700;white-space:nowrap}
.generation-notice-link text{font-size:26rpx}
.generation-notice-timer{position:absolute;bottom:0;left:20rpx;right:20rpx;height:4rpx;background:#e7bda3;border-radius:4rpx;transform-origin:left center;animation:notice-countdown 5s linear both}
@keyframes notice-countdown{from{transform:scaleX(1)}to{transform:scaleX(0)}}
@media(max-width:350px){.generation-notice{gap:12rpx;padding:20rpx 16rpx}.generation-notice-icon{width:52rpx;height:52rpx;border-radius:17rpx;font-size:30rpx}.generation-notice-copy>text{font-size:25rpx}.generation-notice-copy>text:last-child{font-size:20rpx}.generation-notice-link{gap:5rpx;padding:10rpx 12rpx;font-size:21rpx}}
@media(prefers-reduced-motion:reduce){.generation-notice{transition:opacity .8s ease;transform:none}.generation-notice-timer{animation:none;display:none}}
</style>
