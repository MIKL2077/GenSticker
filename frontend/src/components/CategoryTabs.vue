<template>
  <view class="category-tabs">
    <view
      v-for="category in categories"
      :key="category.key"
      class="category-tab"
      :class="{ 'active': selectedCategory === category.key }"
      @click="$emit('select', category.key)"
    >
      <text class="category-icon">{{ category.icon }}</text>
      <text class="category-name">{{ category.name }}</text>
      <text class="category-count">{{ category.count }}</text>
    </view>
  </view>
</template>

<script>
export default {
  name: 'CategoryTabs',
  props: {
    categories: { type: Array, required: true },
    selectedCategory: { type: String, required: true },
  },
  emits: ['select']
}
</script>

<style scoped>
.category-tabs { display:flex; background: rgba(255,255,255,0.9); border-radius:25rpx; padding:8rpx; margin-bottom:30rpx; box-shadow:0 4rpx 16rpx rgba(0,0,0,0.1); overflow:hidden; }
.category-tab { flex:1; display:flex; flex-direction:column; align-items:center; gap:6rpx; padding:20rpx 12rpx; border-radius:20rpx; transition:all .3s ease; position:relative; }
.category-tab.active { background:linear-gradient(45deg, #ff6b6b, #ff8e53); color:#fff; transform: translateY(-2rpx); box-shadow:0 4rpx 12rpx rgba(255,107,107,0.3) }
.category-icon { font-size:28rpx; display:block }
.category-name { font-size:22rpx; font-weight:500; display:block }
.category-count { font-size:18rpx; opacity:.8; display:block; background:rgba(0,0,0,.1); padding:4rpx 8rpx; border-radius:10rpx; min-width:32rpx; text-align:center }
.category-tab.active .category-count { background: rgba(255,255,255,.2) }
</style> 