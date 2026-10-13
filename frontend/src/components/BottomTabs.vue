<template>
  <view class="bottom-tabs">
    <button class="tab" :class="{ active: active === 'home' }" @click="go('home')"><text class="icon">🏠</text><text>首页</text></button>
    <button class="tab" :class="{ active: active === 'my' }" @click="go('my')"><text class="icon">👤</text><text>我的</text></button>
  </view>
</template>
<script>
import { onMounted } from 'vue'
export default {
  props: { active: String },
  setup() {
    onMounted(() => uni.hideTabBar({ animation: false, fail: () => {} }))
    return { go: tab => uni.switchTab({ url: tab === 'home' ? '/pages/index/index' : '/pages/my/index' }) }
  },
}
</script>
<style scoped>
.bottom-tabs { position:fixed; bottom:0; left:0; right:0; display:flex; gap:10rpx; background:white; padding:12rpx 16rpx calc(12rpx + env(safe-area-inset-bottom)); border-radius:24rpx 24rpx 0 0; z-index:100 }
.tab { flex:1; margin:0; border:2rpx solid transparent; border-radius:22rpx; background:#f7f8fa; color:#666; font-size:24rpx; line-height:1.5; padding:20rpx; display:flex; flex-direction:column; align-items:center; gap:6rpx }
.icon { font-size:36rpx }.tab.active { color:#ff6868; border-color:#ffd0d0; background:#fff7f7; font-weight:600 }
</style>
