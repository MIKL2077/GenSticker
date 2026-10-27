<template>
  <view class="container" :class="{'motion-paused':!sceneActive,'scene-enter':sceneActive}">
    <app-header />
    <view class="welcome-card ui-enter"><view class="welcome-copy-block"><view class="studio-tag fx-enter"><view/>私有造梗神器 · 今日也营业</view><text class="welcome-title">一键套模板，<text class="title-pop">把 Ta 玩成梗。</text></text><text class="welcome-copy">紧跟热梗，简单几步就能整活。</text><button class="welcome-action" @click="openRecommend">为 Ta 生成 9 张 <text>↗</text></button></view><view class="hero-toys"><mood-toy :active="sceneActive && !showTemplateDetail && !showPreview"/></view><text class="hero-serial">GENSTICKER / MOOD LAB 001</text></view>
    <popularity-stage v-if="!loadError && (spotlight.length || !isLoadingTemplates)" :items="spotlight" :active="sceneActive && !showTemplateDetail && !showPreview" @select="onSelectTemplate"/>
    <view v-if="trialTemplate" class="trial-card fx-enter" @click="onSelectTemplate(trialTemplate.key)"><image v-if="trialTemplate.previewImage" :src="trialTemplate.previewImage" mode="aspectFit"/><view><text class="trial-label">{{trialTemplate.trialLabel}}</text><text class="trial-title">{{ trialTemplate.name }}</text><text class="trial-hint">{{trialTemplate.trialImageSlots?'换上你的照片，给它一个新表情 ↗':'换句你的文案，接住今天的新梗 ↗'}}</text></view></view>
    <button class="live-entry" @click="openLive"><ui-icon name="video" tone="accent" :size="52"/><view><text>视频转 GIF</text><text>选一段视频 · 自由裁剪 + 自己配文</text></view><ui-icon name="arrow" :size="30"/></button>
    <view class="meme-templates">
      <view class="template-header fx-enter">
        <text class="section-title">模板仓库</text>
        <view class="pagination-info">
          <text class="page-info">{{ currentPage }}/{{ totalPages }}</text>
          <view v-if="isLoadingTemplates" class="loading-indicator">
            <text class="loading-text">加载中...</text>
          </view>
        </view>
      </view>

      <view class="template-search"><view class="search-symbol" aria-hidden="true"/><input class="template-search-input" :value="searchQuery" maxlength="80" confirm-type="search" placeholder="搜模板、关键词，或试试“猫 动图”" placeholder-class="search-placeholder" aria-label="搜索模板" @input="setSearchQuery($event.detail.value)"/><button v-if="searchQuery" class="search-clear" aria-label="清空搜索" @click="setSearchQuery('')"><ui-icon name="close" :size="28"/></button></view>
      <view v-if="searchQuery" class="search-summary"><text>{{searchResultCount?'找到 '+searchResultCount+' 个模板':'没找到相关模板，换个词试试'}}</text><button @click="setSearchQuery('')">查看全部</button></view>
      <category-tabs :categories="categories" :selected-category="selectedCategory" @select="onSelectCategory" />
      <view class="sort-row"><view class="sort-switch"><button :class="{chosen:libraryMode==='warehouse'}" @click="changeLibrary('warehouse')">模板仓库</button><button :class="{chosen:libraryMode==='mine'}" @click="changeLibrary('mine')">我的模板</button></view><picker :range="sortLabels" :value="sortIndex" @change="chooseSort"><view class="sort-note">{{sortLabels[sortIndex]}} ⌄</view></picker></view>
      <button class="create-entry fx-enter" @click="openCreator"><view class="create-symbol"><ui-icon name="plus" tone="accent" :size="34"/></view><view><text>我的梗，我来造</text><text>拖拽做模板 / AI 一键识图 · 私藏或发布都行</text></view><text>↗</text></button>
      <template v-if="libraryMode==='mine'"><text v-if="!accountSession" class="mine-note">先在“我的”登录，就能收好自己制作与收藏的模板。</text><view v-for="item in mineTemplates.filter(t=>t.status!=='published')" :key="item.id" class="template-state"><text>{{item.name}} · {{templateStatus[item.status]||item.status}}</text><button @click="retryPublish(item)">提交发布 ↗</button><text class="state-message">{{item.message}}</text></view><view v-for="task in templateTasks" :key="task.id" class="template-state"><text>{{task.status==='needs_manual'?'需要手动调整':'AI 正在拆解模板 ✦'}}</text><text class="state-message">{{task.message || '稍后再来，小窝做好会喊你'}}</text><button v-if="task.status==='needs_manual'" @click="openCreator">去手动制作 ↗</button></view></template>
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
      <view v-if="!loadError && searchResultCount" class="page-numbers">
        <button v-if="currentPage > 1" class="page-button" @click="prevPage">‹</button>
        <button v-for="number in pageNumbers" :key="number" class="page-button" :class="{ active: number === currentPage }" @click="currentPage = number">{{ number }}</button>
        <button v-if="currentPage < totalPages" class="page-button" @click="nextPage">›</button>
      </view>
    </view>

    <text class="home-footer fx-enter">热梗追得上，私梗造得出。</text>
    <template-detail-modal
      id="template-detail"
      :show="showTemplateDetail"
      :detail="selectedTemplateDetail"
      :template-images="templateImages"
      :text-inputs="textInputs"
      :image-input-count="getImageInputCount()"
      :image-upload-text="getImageUploadText()"
      :active-image-index="activeImageIndex"
      :editor-open="showImageEditor"
      :editor-busy="editorBusy"
      :editor-error="editorError"
      :editor-can-undo="editorCanUndo"
      :text-range="getTextInputRange()"
      :text-max="getTextInputMax()"
      :get-text-placeholder="getTextPlaceholder"
      :get-text-max-length="getTextMaxLength"
      :can-generate="isTemplateInputValid()"
      :favorite="isFavorite(selectedTemplate)"
      :face-blend="faceBlend"
      :fusion-experiments="enableFusionLab"
      @blend="faceBlend=$event"
      @favorite="favoriteTemplate"
      @chooseImages="chooseImagesForTemplate"
      @removeImage="removeTemplateImage"
      @editImage="openImageEditor"
      @closeEditor="closeImageEditor"
      @applyEdit="applyImageEdit"
      @undoEdit="undoImageEdit"
      @restoreImage="restoreImage"
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
      @edit="continueEditing"
    />

    <status-message :message="statusMessage" :show="showStatus" />
    <bottom-tabs active="home" />
    <generation-notice/><first-use-guide />
  </view>
</template>

<script>
import {holdBackgroundWork} from '@/services/backgroundActivity'
import {getCurrentTrial,hasUsedTrial,markTrialUsed} from '@/services/trialService'
import {takeEditDraft,disposeEditDraft} from '@/services/editSession'
import GenerationNotice from '@/components/GenerationNotice.vue'
import FirstUseGuide from '@/components/FirstUseGuide.vue'
import { onMounted, onUnmounted, watch, ref, computed } from 'vue'
import { onShow, onHide, onShareAppMessage, onLoad } from '@dcloudio/uni-app'
import {shareCard} from '@/services/shareCard'
import UiIcon from '@/components/UiIcon.vue'
import MoodToy from '@/components/MoodToy.vue'
import PopularityStage from '@/components/PopularityStage.vue'
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
import { openRecommend } from '@/services/navigation'
import {listStudioJobs,publishTemplate,trackStudioJob} from '@/services/studioService'

import { useStatusMessage } from '@/composables/useStatusMessage'
import { useTemplateData } from '@/composables/useTemplateData'
import { useTemplateInput } from '@/composables/useTemplateInput'
import { useMemeGeneration } from '@/composables/useMemeGeneration'

export default {
  name: 'Index',
  components: { GenerationNotice, FirstUseGuide, UiIcon,MoodToy, PopularityStage, AppHeader, CategoryTabs, TemplateGrid, TemplateDetailModal, PreviewModal, StatusMessage, BottomTabs },
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
      searchQuery,setSearchQuery,searchResultCount,
      libraryMode,loadMine,mineTemplates,
      templateDetails,
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

    const { templateImages, textInputs, extractSubject, selectedTemplateDetail, getImageInputCount, getImageUploadText, getTextInputRange, getTextInputMax, getTextPlaceholder, getTextMaxLength, initializeTemplateInputs, isTemplateInputValid, chooseImagesForTemplate, removeTemplateImage, activeImageIndex, showImageEditor, editorBusy, editorError, editorCanUndo, openImageEditor, closeImageEditor, applyImageEdit, undoImageEdit, restoreImage, resetInputs, restoreDraftImages } = useTemplateInput()
    onUnmounted(resetInputs)

    const { showPreview, isGenerating, generatedMeme, generateFromTemplate, closePreview, saveMeme, shareMeme } = useMemeGeneration(showStatusMessage)

    const trialCandidate=ref(null),trialUseEpoch=ref(0)
    let trialRequest=0,trialTimer=null
    const trialTemplate=computed(()=>{
      trialUseEpoch.value
      const trial=trialCandidate.value
      if(!trial || trial.used || hasUsedTrial(trial.key))return null
      const detail=templateDetails.value.get(trial.key)
      return detail?{...detail,trialLabel:trial.label,trialImageSlots:trial.image_slots}:null
    })
    const refreshTrial=async()=>{
      const request=++trialRequest,identity=account.session.value?.profile?.id || 'guest'
      trialUseEpoch.value++
      try{
        const trial=await getCurrentTrial()
        if(request!==trialRequest || identity!==(account.session.value?.profile?.id || 'guest'))return
        if(trial){await fetchMemeInfo(trial.key);await fetchMemePreview(trial.key,true)}
        if(request===trialRequest && identity===(account.session.value?.profile?.id || 'guest'))trialCandidate.value=trial
      }catch(_){/* Keep the previous valid offer during a transient network failure. */}
    }
    const trialUsed=()=>{trialUseEpoch.value++}
    uni.$on('gensticker:trial-used',trialUsed)
    watch(()=>account.session.value?.profile?.id,()=>{trialCandidate.value=null;refreshTrial()})
    onHide(()=>{clearInterval(trialTimer);trialRequest++})
    onUnmounted(()=>{clearInterval(trialTimer);trialRequest++;uni.$off('gensticker:trial-used',trialUsed)})
    const sceneActive = ref(true)
    onHide(()=>{sceneActive.value=false})
    const selectedTemplate = ref('')
    const faceBlend=ref('replace'),enableFusionLab=ref(false)
    onShareAppMessage(()=>shareCard({image:generatedMeme.value,template:selectedTemplate.value && (!selectedTemplateDetail.value?.ownPreview || selectedTemplateDetail.value?.status==='published')?selectedTemplate.value:''}))
    const showTemplateDetail = ref(false)

    const onSelectCategory = async (key) => {
      await selectCategory(key)
    }

    let templateRequest=0
    const onSelectTemplate = async (key) => {
      const request=++templateRequest,owner=account.session.value?.profile?.id
      restoredArgs={};faceBlend.value='replace'
      selectedTemplate.value = key
      prefetchClientTemplate(key).catch(() => {})
      const detail = (await fetchMemeInfo(key)) || null
      if(request!==templateRequest || owner!==account.session.value?.profile?.id)return false
      if (detail && !detail.previewImage) fetchMemePreview(key)
      if (!detail) { showStatusMessage('模板暂时不可用，请稍后重试'); return }
      if(!detail.ownPreview)account.recordVisit(key)
      trackTemplate(key, 'click')
      selectedTemplateDetail.value = detail
      initializeTemplateInputs(detail)
      showTemplateDetail.value = true
      return true
    }

    let restoredArgs={}
    const onGenerate = async () => {
      if (!isTemplateInputValid()) {
        showStatusMessage('请完整填写所需信息！')
        return
      }
      const texts = (textInputs.value || []).map(t => (t || '').trim()).filter(Boolean)
      const key=selectedTemplate.value,trialOwner=account.session.value?.profile?.id || 'guest'
      const success=await generateFromTemplate(key, templateImages.value, texts, enableFusionLab.value && selectedTemplateDetail.value?.faceBlend?{...restoredArgs,face_blend:faceBlend.value}:restoredArgs, {extractSubject:extractSubject.value})
      if(success && trialOwner===(account.session.value?.profile?.id || 'guest'))markTrialUsed(key)
      if(!success || selectedTemplate.value!==key)return
      showTemplateDetail.value = false
    }
    const continueEditing = () => { closePreview(); showTemplateDetail.value = true }

    const closeTemplateDetail = () => {
      templateRequest++
      showTemplateDetail.value = false
      selectedTemplateDetail.value = null
      resetInputs()
    }

    const favoriteTemplate = () => {
      if(selectedTemplateDetail.value?.ownPreview){showStatusMessage('这张模板已经在我的模板里啦');return}
      try { const saved = account.toggleFavorite(selectedTemplate.value); if (saved && !account.session.value) trackTemplate(selectedTemplate.value,'favorite'); showStatusMessage(saved ? '已收藏模板' : '已取消收藏') }
      catch (e) { showStatusMessage(e.message) }
    }
    const templateTasks=ref([]),sortLabels=['人气从高到低','人气从低到高','最新创建优先','最早创建优先'],sortValues=['hot','cold','new','old']
    const sortIndex=computed(()=>Math.max(0,sortValues.indexOf(sortMode.value)))
    const refreshMine=async()=>{try{await loadMine(account.library.value.favorite_keys);if(account.session.value)templateTasks.value=(await listStudioJobs()).filter(j=>j.kind==='template' && ['queued','running','needs_manual'].includes(j.status));else templateTasks.value=[]}catch(e){showStatusMessage(e.message)}}
    const changeLibrary=async mode=>{libraryMode.value=mode;currentPage.value=1;if(mode==='mine')await refreshMine();await ensurePageLoaded(selectedCategory.value,1)}
    const openCreator=()=>uni.navigateTo({url:'/pages/create/index'})
    const retryPublish=async item=>{try{const task=await publishTemplate(item.id);trackStudioJob(task);showStatusMessage('已提交内容检查，完成后小窝会喊你');await refreshMine()}catch(e){showStatusMessage(e.message)}}
    const completed=async()=>{await fetchMemeCategories(true);await refreshMine();await ensurePageLoaded(selectedCategory.value,currentPage.value)}
    uni.$on('studio-completed',completed);onUnmounted(()=>uni.$off('studio-completed',completed))
    const pageNumbers = computed(() => {
      const start = Math.max(1, Math.min(currentPage.value - 2, totalPages.value - 4))
      return Array.from({ length: Math.min(5, totalPages.value) }, (_, i) => start + i)
    })
    const retryTemplates = async () => { await fetchMemeCategories(); await ensurePageLoaded(selectedCategory.value, currentPage.value) }
    onShow(() => {
      sceneActive.value=true
      refreshTrial();clearInterval(trialTimer);trialTimer=setInterval(refreshTrial,60000)
      const editDraft=takeEditDraft('manual')
      if(editDraft){
        closePreview()
        onSelectTemplate(editDraft.template_key).then(ready=>{
          if(!ready || selectedTemplate.value!==editDraft.template_key || !selectedTemplateDetail.value){disposeEditDraft(editDraft);return}
          restoredArgs={...(editDraft.args||{})};faceBlend.value=restoredArgs.face_blend||'replace';restoreDraftImages(editDraft.paths||[],editDraft.temporaryPaths||[]);textInputs.value=[...(editDraft.texts||[])];extractSubject.value=!!editDraft.extract_subject
        }).catch(e=>{disposeEditDraft(editDraft);showStatusMessage(e.message||'无法恢复编辑内容')})
      }
      uni.hideTabBar({ animation: false, fail: () => {} })
      if(uni.getStorageSync('gensticker.open-mine')){uni.removeStorageSync('gensticker.open-mine');changeLibrary('mine')}
      else if(libraryMode.value==='mine')refreshMine()
      if(uni.getStorageSync('gensticker.templates.changed')){uni.removeStorageSync('gensticker.templates.changed');fetchMemeCategories(true).then(refreshMine)}
      const key = uni.getStorageSync('gensticker.open-template')
      if (key) { uni.removeStorageSync('gensticker.open-template'); onSelectTemplate(key) }
    })

    watch(()=>account.session.value?.profile?.id,()=>{closeTemplateDetail();closePreview();refreshMine()})
    watch([selectedCategory, currentPage, sortMode, libraryMode, searchQuery], ([cat, page], _, onCleanup) => {
      let canceled=false,timer
      const load=async()=>{await ensurePageLoaded(cat,page);if(!canceled)prefetchAdjacent(cat,page)}
      if(searchQuery.value.trim())timer=setTimeout(load,180)
      else load()
      onCleanup(()=>{canceled=true;clearTimeout(timer)})
    })

    onLoad(query=>{enableFusionLab.value=query?.fusionLab==='1';if(query?.template)uni.setStorageSync('gensticker.open-template',query.template)})
    onMounted(async () => {
      const resumeWarmup=holdBackgroundWork()
      try {
        await fetchMemeCategories()
        await ensurePageLoaded(selectedCategory.value, 1)
        prefetchAdjacent(selectedCategory.value, 1)
      } catch (e) {
        showStatusMessage('初始化失败，请刷新页面重试')
      } finally {resumeWarmup()}
    })

    return {
      // 状态消息
      statusMessage,
      showStatus,
      // 分类/分页
      isLoadingTemplates,
      loadError,
      sceneActive,
      openRecommend,openLive:()=>uni.navigateTo({url:"/pages/live/index"}),
      continueEditing,
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
      searchQuery,setSearchQuery,searchResultCount,
      libraryMode,mineTemplates,changeLibrary,sortLabels,sortIndex,chooseSort:e=>{sortMode.value=sortValues[Number(e.detail.value)];currentPage.value=1},openCreator,templateTasks,retryPublish,accountSession:account.session,templateStatus:{private:"私藏",pending:"待检查",rejected:"检查未通过"},
      spotlight,
      changeSort: mode => { sortMode.value = mode; currentPage.value = 1 },
      prevPage,
      nextPage,
      // 模板选择
      trialTemplate,faceBlend,enableFusionLab,
      selectedTemplate,
      showTemplateDetail,
      selectedTemplateDetail,
      onSelectCategory,
      onSelectTemplate,
      closeTemplateDetail,
      // 输入
      extractSubject,
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
      activeImageIndex, showImageEditor, editorBusy, editorError, editorCanUndo,
      openImageEditor, closeImageEditor, applyImageEdit, undoImageEdit, restoreImage,
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
.container{min-height:100vh;background:var(--paper);padding:calc(76rpx + env(safe-area-inset-top)) 30rpx calc(186rpx + env(safe-area-inset-bottom));overflow-x:hidden}.welcome-card{position:relative;isolation:isolate;background:linear-gradient(120deg,#fcf7f1,#faf3ea 65%,#faf3ea);border:3rpx solid #fff;border-radius:42rpx;padding:30rpx 26rpx 55rpx;box-shadow:inset 0 -6rpx 0 #f4e6d7,0 12rpx 24rpx rgba(69,72,138,.05);min-height:365rpx;display:flex;align-items:center;overflow:hidden}.welcome-card:before{content:'';position:absolute;width:360rpx;height:360rpx;border:2rpx solid rgba(255,255,255,.7);border-radius:50%;right:-120rpx;top:-130rpx;z-index:-1}.welcome-copy-block{position:relative;z-index:2;width:67%}.studio-tag{display:inline-flex;align-items:center;gap:8rpx;font-size:18rpx;color:#938575;border:2rpx solid #fff;background:rgba(255,255,255,.65);border-radius:30rpx;padding:6rpx 13rpx;letter-spacing:1rpx}.studio-tag>view{width:7rpx;height:7rpx;background:#e59c82;border-radius:50%}.welcome-title{display:block;font-size:49rpx;font-weight:850;letter-spacing:-2rpx;line-height:1.32;color:#2d4a53;margin-top:20rpx}.title-pop{display:block;color:#dd7752}.welcome-copy{display:block;color:#928474;font-size:22rpx;margin-top:15rpx}.welcome-action{display:inline-flex;gap:20rpx;align-items:center;color:white;background:linear-gradient(155deg,#eda991,#e4805c);font-size:24rpx;font-weight:700;border:2rpx solid #efb29b;border-radius:22rpx;padding:16rpx 22rpx;line-height:1.4;margin-top:24rpx;box-shadow:0 6rpx 0 #b86243,inset 0 2rpx 0 #f2dcc2;transition:transform .18s}.welcome-action:active{transform:translateY(5rpx)}.hero-toys{position:absolute;width:285rpx;height:310rpx;right:-3rpx;top:42rpx;z-index:1}.hero-serial{position:absolute;bottom:18rpx;left:28rpx;font-size:15rpx;color:#b1a79c;letter-spacing:3rpx}.trial-card{display:flex;align-items:center;gap:18rpx;margin:0 0 28rpx;padding:16rpx 20rpx;background:#fffdf7;border:2rpx solid #f0e5ce;border-radius:28rpx;box-shadow:0 5rpx 0 #eee4ce}.trial-card image{width:80rpx;height:80rpx;border-radius:18rpx;flex-shrink:0}.trial-card text{display:block}.trial-label{font-size:18rpx;color:#a58135;letter-spacing:2rpx}.trial-title{font-size:26rpx;font-weight:750;color:var(--ink)}.trial-hint{font-size:21rpx;color:#989080;margin-top:3rpx}.template-header{display:flex;align-items:center;justify-content:space-between;margin-top:30rpx}.section-title{font-size:36rpx;font-weight:800;color:var(--ink);letter-spacing:-1rpx}.pagination-info{display:flex;align-items:center;gap:10rpx}.page-info{font-size:22rpx;color:#9c948a;background:#f3eee9;padding:5rpx 13rpx;border-radius:14rpx}.loading-text{font-size:20rpx;color:#c68e79}.sort-row{display:flex;align-items:center;justify-content:space-between;gap:10rpx;margin:22rpx 0}.sort-switch{display:flex;gap:24rpx}.sort-switch button{font-size:23rpx;color:#a39b92;padding:10rpx 0;line-height:1.4;border-radius:0}.sort-switch .chosen{color:#b46b50;font-weight:750;border-bottom:4rpx solid #d49179}.sort-note{font-size:20rpx;color:#aba39a}.page-numbers{display:flex;justify-content:center;gap:12rpx;margin:30rpx 0 12rpx}.page-button{width:65rpx;height:66rpx;line-height:60rpx;padding:0;font-size:24rpx;border-radius:21rpx;color:#928a80;background:#fff;border:2rpx solid #edebe8;box-shadow:0 4rpx 0 #ebe9e6}.page-button.active{background:#c98870;color:white;border-color:#e0a28c;box-shadow:0 4rpx 0 #ab6349,inset 0 2rpx 0 #edb5a1}.load-error{margin:25rpx 0;padding:26rpx;background:#fff0ea;border-radius:25rpx;font-size:24rpx;color:#aa6753;line-height:1.7}.load-error button{color:#c0765b;font-size:24rpx}.home-footer{display:block;text-align:center;font-size:21rpx;letter-spacing:1rpx;color:#b5aea7;margin:45rpx 0 10rpx}
.welcome-card{background:linear-gradient(125deg,#fff1df,#f6e8d7 65%,#f8eddc);box-shadow:inset 0 -6rpx 0 #e9d8c0,0 12rpx 24rpx rgba(113,86,44,.05)}.welcome-title{color:#29454c}.title-pop{color:#dd7654}.studio-tag{color:#a2835f;background:#fffaf0}.studio-tag>view{background:#c1a46d}.welcome-action{background:linear-gradient(145deg,#ffa37f,#f17f5c);border-color:#ffb292;box-shadow:0 6rpx 0 #cd6648,inset 0 2rpx 0 #ffc7a7;color:#fff}.welcome-copy{color:#a18b70}.hero-serial{color:#b7a38a}.hero-toys{top:31rpx;right:4rpx}.sort-switch .chosen{color:#b56f50;border-color:#e3a17a}.page-button.active{background:linear-gradient(145deg,#f7ac88,#ec8b68);border-color:#ffc6a4;box-shadow:0 4rpx 0 #cd7654,inset 0 2rpx 0 #ffd1b3}.home-footer{color:#b3a08e}
.welcome-action{position:relative;overflow:hidden}.welcome-action:after{content:'';position:absolute;inset:0;width:100%;height:100%;border-radius:inherit;pointer-events:none;background:linear-gradient(105deg,transparent 30%,rgba(255,255,255,.24),transparent 65%);animation:ui-shimmer 1.2s ease-out .7s 2}.page-button.active{animation:ui-pop .3s ease-out both}.load-error{animation:ui-nudge .35s ease-out both}.loading-indicator{animation:ui-breathe 1.6s ease-in-out infinite}
.create-entry{display:flex;align-items:center;gap:18rpx;width:100%;text-align:left;background:linear-gradient(125deg,#fff1dc,#ffebe1);border:3rpx solid white;border-radius:26rpx;padding:22rpx;margin:12rpx 0 25rpx;color:#b78057;line-height:1.6}.create-entry>view:nth-child(2){flex:1}.create-entry text{display:block;font-size:26rpx;font-weight:650}.create-entry>view text:nth-child(2){font-size:20rpx;font-weight:400;color:#b19576}.create-symbol{width:62rpx;height:62rpx;background:#fffcf5;border-radius:21rpx;display:flex;align-items:center;justify-content:center;font-size:36rpx;box-shadow:0 4rpx 0 #e7cbb0}.create-entry:active .create-symbol{transform:rotate(90deg);transition:transform .25s}.mine-note{display:block;color:#a38d70;font-size:24rpx;padding:20rpx}.template-state{display:flex;align-items:center;flex-wrap:wrap;gap:10rpx;background:#f4efe3;border-radius:22rpx;padding:18rpx 22rpx;margin-bottom:15rpx;font-size:24rpx;color:#8e815f}.template-state button{font-size:22rpx;color:#c48058;margin-left:auto}.state-message{display:block;width:100%;font-size:21rpx;color:#a49a85}.sort-note{font-size:22rpx}.sort-row{gap:8rpx}
.live-entry{display:flex;align-items:center;gap:20rpx;background:linear-gradient(120deg,#fff4df,#f2eddd);border:3rpx solid white;border-radius:28rpx;padding:24rpx;width:100%;margin-bottom:25rpx;box-shadow:0 5rpx 0 #e9dfcc;text-align:left}.live-entry>view{flex:1}.live-entry text{display:block;font-size:28rpx;color:#667b64;font-weight:700}.live-entry>view text:nth-child(2){font-size:21rpx;color:#a39c80;font-weight:400;margin-top:6rpx}
.template-search{display:flex;align-items:center;gap:20rpx;background:#fffcf7;border:2rpx solid #eadfd3;border-radius:25rpx;padding:0 22rpx;min-height:84rpx;margin:18rpx 0 22rpx}.template-search-input{flex:1;min-width:0;height:80rpx;font-size:25rpx;color:var(--ink)}.search-placeholder{color:#b5a99b;font-size:24rpx}.search-symbol{position:relative;flex-shrink:0;width:29rpx;height:29rpx;border:4rpx solid #bd8d73;border-radius:50%;margin-right:8rpx}.search-symbol:after{content:'';position:absolute;width:14rpx;height:4rpx;background:#bd8d73;right:-11rpx;bottom:-5rpx;transform:rotate(45deg);border-radius:4rpx}.search-clear{display:flex;align-items:center;justify-content:center;padding:12rpx;min-width:52rpx;min-height:52rpx}.search-summary{display:flex;align-items:center;justify-content:space-between;gap:18rpx;margin:-7rpx 4rpx 20rpx;font-size:22rpx;color:var(--muted)}.search-summary button{font-size:22rpx;color:var(--accent-dark);padding:8rpx 0;flex-shrink:0}
</style>
