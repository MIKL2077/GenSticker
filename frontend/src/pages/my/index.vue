<template>
  <view class="my-page">
    <view class="profile-panel">
      <view class="profile-header">
        <button class="avatar" :loading="loggingIn" @click="showLogin" :aria-label="session ? '编辑资料' : '微信登录'"><image v-if="session?.profile.avatarPath" :src="session.profile.avatarPath" class="profile-avatar" /><text v-else>👤</text></button>
        <text class="name">{{ session ? session.profile.name : '未登录用户' }}</text>
        <text class="hint">{{ session ? '已登录，收藏与历史可跨设备同步' : '点击上方头像登录' }}</text>
        <text v-if="!session" class="guest-note">登录后同步历史与收藏</text>
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
      <text class="analytics-note">模板点击与制作的去重计数用于热力榜，不记录照片或输入文字。</text>
    </view>
    <view v-if="loginVisible" class="login-mask" @click="closeLogin">
      <view class="login-dialog" @click.stop>
        <button class="dialog-close" :disabled="submitting" @click="closeLogin">×</button>
        <text class="login-title">{{ session ? '个人资料' : '微信登录' }}</text>
        <text class="login-subtitle">{{ session ? '设置头像与昵称' : '使用微信账号快速登录' }}</text>
        <text class="field-label">选择头像</text>
        <button class="choose-avatar" open-type="chooseAvatar" @chooseavatar="chooseAvatar"><image v-if="chosenAvatar || session?.profile.avatarPath" :src="chosenAvatar || session.profile.avatarPath" class="chosen-image" /><text v-else>📷</text></button>
        <text class="field-label">输入昵称</text>
        <input class="nickname" type="nickname" v-model="nickname" maxlength="32" placeholder="请输入昵称" @blur="onNickname" />
        <text v-if="loginError" class="login-error">{{ loginError }}</text>
        <button class="login-submit" :loading="submitting" :disabled="submitting" @click="login">{{ session ? '保存资料' : '一键登录' }}</button>
        <text class="login-note">头像与昵称由你主动选择，仅用于个人资料展示</text>
      </view>
    </view>
    <bottom-tabs active="my" />
  </view>
</template>
<script>
import { ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import BottomTabs from '@/components/BottomTabs.vue'
import { useLibrary } from '@/composables/useLibrary'
export default {
  components: { BottomTabs },
  setup() {
    const account = useLibrary()
    onShow(() => { uni.hideTabBar({ animation: false }); account.syncLibrary(); if (!account.session.value) account.prefetchLogin().catch(() => {}); if (uni.getStorageSync('gensticker.open-recommend')) { if (account.session.value) { uni.removeStorageSync('gensticker.open-recommend'); uni.navigateTo({url:'/pages/recommend/index'}) } else showLogin() } })
    const loginVisible = ref(false), nickname = ref(''), chosenAvatar = ref(''), loginError = ref(''), submitting = ref(false)
    let nextLibrary = ''
    const showLogin = () => { nickname.value = account.session.value?.profile.name || ''; chosenAvatar.value = ''; loginError.value = ''; loginVisible.value = true }
    const closeLogin = () => { if (!submitting.value) { loginVisible.value = false; nextLibrary = ''; uni.removeStorageSync('gensticker.open-recommend') } }
    const openLibrary = mode => {
      if (!account.session.value) { nextLibrary = mode; showLogin(); return }
      uni.navigateTo({ url: `/pages/library/index?mode=${mode}` })
    }
    const login = async () => {
      if (submitting.value) return
      const name = nickname.value.trim()
      if (!name) { loginError.value = '请先输入昵称'; return }
      submitting.value = true; loginError.value = ''
      try {
        if (!account.session.value) await account.loginWeChat()
        await account.saveProfile(name, chosenAvatar.value)
        loginVisible.value = false
        uni.showToast({ title: '已完成', icon: 'success' })
        const mode = nextLibrary; nextLibrary = ''
        if (uni.getStorageSync('gensticker.open-recommend')) { uni.removeStorageSync('gensticker.open-recommend'); uni.navigateTo({url:'/pages/recommend/index'}) } else if (mode) openLibrary(mode)
      } catch (e) { loginError.value = e.message || e.errMsg || '登录失败，请重试' }
      finally { submitting.value = false }
    }
    const signOut = async () => {
      try { await account.logout(); uni.showToast({ title: '已退出登录', icon: 'none' }) }
      catch (_) { uni.showToast({ title: '退出失败，请联网重试', icon: 'none' }) }
    }
    return { ...account, login, signOut, openLibrary, showLogin, closeLogin, loginVisible, nickname, chosenAvatar, loginError, submitting, chooseAvatar: e => { chosenAvatar.value = e.detail.avatarUrl }, onNickname: e => { nickname.value = e.detail.value } }
  },
}
</script>
<style scoped>
.feature-card{transition:transform .18s,box-shadow .18s;animation:profile-in .25s ease-out}.feature-card:active{transform:translateY(3rpx) scale(.97)}.avatar:active{transform:rotate(-5deg) scale(.95)}.login-dialog{animation:profile-in .23s ease-out}.analytics-note{display:block;text-align:center;font-size:19rpx;color:#b09c91;line-height:1.7;margin-top:44rpx;padding:0 16rpx}@keyframes profile-in{from{opacity:0;transform:translateY(16rpx)}to{opacity:1;transform:translateY(0)}}
.my-page { min-height:100vh; padding:calc(100rpx + env(safe-area-inset-top)) 18rpx 180rpx; background:linear-gradient(135deg,#ff6b6b,#ffa500); box-sizing:border-box }
.profile-panel { min-height:calc(100vh - 200rpx); border-radius:30rpx 30rpx 0 0; background:#fffaf7; padding:48rpx 18rpx; box-sizing:border-box }
.profile-header { text-align:center; padding:8rpx 0 50rpx }.avatar { width:128rpx; height:128rpx; display:flex; align-items:center; justify-content:center; padding:0; font-size:56rpx; background:linear-gradient(45deg,#ff6b6b,#ff8e53); border-radius:34rpx; box-shadow:0 12rpx 30rpx rgba(255,107,107,.2); margin:0 auto 22rpx }
.name { display:block; font-size:34rpx; font-weight:700; color:#333 }.hint { display:block; font-size:22rpx; color:#888; margin-top:18rpx }.guest-note { display:block; font-size:20rpx; color:#aaa; margin-top:12rpx }
.section-title { display:block; font-size:28rpx; font-weight:700; margin:8rpx 0 20rpx; color:#333 }.feature-grid { display:flex; gap:18rpx }
.feature-card { flex:1; min-width:0; margin:0; padding:28rpx 24rpx; border-radius:26rpx; background:white; text-align:left; line-height:1.5; box-shadow:0 6rpx 16rpx rgba(0,0,0,.06) }.feature-title { display:block; font-size:27rpx; font-weight:600; color:#333 }.feature-desc { display:flex; align-items:center; gap:16rpx; color:#999; font-size:20rpx; margin-top:22rpx }.feature-icon { font-size:38rpx }.count { display:block; color:#ff7474; font-size:20rpx; margin-top:12rpx }.logout { margin-top:50rpx; color:#888; font-size:24rpx }.sync-message { font-size:22rpx; color:#a85b22; margin-top:24rpx; line-height:1.6; padding:16rpx }

.profile-avatar { width:100%; height:100%; border-radius:34rpx }
.login-mask { position:fixed; inset:0; z-index:3000; background:rgba(30,25,23,.55); display:flex; align-items:center; justify-content:center; padding:32rpx; box-sizing:border-box }
.login-dialog { position:relative; width:100%; max-width:600rpx; border-radius:36rpx; background:white; padding:52rpx 38rpx 38rpx; box-sizing:border-box }
.dialog-close { position:absolute; top:16rpx; right:18rpx; margin:0; color:#999; font-size:40rpx; width:60rpx; padding:0; line-height:1.3; background:transparent }
.login-title { display:block; text-align:center; font-size:40rpx; font-weight:700; color:#302b28 }.login-subtitle { display:block; text-align:center; font-size:25rpx; color:#888; margin:16rpx 0 32rpx }
.field-label { display:block; color:#514741; font-size:26rpx; margin:24rpx 0 16rpx }.choose-avatar { width:130rpx; height:130rpx; border-radius:50%; padding:0; display:flex; justify-content:center; align-items:center; background:#f5f5f5; font-size:45rpx; margin:0 auto }.chosen-image { width:130rpx; height:130rpx; border-radius:50% }
.nickname { border:2rpx solid #ebe6e3; border-radius:18rpx; padding:0 22rpx; font-size:28rpx; height:88rpx; box-sizing:border-box; background:#fffaf7 }.login-submit { background:#07b963; color:white; border-radius:24rpx; margin-top:34rpx; font-size:30rpx; font-weight:600; line-height:2.8 }.login-note { display:block; margin-top:26rpx; text-align:center; font-size:21rpx; line-height:1.6; color:#999 }.login-error { display:block; color:#b43c2e; font-size:24rpx; margin-top:16rpx }
</style>
