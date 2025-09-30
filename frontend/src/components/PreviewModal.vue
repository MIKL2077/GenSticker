<template>
  <view v-if="show" class="preview-modal">
    <view class="preview-content">
      <view class="preview-header">
        <text class="preview-title">表情包预览</text>
        <button class="close-btn" @click="$emit('close')">✕</button>
      </view>
      <view v-if="isGenerating" class="generating-container">
        <view class="loading-spinner"></view>
        <text class="loading-text">正在生成中...</text>
      </view>
      <view v-else-if="image" class="meme-result">
        <image :src="image" class="meme-image" mode="aspectFit" />
        <view class="meme-actions">
          <button class="btn btn-secondary" @click="$emit('save')">保存到相册</button>
          <button class="btn btn-primary" @click="$emit('share')">分享</button>
        </view>
      </view>
    </view>
  </view>
</template>

<script>
export default {
  name: 'PreviewModal',
  props: {
    show: { type: Boolean, required: true },
    isGenerating: { type: Boolean, required: true },
    image: { type: String, default: '' },
  },
  emits: ['close', 'save', 'share']
}
</script>

<style scoped>
.preview-modal { position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,.8); display:flex; align-items:center; justify-content:center; z-index:2000 }
.preview-content { background:#fff; border-radius:20rpx; width:90%; max-width:600rpx; max-height:80%; overflow:hidden; position:relative }
.preview-header { display:flex; justify-content:space-between; align-items:center; padding:30rpx; border-bottom:2rpx solid #eee }
.preview-title { font-size:32rpx; font-weight:bold; color:#333 }
.generating-container { padding:80rpx 40rpx; text-align:center }
.loading-spinner { width:80rpx; height:80rpx; border:6rpx solid #f3f3f3; border-top:6rpx solid #ff6b6b; border-radius:50%; animation:spin 1s linear infinite; margin:0 auto 30rpx }
@keyframes spin { 0%{ transform:rotate(0deg)} 100%{ transform:rotate(360deg)} }
.loading-text { font-size:28rpx; color:#666 }
.meme-result { padding:40rpx }
.meme-image { width:100%; max-height:400rpx; border-radius:16rpx; margin-bottom:30rpx }
.meme-actions { display:flex; gap:20rpx }
.btn { flex:1; padding:24rpx; border:none; border-radius:40rpx; font-size:28rpx; font-weight:bold; transition:all .3s ease }
.btn-primary { background:linear-gradient(45deg, #ff6b6b, #ff8e53); color:#fff }
.btn-secondary { background:#f8f9fa; color:#666; border:2rpx solid #ddd }
</style> 