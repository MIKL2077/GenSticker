<template>
  <view v-if="show" class="template-detail-modal">
    <view class="detail-content">
      <view class="detail-header">
        <text class="detail-title">模板详情</text>
        <button class="close-btn" @click="$emit('close')">✕</button>
      </view>
      <view class="detail-body">
        <view class="example-section">
          <text class="detail-label">示例图</text>
          <image :src="detail?.previewImage || '/static/placeholder.png'" class="example-image" mode="aspectFit" />
        </view>
        <view class="template-info-section">
          <text class="detail-label">模板信息</text>
          <view class="info-item"><text class="info-key">名称：</text><text class="info-value">{{ detail?.name || detail?.key }}</text></view>
          <view class="info-item"><text class="info-key">关键词：</text><text class="info-value">{{ (detail?.keywords||[]).join(', ') || '无' }}</text></view>
          <view class="info-item"><text class="info-key">标签：</text><text class="info-value">{{ (detail?.tags||[]).join(', ') || '无' }}</text></view>
        </view>
        <view class="requirements-section">
          <text class="detail-label">输入要求</text>
          <view class="requirements-list">
            <text class="requirement-text">📷 图片数量：{{ detail?.imageCount || '0-0' }} 张</text>
            <text class="requirement-text">📝 文本数量：{{ detail?.textCount || '0-0' }} 个</text>
            <text v-if="detail?.defaultTexts?.length" class="requirement-text">默认文本：{{ detail.defaultTexts.join(', ') }}</text>
          </view>
        </view>
        <view v-if="imageInputCount > 0" class="image-input-section">
          <text class="detail-label">图片上传</text>
          <view class="image-upload-area" @click="$emit('chooseImages')">
            <view class="upload-icon">📷</view>
            <text class="upload-text">{{ imageUploadText }}</text>
          </view>
          <view v-if="templateImages.length > 0" class="template-images-grid">
            <view v-for="(image, index) in templateImages" :key="`template-image-${index}`" class="template-image-item">
              <image :src="image" class="template-image" mode="aspectFill" />
              <button class="remove-image-btn" @click.stop="$emit('removeImage', index)">✕</button>
            </view>
          </view>
        </view>
        <view v-if="textMax > 0" class="text-input-section">
          <text class="detail-label">文本输入（至少{{ textRange.min }}个，至多{{ textRange.max }}个）</text>
          <view class="text-input-grid">
            <view v-for="(val, idx) in textInputs" :key="`template-text-${idx}`" class="text-input-item">
              <input class="text-input" type="text" :placeholder="getTextPlaceholder(idx)" v-model="textInputs[idx]" :maxlength="getTextMaxLength(idx)" />
            </view>
          </view>
        </view>
        <view class="detail-actions">
          <button class="btn btn-primary" :disabled="!canGenerate" @click="$emit('generate')">生成表情包</button>
          <button class="btn btn-secondary" @click="$emit('close')">取消</button>
        </view>
      </view>
    </view>
  </view>
</template>

<script>
export default {
  name: 'TemplateDetailModal',
  props: {
    show: { type: Boolean, required: true },
    detail: { type: Object, default: null },
    templateImages: { type: Array, default: () => [] },
    textInputs: { type: Array, default: () => [] },
    imageInputCount: { type: Number, default: 0 },
    imageUploadText: { type: String, default: '' },
    textRange: { type: Object, default: () => ({ min: 0, max: 0 }) },
    textMax: { type: Number, default: 0 },
    getTextPlaceholder: { type: Function, required: true },
    getTextMaxLength: { type: Function, required: true },
    canGenerate: { type: Boolean, default: false },
  },
  emits: ['close', 'chooseImages', 'removeImage', 'generate']
}
</script>

<style scoped>
.template-detail-modal { position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,.8); display:flex; align-items:center; justify-content:center; z-index:2000 }
.detail-content { background:#fff; border-radius:20rpx; width:90%; max-width:700rpx; max-height:80%; overflow:hidden; position:relative }
.detail-header { display:flex; justify-content:center; align-items:center; padding:30rpx; border-bottom:2rpx solid #eee }
.detail-title { font-size:32rpx; font-weight:bold; color:#333 }
.close-btn { position:absolute; top:16rpx; right:16rpx; width:72rpx; height:48rpx; background:#c62828; color:#fff; border:none; border-radius:12rpx; font-size:28rpx; display:flex; align-items:center; justify-content:center; box-shadow:0 2rpx 10rpx rgba(198,40,40,.3); z-index:10 }
.detail-body { padding:30rpx; max-height:600rpx; overflow-y:auto; position:relative; z-index:1 }
.example-section { margin-bottom:40rpx; text-align:center }
.detail-label { font-size:28rpx; font-weight:bold; color:#333; margin-bottom:20rpx; display:block }
.example-image { width:100%; max-height:300rpx; border-radius:16rpx; background:#f5f5f5 }
.template-info-section { margin-bottom:40rpx }
.info-item { display:flex; margin-bottom:16rpx }
.info-key { font-size:26rpx; color:#666; width:140rpx; flex-shrink:0 }
.info-value { font-size:26rpx; color:#333; flex:1 }
.requirements-list { display:flex; flex-direction:column; gap:12rpx }
.requirement-text { font-size:24rpx; color:#666; background:#f8f9fa; padding:16rpx 20rpx; border-radius:12rpx }
.image-input-section { margin-bottom:40rpx }
.image-upload-area { background:#f8f9fa; border:4rpx dashed #ddd; border-radius:20rpx; padding:40rpx; text-align:center; transition:all .3s ease }
.template-images-grid { display:grid; grid-template-columns: repeat(3, 1fr); gap:20rpx; margin-top:20rpx }
.template-image-item { position:relative; aspect-ratio:1; border-radius:16rpx; overflow:hidden; box-shadow:0 4rpx 12rpx rgba(0,0,0,.1) }
.template-image { width:100%; height:100%; border-radius:16rpx }
.remove-image-btn { position:absolute; top:8rpx; right:8rpx; width:40rpx; height:40rpx; background:rgba(255,0,0,.8); color:#fff; border:none; border-radius:50%; font-size:24rpx; display:flex; align-items:center; justify-content:center; box-shadow:0 2rpx 8rpx rgba(0,0,0,.3); transition:all .2s ease }
.text-input-section { margin-bottom:40rpx }
.text-input-grid { display:grid; grid-template-columns:1fr; gap:16rpx }
.text-input-item { background:#f8f9fa; border:2rpx solid #e5e7eb; border-radius:16rpx; padding:12rpx 16rpx }
.text-input { width:100%; font-size:26rpx; color:#333 }
.detail-actions { display:flex; gap:20rpx; margin-top:30rpx }
.btn { flex:1; padding:24rpx; border:none; border-radius:40rpx; font-size:28rpx; font-weight:bold; transition:all .3s ease }
.btn-primary { background:linear-gradient(45deg, #ff6b6b, #ff8e53); color:#fff }
.btn-secondary { background:#f8f9fa; color:#666; border:2rpx solid #ddd }
</style> 