<template>
  <view class="container">
    <app-header>
      <view class="floating-emoji" style="top: 10%; left: 10%; animation-delay: 0s;">😀</view>
      <view class="floating-emoji" style="top: 20%; right: 15%; animation-delay: 1s;">😂</view>
      <view class="floating-emoji" style="bottom: 30%; left: 5%; animation-delay: 2s;">🤣</view>
      <view class="floating-emoji" style="bottom: 20%; right: 10%; animation-delay: 0.5s;">😍</view>
    </app-header>

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

      <template-grid
        :templates="currentPageTemplates"
        :selected-template="selectedTemplate"
        :current-page="currentPage"
        :total-pages="totalPages"
        @select="onSelectTemplate"
        @prev="prevPage"
        @next="nextPage"
      />
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
  </view>
</template>

<script>
import { onMounted, watch, ref } from 'vue'
import AppHeader from '@/components/AppHeader.vue'
import CategoryTabs from '@/components/CategoryTabs.vue'
import TemplateGrid from '@/components/TemplateGrid.vue'
import TemplateDetailModal from '@/components/TemplateDetailModal.vue'
import PreviewModal from '@/components/PreviewModal.vue'
import StatusMessage from '@/components/StatusMessage.vue'

import { useStatusMessage } from '@/composables/useStatusMessage'
import { useTemplateData } from '@/composables/useTemplateData'
import { useTemplateInput } from '@/composables/useTemplateInput'
import { useMemeGeneration } from '@/composables/useMemeGeneration'

export default {
  name: 'Index',
  components: { AppHeader, CategoryTabs, TemplateGrid, TemplateDetailModal, PreviewModal, StatusMessage },
  setup() {
    const { statusMessage, showStatus, showStatusMessage } = useStatusMessage()

    const {
      isLoadingTemplates,
      selectedCategory,
      categories,
      currentPage,
      totalPages,
      currentPageTemplates,
      fetchMemeCategories,
      ensurePageLoaded,
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
      await fetchMemeInfo(key)
      const detail = (await fetchMemeInfo(key)) || null
      if (detail && !detail.previewImage) fetchMemePreview(key)
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

    watch([selectedCategory, currentPage], async ([cat, page]) => {
      await ensurePageLoaded(cat, page)
      ensurePageLoaded(cat, page + 1)
    })

    onMounted(async () => {
      try {
        await fetchMemeCategories()
        await ensurePageLoaded(selectedCategory.value, 1)
        setTimeout(() => {
          ensurePageLoaded('all', 2)
          ;['text', 'image', 'mixed'].forEach((c) => ensurePageLoaded(c, 1))
        }, 0)
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
      selectedCategory,
      categories,
      currentPage,
      totalPages,
      currentPageTemplates,
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
.container {
  min-height: 100vh;
  background: linear-gradient(135deg, #ff6b6b 0%, #ffa500 100%);
  padding: 40rpx 30rpx;
  position: relative;
  overflow: hidden;
  padding-top: calc(40rpx + constant(safe-area-inset-top));
  padding-top: calc(40rpx + env(safe-area-inset-top));
  padding-bottom: calc(30rpx + constant(safe-area-inset-bottom));
  padding-bottom: calc(30rpx + env(safe-area-inset-bottom));
}

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
</style>