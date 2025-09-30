<template>
  <view class="header">
    <view class="logo">🎭</view>
    <text class="app-title">表情包生成器</text>
    <text class="app-subtitle">轻松制作专属表情包</text>
    <slot />
  </view>
</template>

<script>
export default { name: 'AppHeader' }
</script>

<style scoped>
.header { text-align: center; margin-bottom: 40rpx; }
.logo {
  width: 120rpx; height: 120rpx; background: linear-gradient(45deg, #ff6b6b, #ff8e53);
  border-radius: 30rpx; display: flex; align-items: center; justify-content: center;
  font-size: 60rpx; margin: 0 auto 30rpx; box-shadow: 0 10rpx 30rpx rgba(255, 107, 107, 0.3);
  animation: bounce 2s infinite;
}
@keyframes bounce { 0%,20%,50%,80%,100%{transform:translateY(0);} 40%{transform:translateY(-16rpx);} 60%{transform:translateY(-8rpx);} }
.app-title { color:#333; font-size:44rpx; font-weight:bold; margin-bottom:10rpx; display:block; }
.app-subtitle { color:#666; font-size:28rpx; display:block; }
</style> 