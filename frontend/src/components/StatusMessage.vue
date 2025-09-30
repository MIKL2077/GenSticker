<template>
  <view v-if="message" class="status-message" :class="{ 'show': show }">{{ message }}</view>
</template>

<script>
export default {
  name: 'StatusMessage',
  props: {
    message: { type: String, default: '' },
    show: { type: Boolean, default: false },
  }
}
</script>

<style scoped>
.status-message { position:fixed; top:40rpx; left:50%; transform:translateX(-50%) translateY(-100rpx); background:#4caf50; color:#fff; padding:30rpx 40rpx; border-radius:16rpx; box-shadow:0 8rpx 24rpx rgba(0,0,0,.2); transition:transform .3s ease; z-index:1000; margin-top:env(safe-area-inset-top) }
.status-message.show { transform:translateX(-50%) translateY(0) }
</style> 