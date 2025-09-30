<template>
  <view class="template-container">
    <button v-if="currentPage > 1" class="nav-btn nav-left" @click="$emit('prev')">‹</button>
    <view class="template-grid">
      <view 
        v-for="template in templates" 
        :key="template.key"
        class="template-item"
        :class="{ 'selected': selectedTemplate === template.key }"
        @click="$emit('select', template.key)"
      >
        <image v-if="template.previewImage" :src="template.previewImage" class="template-preview" mode="aspectFit" />
        <text v-else class="template-emoji"></text>
        <text class="template-name">{{ template.name || template.key }}</text>
      </view>
    </view>
    <button v-if="currentPage < totalPages" class="nav-btn nav-right" @click="$emit('next')">›</button>
  </view>
</template>

<script>
export default {
  name: 'TemplateGrid',
  props: {
    templates: { type: Array, required: true },
    selectedTemplate: { type: String, default: '' },
    currentPage: { type: Number, required: true },
    totalPages: { type: Number, required: true },
  },
  emits: ['select', 'prev', 'next']
}
</script>

<style scoped>
.template-container { position:relative; display:flex; align-items:center }
.nav-btn { position:absolute; width:60rpx; height:60rpx; background:rgba(255,255,255,.9); border:none; border-radius:50%; font-size:32rpx; color:#666; display:flex; align-items:center; justify-content:center; box-shadow:0 4rpx 12rpx rgba(0,0,0,.15); transition:all .3s ease; z-index:10 }
.nav-left { left:-30rpx }
.nav-right { right:-30rpx }
.template-grid { display:grid; grid-template-columns: repeat(3, 1fr); gap:20rpx; flex:1; margin:0 10rpx }
.template-item { background:#fff; border-radius:24rpx; padding:30rpx; text-align:center; box-shadow:0 4rpx 16rpx rgba(0,0,0,.1); transition:all .3s ease; border:4rpx solid transparent; min-height:160rpx; display:flex; flex-direction:column; align-items:center; justify-content:center }
.template-item.selected { border-color:#ff6b6b; background:#fff5f5 }
.template-preview { width:60rpx; height:60rpx; border-radius:8rpx; margin-bottom:16rpx }
.template-emoji { font-size:48rpx; margin-bottom:16rpx; display:block }
.template-name { font-size:24rpx; color:#666; font-weight:500; display:block; word-break: break-all }
</style> 