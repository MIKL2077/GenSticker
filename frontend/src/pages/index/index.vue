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
import { prefetchClientTemplate } from '@/services/clientRenderer'
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
      prefetchClientTemplate(key).catch(() => {})
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

.container{min-height:100vh;background:linear-gradient(150deg,#ff8c78 0%,#ffa849 100%);padding:calc(120rpx + env(safe-area-inset-top)) 30rpx calc(180rpx + env(safe-area-inset-bottom));position:relative;overflow:hidden}
.meme-templates{margin-bottom:32rpx}.template-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:24rpx}.section-title{color:#432e29;font-size:30rpx;font-weight:700}.pagination-info{display:flex;align-items:center;gap:12rpx;background:#fff8ef;padding:10rpx 20rpx;border-radius:18rpx}.page-info{color:#826951;font-size:23rpx}.loading-text{color:#b97350;font-size:19rpx}
.page-numbers{display:flex;justify-content:center;align-items:center;gap:12rpx;margin:30rpx 0}.page-button{margin:0;width:54rpx;height:54rpx;border-radius:18rpx;background:#fff7f2;color:#97735b;font-size:24rpx;line-height:54rpx;padding:0}.page-button.active{background:#6f548a;color:white;box-shadow:0 4rpx 14rpx rgba(81,46,100,.15)}
.load-error{background:#fff8f5;border-radius:24rpx;padding:38rpx;text-align:center;color:#777;font-size:24rpx}.load-error button{margin-top:20rpx;color:#bc6a46}
.floating-emoji{position:absolute;font-size:36rpx;opacity:.08;pointer-events:none;animation:drift 7s ease-in-out infinite}@keyframes drift{0%,100%{transform:translateY(0) rotate(-4deg)}50%{transform:translateY(-10rpx) rotate(4deg)}}
</style>
