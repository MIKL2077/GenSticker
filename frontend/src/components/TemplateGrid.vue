<template>
  <view class="template-container">
    <button v-if="currentPage > 1" class="nav-btn nav-left" @click="$emit('prev')">‹</button>
    <view v-if="loading && !templates.length" class="template-grid">
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
        <view v-else class="preview-placeholder" />
        <text class="template-name">{{ template.name || template.key }}</text>
        <text class="input-hint">{{ template.inputHint || inputSummary(template) }}</text><text v-if="template.heat" class="heat-label">✦ {{ template.heat }}</text>
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
  emits: ['select', 'prev', 'next'],
  methods:{inputSummary(t){const images=Number(String(t.imageCount||'0-0').split('-').pop());const texts=Number(String(t.textCount||'0-0').split('-').pop());return images&&texts?'图片 + 文字':images?'上传图片':texts?'写点文字':'直接生成'}}
}
</script>

<style scoped>
.template-container{position:relative}.template-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16rpx}.template-item{position:relative;min-width:0;background:#fff;border:2rpx solid #f0e7dc;border-radius:28rpx;padding:18rpx 10rpx 16rpx;display:flex;flex-direction:column;align-items:center;transition:transform .16s;animation:ui-enter .24s ease-out both}.template-item:active{transform:scale(.96)}.template-item.selected{border-color:var(--accent);background:#fff5ed}.template-preview,.preview-placeholder{width:100%;height:142rpx;border-radius:14rpx;margin-bottom:14rpx}.preview-placeholder,.skeleton-image{background:#f3f1eb}.template-name{font-size:25rpx;font-weight:650;color:var(--ink);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:100%}.input-hint{color:#92968e;font-size:20rpx;margin-top:5rpx;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:100%}.heat-label{font-size:19rpx;color:#bc7859;margin-top:8rpx}.nav-btn{position:absolute;top:40%;width:52rpx;height:88rpx;border-radius:22rpx;color:var(--accent-dark);background:#fff8ef;border:2rpx solid var(--line);font-size:42rpx;line-height:80rpx;padding:0;z-index:2}.nav-left{left:-20rpx}.nav-right{right:-20rpx}.skeleton{min-height:230rpx}.skeleton-image{width:100%;height:142rpx;border-radius:16rpx}.skeleton-text{height:20rpx;width:70%;background:#f3f1eb;margin-top:18rpx;border-radius:10rpx}
.template-grid{gap:18rpx}.template-item{border:2rpx solid #fff;border-radius:30rpx;padding:15rpx 10rpx 20rpx;box-shadow:0 6rpx 0 #efe9e2,0 10rpx 18rpx rgba(64,42,94,.035);background:linear-gradient(145deg,#fff,#fefefd);animation:ui-enter .35s both}.template-item:nth-child(3n+2){animation-delay:.035s}.template-item:nth-child(3n){animation-delay:.07s}.template-item:active{transform:translateY(5rpx) rotate(-2deg)}.template-item.selected{background:#fbf4ed;border-color:#e1b4a4}.template-preview{height:145rpx;border-radius:20rpx;background:#fff}.template-name{font-size:25rpx;font-weight:750}.input-hint{color:#aaa39a}.heat-label{color:#c7907c}.nav-btn{background:#fff;border-color:#fff;color:#a29689;box-shadow:0 4rpx 0 #ede5dc}.preview-placeholder,.skeleton-image,.skeleton-text{background:#f6f2ee}
.skeleton-image,.preview-placeholder{position:relative;overflow:hidden}.skeleton-image:after,.preview-placeholder:after{content:'';position:absolute;inset:0;background:linear-gradient(100deg,transparent,rgba(255,255,255,.75),transparent);animation:ui-shimmer 1.8s ease-in-out infinite}.template-item:nth-child(3n+2){animation-delay:.055s}.template-item:nth-child(3n){animation-delay:.1s}.template-item.selected{animation:ui-pop .3s ease-out both}.template-preview{animation:ui-reveal .3s ease-out both}
</style>
