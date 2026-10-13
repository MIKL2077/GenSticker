<template>
  <view class="my-page">
    <view class="profile-panel">
      <view class="profile-header">
        <button class="avatar" :loading="loggingIn" @click="login" aria-label="微信登录">👤</button>
        <text class="name">{{ session ? session.profile.name : '未登录用户' }}</text>
        <text class="hint">{{ session ? '已登录，收藏与历史可跨设备同步' : '点击上方头像登录' }}</text>
        <text v-if="!session" class="guest-note">无需登录也能使用本机历史与收藏</text>
      </view>
      <text class="section-title">🎯 常用功能</text>
      <view class="feature-grid">
        <button class="feature-card history-card" @click="openLibrary('history')">
          <text class="feature-title">历史记录</text><view class="feature-desc"><text class="feature-icon">🕘</text><text>浏览过的表情模板</text></view><text v-if="historyCount" class="count">{{ historyCount }} 个模板</text>
        </button>
        <button class="feature-card favorites-card" @click="openLibrary('favorites')">
          <text class="feature-title">收藏模板</text><view class="feature-desc"><text class="feature-icon">⭐</text><text>我收藏的表情模板</text></view><text v-if="favoritesCount" class="count">{{ favoritesCount }} 个模板</text>
        </button>
      </view>
      <button v-if="syncError" class="sync-message" @click="syncLibrary">{{ syncError }} · 点击重试</button>
      <button v-if="session" class="logout" @click="signOut">退出登录</button>
    </view>
    <bottom-tabs active="my" />
  </view>
</template>
<script>
import { onShow } from '@dcloudio/uni-app'
import BottomTabs from '@/components/BottomTabs.vue'
import { useLibrary } from '@/composables/useLibrary'
export default {
  components: { BottomTabs },
  setup() {
    const account = useLibrary()
    onShow(() => { uni.hideTabBar({ animation: false }); account.syncLibrary() })
    const login = async () => {
      if (account.session.value) return
      try { await account.loginWeChat(); uni.showToast({ title: '登录成功', icon: 'success' }) }
      catch (e) { uni.showModal({ title: '微信登录', content: e.message || e.errMsg || '登录失败，请重试', showCancel: false }) }
    }
    const signOut = async () => {
      try { await account.logout(); uni.showToast({ title: '已退出登录', icon: 'none' }) }
      catch (_) { uni.showToast({ title: '退出失败，请联网重试', icon: 'none' }) }
    }
    return { ...account, login, signOut, openLibrary: mode => uni.navigateTo({ url: `/pages/library/index?mode=${mode}` }) }
  },
}
</script>
<style scoped>
.my-page { min-height:100vh; padding:calc(100rpx + env(safe-area-inset-top)) 18rpx 180rpx; background:linear-gradient(135deg,#ff6b6b,#ffa500); box-sizing:border-box }
.profile-panel { min-height:calc(100vh - 200rpx); border-radius:30rpx 30rpx 0 0; background:#fffaf7; padding:48rpx 18rpx; box-sizing:border-box }
.profile-header { text-align:center; padding:8rpx 0 50rpx }.avatar { width:128rpx; height:128rpx; display:flex; align-items:center; justify-content:center; padding:0; font-size:56rpx; background:linear-gradient(45deg,#ff6b6b,#ff8e53); border-radius:34rpx; box-shadow:0 12rpx 30rpx rgba(255,107,107,.2); margin:0 auto 22rpx }
.name { display:block; font-size:34rpx; font-weight:700; color:#333 }.hint { display:block; font-size:22rpx; color:#888; margin-top:18rpx }.guest-note { display:block; font-size:20rpx; color:#aaa; margin-top:12rpx }
.section-title { display:block; font-size:28rpx; font-weight:700; margin:8rpx 0 20rpx; color:#333 }.feature-grid { display:flex; gap:18rpx }
.feature-card { flex:1; min-width:0; margin:0; padding:28rpx 24rpx; border-radius:26rpx; background:white; text-align:left; line-height:1.5; box-shadow:0 6rpx 16rpx rgba(0,0,0,.06) }.feature-title { display:block; font-size:27rpx; font-weight:600; color:#333 }.feature-desc { display:flex; align-items:center; gap:16rpx; color:#999; font-size:20rpx; margin-top:22rpx }.feature-icon { font-size:38rpx }.count { display:block; color:#ff7474; font-size:20rpx; margin-top:12rpx }.logout { margin-top:50rpx; color:#888; font-size:24rpx }.sync-message { font-size:22rpx; color:#a85b22; margin-top:24rpx; line-height:1.6; padding:16rpx }
</style>
