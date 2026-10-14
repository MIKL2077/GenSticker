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
.status-message{position:fixed;bottom:calc(210rpx + env(safe-area-inset-bottom));left:50%;transform:translateX(-50%) translateY(12rpx);background:#3a3042;color:#fff;padding:20rpx 30rpx;border-radius:24rpx;box-shadow:0 8rpx 26rpx rgba(34,22,45,.16);transition:transform .2s,opacity .2s;z-index:4000;opacity:0;font-size:23rpx;line-height:1.6;max-width:85%;text-align:center;pointer-events:none}
.status-message.show{transform:translateX(-50%) translateY(0);opacity:1}
</style>
