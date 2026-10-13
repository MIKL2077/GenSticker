<template>
  <view class="template-container">
    <button v-if="currentPage > 1" class="nav-btn nav-left" @click="$emit('prev')">‹</button>
    <view v-if="loading && !templates.some(t => t.previewImage)" class="template-grid">
      <view v-for="n in 9" :key="n" class="template-item skeleton"><view class="skeleton-image" /><view class="skeleton-text" /></view>
    </view>
    <view v-else class="template-grid">
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
    loading: { type: Boolean, default: false },
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
.template-grid { display:grid; grid-template-columns: repeat(3, 1fr); gap:16rpx; flex:1; margin:0 10rpx }
.template-item { background:#fff; border-radius:24rpx; padding:18rpx 10rpx; text-align:center; box-shadow:0 4rpx 14rpx rgba(120,65,32,.06); transition:all .3s ease; border:4rpx solid transparent; min-height:160rpx; display:flex; flex-direction:column; align-items:center; justify-content:center }
.template-item.selected { border-color:#ff6b6b; background:#fff5f5 }
.template-preview { width:108rpx; height:108rpx; border-radius:8rpx; margin-bottom:16rpx }
.template-emoji { font-size:48rpx; margin-bottom:16rpx; display:block }
.template-name { font-size:23rpx; color:#51413a; font-weight:500; display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; max-width:100% }
.skeleton { min-height:120rpx }.skeleton-image { width:56rpx; height:56rpx; border-radius:10rpx; background:#f7f7f7; margin-bottom:16rpx }.skeleton-text { width:110rpx; height:16rpx; border-radius:12rpx; background:#f7f7f7 }
</style>
