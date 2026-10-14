<template>
  <view class="container">
    <app-header>
      <view class="floating-emoji" style="top: 10%; left: 10%; animation-delay: 0s;">😀</view>
      <view class="floating-emoji" style="top: 20%; right: 15%; animation-delay: 1s;">😂</view>
      <view class="floating-emoji" style="bottom: 30%; left: 5%; animation-delay: 2s;">🤣</view>
      <view class="floating-emoji" style="bottom: 20%; right: 10%; animation-delay: 0.5s;">😍</view>
    </app-header>

    <view class="heat-hero"><view class="hero-heading"><view><text class="hero-eyebrow">THE REACTION CLUB</text><text class="hero-title">今日，谁最有梗？</text></view><text class="hero-mark">✦</text></view><text class="hero-sub">大家的点击、收藏与制作，让好玩的表情浮上来</text><view class="spotlight"><view v-for="(item,index) in spotlight" :key="item.key" class="spotlight-card" @click="onSelectTemplate(item.key)"><text class="spotlight-rank">0{{ index+1 }}</text><image v-if="item.previewImage" :src="item.previewImage" mode="aspectFit" class="spotlight-image"/><text class="spotlight-name">{{ item.name }}</text><text class="spotlight-heat">{{ item.heat ? '热力 '+item.heat : '等你点燃' }}</text></view></view></view>
    <view class="meme-templates">
      <view class="template-header">
        <text class="section-title">🎭 选择表情模板</text>
        <view class="pagination-info">
          <text class="page-info">{{ currentPage }}/{{ totalPages }}</text>
          <view v-if="isLoadingTemplates" class="loading-indicator">
            <text class="loading-text">加载中...</text>
          </view>
        </view>
      </view>

      <category-tabs :categories="categories" :selected-category="selectedCategory" @select="onSelectCategory" />
      <view class="sort-row"><view class="sort-switch"><button :class="{chosen:sortMode==='hot'}" @click="changeSort('hot')">热力榜</button><button :class="{chosen:sortMode==='explore'}" @click="changeSort('explore')">全部探索</button></view><text class="sort-note">{{ sortMode==='hot' ? '近7日热度 · 新鲜反应' : '完整模板库' }}</text></view>
      <view v-if="loadError" class="load-error"><text>{{ loadError }}</text><button @click="retryTemplates">重试</button></view>

      <template-grid
        v-if="!loadError"
        :templates="currentPageTemplates"
        :selected-template="selectedTemplate"
        :current-page="currentPage"
        :total-pages="totalPages"
        :loading="isLoadingTemplates"
        @select="onSelectTemplate"
        @prev="prevPage"
        @next="nextPage"
      />
      <view v-if="!loadError" class="page-numbers">
        <button v-if="currentPage > 1" class="page-button" @click="prevPage">‹</button>
        <button v-for="number in pageNumbers" :key="number" class="page-button" :class="{ active: number === currentPage }" @click="currentPage = number">{{ number }}</button>
        <button v-if="currentPage < totalPages" class="page-button" @click="nextPage">›</button>
      </view>
    </view>

    <template-detail-modal
      :show="showTemplateDetail"
      :detail="selectedTemplateDetail"
      :template-images="templateImages"
      :text-inputs="textInputs"
      :image-input-count="getImageInputCount()"
      :image-upload-text="getImageUploadText()"
      :text-range="getTextInputRange()"
      :text-max="getTextInputMax()"
      :get-text-placeholder="getTextPlaceholder"
      :get-text-max-length="getTextMaxLength"
      :can-generate="isTemplateInputValid()"
      :favorite="isFavorite(selectedTemplate)"
      @favorite="favoriteTemplate"
      @chooseImages="chooseImagesForTemplate"
      @removeImage="removeTemplateImage"
      @generate="onGenerate"
      @close="closeTemplateDetail"
    />

    <preview-modal
      :show="showPreview"
      :is-generating="isGenerating"
      :image="generatedMeme"
      @close="closePreview"
      @save="saveMeme"
      @share="shareMeme"
    />

    <status-message :message="statusMessage" :show="showStatus" />
    <bottom-tabs active="home" />
  </view>
</template>

<script>
import { onMounted, watch, ref, computed } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import AppHeader from '@/components/AppHeader.vue'
import CategoryTabs from '@/components/CategoryTabs.vue'
import TemplateGrid from '@/components/TemplateGrid.vue'
import TemplateDetailModal from '@/components/TemplateDetailModal.vue'
import PreviewModal from '@/components/PreviewModal.vue'
import StatusMessage from '@/components/StatusMessage.vue'
import BottomTabs from '@/components/BottomTabs.vue'
import { useLibrary } from '@/composables/useLibrary'
import { trackTemplate } from '@/services/popularityService'

import { useStatusMessage } from '@/composables/useStatusMessage'
import { useTemplateData } from '@/composables/useTemplateData'
import { useTemplateInput } from '@/composables/useTemplateInput'
import { useMemeGeneration } from '@/composables/useMemeGeneration'

export default {
  name: 'Index',
  components: { AppHeader, CategoryTabs, TemplateGrid, TemplateDetailModal, PreviewModal, StatusMessage, BottomTabs },
  setup() {
    const { statusMessage, showStatus, showStatusMessage } = useStatusMessage()
    const account = useLibrary()

    const {
      isLoadingTemplates,
      loadError,
      selectedCategory,
      categories,
      currentPage,
      totalPages,
      currentPageTemplates,
      sortMode,
      spotlight,
      fetchMemeCategories,
      ensurePageLoaded,
      prefetchAdjacent,
      selectCategory,
      prevPage,
      nextPage,
      fetchMemeInfo,
      fetchMemePreview,
    } = useTemplateData(showStatusMessage)

    const { templateImages, textInputs, selectedTemplateDetail, getImageInputCount, getImageUploadText, getTextInputRange, getTextInputMax, getTextPlaceholder, getTextMaxLength, initializeTemplateInputs, isTemplateInputValid, chooseImagesForTemplate, removeTemplateImage, resetInputs } = useTemplateInput()

    const { showPreview, isGenerating, generatedMeme, generateFromTemplate, closePreview, saveMeme, shareMeme } = useMemeGeneration(showStatusMessage)

    const selectedTemplate = ref('')
    const showTemplateDetail = ref(false)

    const onSelectCategory = async (key) => {
      await selectCategory(key)
    }

    const onSelectTemplate = async (key) => {
      selectedTemplate.value = key
      const detail = (await fetchMemeInfo(key)) || null
      if (detail && !detail.previewImage) fetchMemePreview(key)
      if (!detail) { showStatusMessage('模板暂时不可用，请稍后重试'); return }
      account.recordVisit(key)
      trackTemplate(key, 'click')
      selectedTemplateDetail.value = detail
      initializeTemplateInputs(detail)
      showTemplateDetail.value = true
    }

    const onGenerate = async () => {
      if (!isTemplateInputValid()) {
        showStatusMessage('请完整填写所需信息！')
        return
      }
      const texts = (textInputs.value || []).map(t => (t || '').trim()).filter(Boolean)
      await generateFromTemplate(selectedTemplate.value, templateImages.value, texts, {})
      showTemplateDetail.value = false
      selectedTemplateDetail.value = null
      resetInputs()
    }

    const closeTemplateDetail = () => {
      showTemplateDetail.value = false
      selectedTemplateDetail.value = null
      resetInputs()
    }

    const favoriteTemplate = () => {
      try { const saved = account.toggleFavorite(selectedTemplate.value); if (saved && !account.session.value) trackTemplate(selectedTemplate.value,'favorite'); showStatusMessage(saved ? '已收藏模板' : '已取消收藏') }
      catch (e) { showStatusMessage(e.message) }
    }
    const pageNumbers = computed(() => {
      const start = Math.max(1, Math.min(currentPage.value - 2, totalPages.value - 4))
      return Array.from({ length: Math.min(5, totalPages.value) }, (_, i) => start + i)
    })
    const retryTemplates = async () => { await fetchMemeCategories(); await ensurePageLoaded(selectedCategory.value, currentPage.value) }
    onShow(() => {
      uni.hideTabBar({ animation: false, fail: () => {} })
      const key = uni.getStorageSync('gensticker.open-template')
      if (key) { uni.removeStorageSync('gensticker.open-template'); onSelectTemplate(key) }
    })

    watch([selectedCategory, currentPage, sortMode], async ([cat, page]) => {
      await ensurePageLoaded(cat, page)
      prefetchAdjacent(cat, page)
    })

    onMounted(async () => {
      try {
        await fetchMemeCategories()
        await ensurePageLoaded(selectedCategory.value, 1)
        prefetchAdjacent(selectedCategory.value, 1)
      } catch (e) {
        showStatusMessage('初始化失败，请刷新页面重试')
      }
    })

    return {
      // 状态消息
      statusMessage,
      showStatus,
      // 分类/分页
      isLoadingTemplates,
      loadError,
      openRecommend: () => uni.navigateTo({ url: '/pages/recommend/index' }),
      pageNumbers,
      retryTemplates,
      favoriteTemplate,
      isFavorite: account.isFavorite,
      selectedCategory,
      categories,
      currentPage,
      totalPages,
      currentPageTemplates,
      sortMode,
      spotlight,
      changeSort: mode => { sortMode.value = mode; currentPage.value = 1 },
      prevPage,
      nextPage,
      // 模板选择
      selectedTemplate,
      showTemplateDetail,
      selectedTemplateDetail,
      onSelectCategory,
      onSelectTemplate,
      closeTemplateDetail,
      // 输入
      templateImages,
      textInputs,
      getImageInputCount,
      getImageUploadText,
      getTextInputRange,
      getTextInputMax,
      getTextPlaceholder,
      getTextMaxLength,
      isTemplateInputValid,
      chooseImagesForTemplate,
      removeTemplateImage,
      // 生成/预览
      showPreview,
      isGenerating,
      generatedMeme,
      onGenerate,
      closePreview,
      saveMeme,
      shareMeme,
    }
  }
}
</script>

<style scoped>
.heat-hero{background:#fff9f2;border-radius:36rpx;padding:30rpx;margin:0 0 36rpx;box-shadow:0 14rpx 38rpx rgba(101,49,25,.08)}.hero-heading{display:flex;justify-content:space-between;align-items:center}.hero-eyebrow{display:block;font-size:17rpx;letter-spacing:3rpx;color:#a88572}.hero-title{display:block;font-size:38rpx;font-weight:750;color:#3a2c29;margin-top:10rpx}.hero-mark{font-size:64rpx;color:#d97b55}.hero-sub{display:block;color:#9b7e6e;font-size:21rpx;line-height:1.7;margin:16rpx 0 24rpx}.spotlight{display:flex;gap:14rpx}.spotlight-card{flex:1;min-width:0;position:relative;border-radius:24rpx;background:#fff;padding:20rpx 10rpx 16rpx;text-align:center;transition:transform .2s}.spotlight-card:active{transform:scale(.95)}.spotlight-rank{position:absolute;left:12rpx;top:10rpx;font-size:20rpx;color:#bda08d;font-style:italic}.spotlight-image{width:102rpx;height:102rpx;margin:6rpx 0 14rpx}.spotlight-name{display:block;font-size:23rpx;color:#493a34;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.spotlight-heat{display:block;font-size:18rpx;color:#b76c49;margin-top:8rpx}.sort-row{display:flex;align-items:center;justify-content:space-between;margin:24rpx 0}.sort-switch{display:flex;background:rgba(255,255,255,.3);padding:5rpx;border-radius:25rpx}.sort-switch button{margin:0;background:transparent;border:0;font-size:22rpx;padding:0 23rpx;line-height:2.5;color:#6d4635;border-radius:22rpx}.sort-switch .chosen{background:#fffaf6;color:#9c4e35;font-weight:700}.sort-note{font-size:19rpx;color:#73442e}

.container {
  min-height: 100vh;
  background: linear-gradient(135deg, #ff6b6b 0%, #ffa500 100%);
  padding: 40rpx 30rpx;
  position: relative;
  overflow: hidden;
  padding-top: calc(40rpx + constant(safe-area-inset-top));
  padding-top: calc(120rpx + env(safe-area-inset-top));
  padding-bottom: calc(30rpx + constant(safe-area-inset-bottom));
  padding-bottom: calc(160rpx + env(safe-area-inset-bottom));
}
.page-numbers { display:flex; justify-content:center; align-items:center; gap:12rpx; margin:32rpx 0 }
.page-button { margin:0; width:54rpx; height:54rpx; border-radius:18rpx; background:#fff7f2; color:#777; font-size:24rpx; line-height:54rpx; padding:0 }
.page-button.active { background:#ff7373; color:white; border:6rpx solid #fff7f2; box-sizing:content-box }
.load-error { background:#fff8f5; border-radius:24rpx; padding:38rpx; text-align:center; color:#777; font-size:24rpx }.load-error button { margin-top:20rpx; color:#ff6868 }

.header { text-align: center; margin-bottom: 40rpx; }
.logo { width: 120rpx; height: 120rpx; background: linear-gradient(45deg, #ff6b6b, #ff8e53); border-radius: 30rpx; display: flex; align-items: center; justify-content: center; font-size: 60rpx; margin: 0 auto 30rpx; box-shadow: 0 10rpx 30rpx rgba(255, 107, 107, 0.3); animation: bounce 2s infinite; }
@keyframes bounce { 0%, 20%, 50%, 80%, 100% { transform: translateY(0); } 40% { transform: translateY(-16rpx); } 60% { transform: translateY(-8rpx); } }
.app-title { color: #333; font-size: 44rpx; font-weight: bold; margin-bottom: 10rpx; display: block; }
.app-subtitle { color: #666; font-size: 28rpx; display: block; }

.meme-templates { margin-bottom: 40rpx; }
.template-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 30rpx; }
.section-title { color: #333; font-size: 32rpx; font-weight: bold; display: block; }
.pagination-info { display: flex; align-items: center; gap: 20rpx; background: rgba(255, 255, 255, 0.9); padding: 10rpx 20rpx; border-radius: 20rpx; box-shadow: 0 2rpx 8rpx rgba(0,0,0,0.1); }
.page-info { color: #666; font-size: 24rpx; font-weight: 500; }
.loading-indicator { display: flex; align-items: center; gap: 10rpx; }
.loading-text { color: #ff6b6b; font-size: 20rpx; }

.category-tabs { display: flex; background: rgba(255, 255, 255, 0.9); border-radius: 25rpx; padding: 8rpx; margin-bottom: 30rpx; box-shadow: 0 4rpx 16rpx rgba(0,0,0,0.1); overflow: hidden; }
.category-tab { flex: 1; display: flex; flex-direction: column; align-items: center; gap: 6rpx; padding: 20rpx 12rpx; border-radius: 20rpx; transition: all 0.3s ease; position: relative; cursor: pointer; }
.category-tab.active { background: linear-gradient(45deg, #ff6b6b, #ff8e53); color: white; transform: translateY(-2rpx); box-shadow: 0 4rpx 12rpx rgba(255, 107, 107, 0.3); }
.category-tab:active { transform: scale(0.98); }
.category-icon { font-size: 28rpx; display: block; }
.category-name { font-size: 22rpx; font-weight: 500; display: block; }
.category-count { font-size: 18rpx; opacity: 0.8; display: block; background: rgba(0, 0, 0, 0.1); padding: 4rpx 8rpx; border-radius: 10rpx; min-width: 32rpx; text-align: center; }
.category-tab.active .category-count { background: rgba(255, 255, 255, 0.2); }

.template-container { position: relative; display: flex; align-items: center; }
.nav-btn { position: absolute; width: 60rpx; height: 60rpx; background: rgba(255, 255, 255, 0.9); border: none; border-radius: 50%; font-size: 32rpx; color: #666; display: flex; align-items: center; justify-content: center; box-shadow: 0 4rpx 12rpx rgba(0,0,0,0.15); transition: all 0.3s ease; z-index: 10; }
.nav-btn:active { transform: scale(0.9); background: rgba(255, 107, 107, 0.9); color: white; }
.nav-left { left: -30rpx; }
.nav-right { right: -30rpx; }
.template-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20rpx; flex: 1; margin: 0 10rpx; }
.template-item { background: white; border-radius: 24rpx; padding: 30rpx; text-align: center; box-shadow: 0 4rpx 16rpx rgba(0,0,0,0.1); transition: all 0.3s ease; border: 4rpx solid transparent; min-height: 160rpx; display: flex; flex-direction: column; align-items: center; justify-content: center; }
.template-item:active { transform: scale(0.95); }
.template-item.selected { border-color: #ff6b6b; background: #fff5f5; }
.template-preview { width: 60rpx; height: 60rpx; border-radius: 8rpx; margin-bottom: 16rpx; }
.template-emoji { font-size: 48rpx; margin-bottom: 16rpx; display: block; }
.template-name { font-size: 24rpx; color: #666; font-weight: 500; display: block; word-break: break-all; }

.template-detail-modal { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0, 0, 0, 0.8); display: flex; align-items: center; justify-content: center; z-index: 2000; }
.detail-content { background: white; border-radius: 20rpx; width: 90%; max-width: 700rpx; max-height: 80%; overflow: hidden; position: relative; }
.detail-header { display: flex; justify-content: center; align-items: center; padding: 30rpx; border-bottom: 2rpx solid #eee; }
.detail-title { font-size: 32rpx; font-weight: bold; color: #333; }
.close-btn { position: absolute; top: 16rpx; right: 16rpx; width: 72rpx; height: 48rpx; background: #c62828; color: #fff; border: none; border-radius: 12rpx; font-size: 28rpx; display: flex; align-items: center; justify-content: center; box-shadow: 0 2rpx 10rpx rgba(198, 40, 40, 0.3); z-index: 10; }
.close-btn:active { transform: scale(0.95); background: #b71c1c; }
.detail-body { padding: 30rpx; max-height: 600rpx; overflow-y: auto; position: relative; z-index: 1; }
.example-section { margin-bottom: 40rpx; text-align: center; }
.detail-label { font-size: 28rpx; font-weight: bold; color: #333; margin-bottom: 20rpx; display: block; }
.example-image { width: 100%; max-height: 300rpx; border-radius: 16rpx; background: #f5f5f5; }
.template-info-section { margin-bottom: 40rpx; }
.info-item { display: flex; margin-bottom: 16rpx; }
.info-key { font-size: 26rpx; color: #666; width: 140rpx; flex-shrink: 0; }
.info-value { font-size: 26rpx; color: #333; flex: 1; }
.requirements-section { margin-bottom: 40rpx; }
.requirements-list { display: flex; flex-direction: column; gap: 12rpx; }
.requirement-text { font-size: 24rpx; color: #666; background: #f8f9fa; padding: 16rpx 20rpx; border-radius: 12rpx; }
.image-input-section { margin-bottom: 40rpx; }
.image-upload-area { background: #f8f9fa; border: 4rpx dashed #ddd; border-radius: 20rpx; padding: 40rpx; text-align: center; transition: all 0.3s ease; cursor: pointer; }
.image-upload-area:active { border-color: #ff6b6b; background: #fff5f5; transform: scale(0.98); }
.template-images-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 20rpx; margin-top: 20rpx; }
.template-image-item { position: relative; aspect-ratio: 1; border-radius: 16rpx; overflow: hidden; box-shadow: 0 4rpx 12rpx rgba(0,0,0,0.1); }
.template-image { width: 100%; height: 100%; border-radius: 16rpx; }
.remove-image-btn { position: absolute; top: 8rpx; right: 8rpx; width: 40rpx; height: 40rpx; background: rgba(255, 0, 0, 0.8); color: white; border: none; border-radius: 50%; font-size: 24rpx; display: flex; align-items: center; justify-content: center; box-shadow: 0 2rpx 8rpx rgba(0,0,0,0.3); transition: all 0.2s ease; }
.remove-image-btn:active { transform: scale(0.9); background: rgba(255, 0, 0, 1); }
.text-input-section { margin-bottom: 40rpx; }
.text-input-grid { display: grid; grid-template-columns: 1fr; gap: 16rpx; }
.text-input-item { background: #f8f9fa; border: 2rpx solid #e5e7eb; border-radius: 16rpx; padding: 12rpx 16rpx; }
.text-input { width: 100%; font-size: 26rpx; color: #333; }
.detail-actions { display: flex; gap: 20rpx; margin-top: 30rpx; }
.detail-actions .btn { flex: 1; }
.detail-actions .btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn { flex: 1; padding: 24rpx; border: none; border-radius: 40rpx; font-size: 28rpx; font-weight: bold; transition: all 0.3s ease; }
.btn-primary { background: linear-gradient(45deg, #ff6b6b, #ff8e53); color: white; }
.btn-secondary { background: #f8f9fa; color: #666; border: 2rpx solid #ddd; }
.btn:active { transform: scale(0.95); }

.preview-modal { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0, 0, 0, 0.8); display: flex; align-items: center; justify-content: center; z-index: 2000; }
.preview-content { background: white; border-radius: 20rpx; width: 90%; max-width: 600rpx; max-height: 80%; overflow: hidden; position: relative; }
.preview-header { display: flex; justify-content: space-between; align-items: center; padding: 30rpx; border-bottom: 2rpx solid #eee; }
.preview-title { font-size: 32rpx; font-weight: bold; color: #333; }
.generating-container { padding: 80rpx 40rpx; text-align: center; }
.loading-spinner { width: 80rpx; height: 80rpx; border: 6rpx solid #f3f3f3; border-top: 6rpx solid #ff6b6b; border-radius: 50%; animation: spin 1s linear infinite; margin: 0 auto 30rpx; }
@keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
.loading-text { font-size: 28rpx; color: #666; }
.meme-result { padding: 40rpx; }
.meme-image { width: 100%; max-height: 400rpx; border-radius: 16rpx; margin-bottom: 30rpx; }
.meme-actions { display: flex; gap: 20rpx; }
.meme-actions .btn { flex: 1; }

.status-message { position: fixed; top: 40rpx; left: 50%; transform: translateX(-50%) translateY(-100rpx); background: #4caf50; color: white; padding: 30rpx 40rpx; border-radius: 16rpx; box-shadow: 0 8rpx 24rpx rgba(0,0,0,0.2); transition: transform 0.3s ease; z-index: 1000; margin-top: constant(safe-area-inset-top); margin-top: env(safe-area-inset-top); }
.status-message.show { transform: translateX(-50%) translateY(0); }

.floating-emoji { position: absolute; font-size: 40rpx; animation: float 3s ease-in-out infinite; pointer-events: none; }
@keyframes float { 0%, 100% { transform: translateY(0px) rotate(0deg); } 50% { transform: translateY(-30rpx) rotate(10deg); } }

.close-btn::after, .btn::after { content: none !important; display: none !important; }
.detail-body { position: relative; z-index: 1; }
.recommend-entry{display:flex;align-items:center;justify-content:space-between;background:#fff8ef;border-radius:26rpx;padding:24rpx 28rpx;margin:28rpx 0;color:#713f2c}.recommend-title{display:block;font-size:29rpx;font-weight:700}.recommend-copy{display:block;font-size:22rpx;color:#a47761;margin-top:8rpx}.recommend-arrow{font-size:44rpx}
</style>
