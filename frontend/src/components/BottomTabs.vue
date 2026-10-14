<template>
  <view class="bottom-tabs">
    <button class="tab" :class="{ active: active === 'home' }" @click="go('home')"><text class="icon">🏠</text><text>首页</text></button>
    <view class="ai-slot"><button class="ai-orb" :class="{ selected: active === 'ai' }" aria-label="AI生成" @click="go('ai')"><text class="spark">✦</text><text class="ai-label">AI</text></button><text class="ai-copy">AI 生成</text></view>
    <button class="tab" :class="{ active: active === 'my' }" @click="go('my')"><text class="icon">👤</text><text>我的</text></button>
  </view>
</template>
<script>
import { onMounted } from 'vue'
export default {
  props: { active: String },
  setup(props) {
    onMounted(() => uni.hideTabBar({ animation: false, fail: () => {} }))
    return { go: tab => { if (tab === props.active) return; if (tab === 'ai') return uni.navigateTo({ url: '/pages/recommend/index' }); uni.switchTab({ url: tab === 'home' ? '/pages/index/index' : '/pages/my/index' }) } }
  },
}
</script>
<style scoped>
.bottom-tabs { position:fixed; bottom:0; left:0; right:0; display:flex; gap:10rpx; background:white; padding:12rpx 16rpx calc(12rpx + env(safe-area-inset-bottom)); border-radius:24rpx 24rpx 0 0; z-index:100 }
.tab { flex:1; margin:0; border:2rpx solid transparent; border-radius:22rpx; background:#f7f8fa; color:#666; font-size:24rpx; line-height:1.5; padding:20rpx; display:flex; flex-direction:column; align-items:center; gap:6rpx }
.icon { font-size:36rpx }.tab.active { color:#ff6868; border-color:#ffd0d0; background:#fff7f7; font-weight:600 }
.bottom-tabs{align-items:center;background:rgba(255,255,255,.97)}
.ai-slot{width:132rpx;display:flex;flex-direction:column;align-items:center;position:relative;margin-top:-44rpx;gap:8rpx}
.ai-orb{width:112rpx;height:112rpx;padding:0;margin:0;line-height:1;background:linear-gradient(145deg,#302449,#6750b9 65%,#f19e93);color:white;border-radius:50%;border:8rpx solid #fff;box-shadow:0 8rpx 28rpx rgba(87,58,136,.28);display:flex;flex-direction:column;align-items:center;justify-content:center;animation:orb-breathe 3.4s ease-in-out infinite;transition:transform .2s}
.ai-orb:active{transform:scale(.92)}.ai-orb.selected{box-shadow:0 0 0 5rpx #e9ddff,0 8rpx 28rpx rgba(87,58,136,.28)}.spark{font-size:32rpx;line-height:1}.ai-label{font-size:24rpx;font-weight:700;margin-top:4rpx}.ai-copy{font-size:20rpx;color:#695283;font-weight:600}
@keyframes orb-breathe{0%,100%{box-shadow:0 8rpx 24rpx rgba(87,58,136,.24)}50%{box-shadow:0 8rpx 34rpx rgba(87,58,136,.4)}}
</style>
