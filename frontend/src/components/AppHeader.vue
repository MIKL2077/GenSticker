<template>
  <view class="header">
    <view class="logo"><text class="brand-mark">🎭</text><text class="brand-name">GenSticker</text></view>
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
  width: 140rpx; height: 140rpx; background: #fffaf7;
  border-radius: 22rpx; display: flex; flex-direction:column; align-items: center; justify-content: center;
  margin: 0 auto 38rpx; box-shadow: 0 8rpx 16rpx rgba(0,0,0,.12);
}
.brand-mark { font-size:48rpx }.brand-name { color:#063c50; font-size:22rpx; font-weight:800 }
@keyframes bounce { 0%,20%,50%,80%,100%{transform:translateY(0);} 40%{transform:translateY(-16rpx);} 60%{transform:translateY(-8rpx);} }
.app-title { color:#333; font-size:44rpx; font-weight:bold; margin-bottom:10rpx; display:block; }
.app-subtitle { color:#666; font-size:28rpx; display:block; }
.header{display:grid;grid-template-columns:112rpx 1fr;grid-template-rows:1fr 1fr;gap:4rpx 24rpx;text-align:left;position:relative;margin-bottom:32rpx}.logo{grid-row:1/3;width:112rpx;height:112rpx;margin:0;border-radius:28rpx;box-shadow:0 6rpx 20rpx rgba(112,52,27,.1)}.brand-mark{font-size:40rpx}.brand-name{font-size:17rpx}.app-title{grid-column:2;align-self:end;font-size:36rpx;margin:0;color:#432e29}.app-subtitle{grid-column:2;align-self:start;font-size:22rpx;color:#815443;padding-top:7rpx}
</style>
