<template>
  <view class="library-page" :class="{'motion-paused':!sceneActive}">
    <view class="library-header fx-enter"><button class="back" @click="back">‹ 返回</button><text class="title">{{ isHistory ? '浏览历史' : '收藏模板' }}</text><button v-if="isHistory && records.length" class="clear" @click="confirmClear">清空</button></view>
    <text class="description">{{ isHistory ? '最近浏览过的模板，点击可继续制作' : '收藏的模板，随时回来制作' }}</text>
    <view v-if="!records.length" class="empty"><text class="empty-icon fx-drift">{{ isHistory ? '🕘' : '⭐' }}</text><text>{{ isHistory ? '还没有浏览记录' : '还没有收藏模板' }}</text><text class="empty-hint">{{ isHistory ? '打开一个模板，它就会出现在这里' : '在模板详情中点击收藏即可添加' }}</text><button class="home" @click="goHome">去首页</button></view>
    <view v-else class="records">
      <view v-for="record in visibleRecords" :key="record.key" class="record">
        <view class="record-main" @click="open(record.key)"><image v-if="details[record.key]?.previewImage" class="thumbnail" :src="details[record.key].previewImage" mode="aspectFit" /><view v-else class="thumbnail" /><view class="record-copy"><text class="record-name">{{ details[record.key]?.name || record.key }}</text><text class="record-meta">{{ details[record.key]?.unavailable ? '模板暂时不可用' : (isHistory ? formatTime(record.visited_at) : '点击继续制作') }}</text></view></view>
        <button v-if="!isHistory" class="remove" @click="remove(record.key)">取消收藏</button>
      </view>
      <button v-if="visibleRecords.length < records.length" class="more" @click="limit += 20">加载更多</button>
    </view>
    <button v-if="syncError" class="sync-message" @click="syncLibrary">{{ syncError }} · 点击重试</button>
    <generation-notice/><first-use-guide />
  </view>
</template>
<script>
import {shareCard} from '@/services/shareCard'
import GenerationNotice from '@/components/GenerationNotice.vue'
import FirstUseGuide from '@/components/FirstUseGuide.vue'
import { ref, computed, watch } from 'vue'
import { onLoad, onShow, onHide,onShareAppMessage} from '@dcloudio/uni-app'
import { useLibrary } from '@/composables/useLibrary'
import { getTemplateInfo, getTemplatePreviewPath } from '@/services/memeService'
export default {
  components:{GenerationNotice,FirstUseGuide},
  setup() {
    onShareAppMessage(()=>shareCard())
    const sceneActive=ref(true)
    onHide(()=>{sceneActive.value=false})
    const account = useLibrary(), mode = ref('history'), details = ref({}), limit = ref(20)
    const isHistory = computed(() => mode.value === 'history')
    const records = computed(() => isHistory.value ? account.library.value.history : account.library.value.favorite_keys.map(key => ({ key })))
    const visibleRecords = computed(() => records.value.slice(0, limit.value))
    onLoad(options => { mode.value = options.mode === 'favorites' ? 'favorites' : 'history' })
    onShow(() => {sceneActive.value=true;account.syncLibrary()})
    watch(visibleRecords, async list => {
      await Promise.allSettled(list.filter(r => !details.value[r.key]).map(async r => {
        try {
          const info = await getTemplateInfo(r.key)
          details.value[r.key] = { name: info.keywords?.[0] || info.key }
          try { details.value[r.key].previewImage = await getTemplatePreviewPath(r.key) } catch (_) {}
        }
        catch (_) { details.value[r.key] = { name: r.key, unavailable: true } }
      }))
    }, { immediate: true })
    const open = key => {
      if (details.value[key]?.unavailable) return uni.showToast({ title: '这个模板暂时不可用', icon: 'none' })
      uni.setStorageSync('gensticker.open-template', key); uni.switchTab({ url: '/pages/index/index' })
    }
    const confirmClear = () => uni.showModal({ title: '清空浏览历史', content: '清空后可通过重新浏览模板添加记录。收藏不会被删除。', success: r => { if (r.confirm) account.clearHistory() } })
    return { sceneActive, ...account, mode, isHistory, records, visibleRecords, details, limit, open, confirmClear,
      remove: key => account.toggleFavorite(key),
      formatTime: t => new Date(t).toLocaleString(), back: () => uni.navigateBack(), goHome: () => uni.switchTab({ url: '/pages/index/index' }) }
  },
}
</script>
<style scoped>
.library-page { min-height:100vh; padding:calc(100rpx + env(safe-area-inset-top)) 28rpx 48rpx; background:var(--paper); box-sizing:border-box }.library-header { display:flex; align-items:center; gap:18rpx; margin-bottom:24rpx }.back,.clear { margin:0; padding:10rpx; color:var(--accent-dark); font-size:24rpx; line-height:1.5 }.title { flex:1; font-size:34rpx; font-weight:700; color:var(--ink) }.description { color:#888; font-size:24rpx }.records { margin-top:30rpx }.record { background:white; border-radius:24rpx; padding:22rpx; margin-bottom:18rpx; display:flex; align-items:center; box-shadow:0 4rpx 14rpx rgba(0,0,0,.04) }.record-main { display:flex; align-items:center; flex:1; min-width:0 }.thumbnail { width:100rpx; height:100rpx; margin-right:22rpx; background:#fafafa; border-radius:12rpx }.record-copy { flex:1; min-width:0 }.record-name { display:block; color:var(--ink); font-size:28rpx; font-weight:600 }.record-meta { display:block; color:#999; font-size:20rpx; margin-top:10rpx }.remove { color:var(--accent-dark); font-size:20rpx; padding:10rpx; margin:0; line-height:1.5 }.empty { padding:100rpx 24rpx; display:flex; flex-direction:column; align-items:center; gap:22rpx; color:#666; font-size:28rpx }.empty-icon { font-size:70rpx }.empty-hint { font-size:23rpx; color:#999; text-align:center }.home { background:var(--accent); border-radius:30rpx; color:white; padding:12rpx 46rpx; font-size:26rpx; margin-top:22rpx }.more,.sync-message { font-size:24rpx; color:var(--accent-dark) }
.record{border:2rpx solid var(--line);box-shadow:none;animation:ui-enter .23s ease-out}.thumbnail{width:120rpx;height:120rpx;border-radius:24rpx}.back,.clear,.remove{min-height:80rpx;display:flex;align-items:center}.back{background:var(--peach);border-radius:22rpx;padding:12rpx 20rpx}.library-page{padding-top:calc(105rpx + env(safe-area-inset-top))}.title{font-size:38rpx}.record-name{font-size:28rpx}.record-meta{font-size:22rpx;color:#8f998c}.empty{background:#f2eadc;border-radius:32rpx;margin-top:30rpx}.home{min-height:90rpx;padding:22rpx 40rpx;border-radius:24rpx;line-height:1.5}
.record{border:3rpx solid #fff;box-shadow:0 6rpx 0 #f0e9e1;border-radius:30rpx}.record-meta{color:#b8afa4}.empty{background:linear-gradient(135deg,#fbf5ee,#faf1e7);border:3rpx solid white;box-shadow:0 7rpx 0 #efe4d7}.home{background:linear-gradient(135deg,#e7b3a0,#c68973);box-shadow:0 6rpx 0 #b3684d;color:white}.empty-icon{text-shadow:0 5rpx 0 rgba(155,130,187,.2)}
.record:nth-child(2){animation-delay:.04s}.record:nth-child(3){animation-delay:.08s}.record:active{transform:translateY(3rpx)}.record{transition:transform .18s ease}.thumbnail{animation:ui-reveal .3s ease-out both}
</style>
