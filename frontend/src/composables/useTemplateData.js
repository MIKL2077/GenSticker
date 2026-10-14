import { ref, computed, onUnmounted } from 'vue'
import { PAGINATION, CATEGORY_UI_TO_API } from '@/constants'
import { getCategories, getTemplateInfo, getTemplatePreviewPath, setThumbnailWindow, onThumbnailEvict } from '@/services/memeService'
import { seedClientRecipes } from '@/services/clientRenderer'

export function useTemplateData(showStatusMessage) {
  const isLoadingTemplates = ref(false)
  const loadError = ref('')
  const templateDetails = ref(new Map())
  const previewImageCache = ref(new Map())
  const loadingStates = ref(new Map())
  const stopEvictions = onThumbnailEvict(key => { previewImageCache.value.delete(key); const detail=templateDetails.value.get(key); if(detail) detail.previewImage=null })
  onUnmounted(stopEvictions)

  const selectedCategory = ref('all')
  const categories = ref([
    { key: 'all', name: '全部', icon: '🎭', count: 0 },
    { key: 'text', name: '仅文字', icon: '📝', count: 0 },
    { key: 'image', name: '仅图片', icon: '📷', count: 0 },
    { key: 'mixed', name: '图文混合', icon: '📝+📷', count: 0 },
  ])

  const currentPage = ref(1)
  const sortMode = ref('hot')

  const categoryKeys = ref({ all: [], text_only: [], image_only: [], mixed: [] })
  const categoryLoadedPages = ref(new Map()) // Map<uiCategoryKey, Set<number>>

  const pageTasks = new Map()
  let visibleLoads = 0
  const templatesPerPage = PAGINATION.templatesPerPage

  const currentCategoryAllKeys = computed(() => {
    const apiKey = CATEGORY_UI_TO_API[selectedCategory.value]
    const keys = categoryKeys.value[apiKey] || []
    return sortMode.value === 'explore' ? [...keys].sort((a,b) => a.localeCompare(b)) : keys
    })

  const totalPages = computed(() => Math.max(1, Math.ceil(currentCategoryAllKeys.value.length / templatesPerPage)))

  const currentPageKeys = computed(() => {
    const start = (currentPage.value - 1) * templatesPerPage
    const end = start + templatesPerPage
    return currentCategoryAllKeys.value.slice(start, end)
  })

  const currentPageTemplates = computed(() => currentPageKeys.value.map((key) => {
    const detail = templateDetails.value.get(key)
    if (detail) return detail
    return {
      key,
      name: key,
      keywords: [],
      tags: [],
      imageCount: '0-0',
      textCount: '0-0',
      defaultTexts: [],
      previewImage: null,
      isLoadingPreview: true,
    }
  }))

  const fetchMemeCategories = async () => {
    try {
      isLoadingTemplates.value = true
      loadError.value = ''
      const data = await getCategories()
      seedClientRecipes(data.client)
      const localKeys=new Set((data.client?.recipes || []).map(r=>r.key))
      categoryKeys.value = {
        all: Array.isArray(data.all) ? data.all : [],
        text_only: Array.isArray(data.text_only) ? data.text_only : [],
        image_only: Array.isArray(data.image_only) ? data.image_only : [],
        mixed: Array.isArray(data.mixed) ? data.mixed : [],
      }
      for (const card of data.cards || []) {
        const existing = templateDetails.value.get(card.key) || { key: card.key, previewImage: null, isLoadingPreview: true }
        const params=card.params_type
        templateDetails.value.set(card.key, { ...existing, name:card.name, featuredTrial:!!card.featured_trial, inputHint:card.input_hint || '', keywords:card.keywords || [], tags:card.tags || [], heat:card.heat || 0, counts:card.counts || {}, localCapable:localKeys.has(card.key), ...(params ? {metadataLoaded:true, templateId:card.template_id, version:card.version, attribution:card.attribution || {}, imageCount:`${params.min_images}-${params.max_images}`, textCount:`${params.min_texts}-${params.max_texts}`, defaultTexts:params.default_texts || []} : {}) })
      }
      for(const card of data.cards || [])if(card.featured_trial)fetchMemePreview(card.key, true)
      categoryLoadedPages.value.clear()
      categories.value = categories.value.map(c => {
        const apiKey = CATEGORY_UI_TO_API[c.key]
        const len = categoryKeys.value[apiKey]?.length || 0
        return { ...c, count: len }
      })
    } catch (error) {
      console.error('获取分类失败:', error)
      loadError.value = '模板暂时无法加载，请检查网络后重试'
      showStatusMessage && showStatusMessage(`获取分类失败: ${error.message}`)
    } finally {
      isLoadingTemplates.value = false
    }
  }

  const fetchMemeInfo = async (key) => {
    try {
      if (templateDetails.value.has(key)) {
        const existing = templateDetails.value.get(key)
        if (existing?.metadataLoaded) return existing
      }
      const info = await getTemplateInfo(key)
      const existingDetail = templateDetails.value.get(key) || { key }
      existingDetail.inputHint = info.input_hint || ''
      existingDetail.templateId = info.template_id
      existingDetail.version = info.version
      existingDetail.attribution = info.attribution || {}
      existingDetail.metadataLoaded = true
      existingDetail.key = info.key
      existingDetail.name = info.keywords?.[0] || info.key
      existingDetail.keywords = info.keywords || []
      existingDetail.tags = info.tags || []
      existingDetail.imageCount = `${info.params_type?.min_images || 0}-${info.params_type?.max_images || 0}`
      existingDetail.textCount = `${info.params_type?.min_texts || 0}-${info.params_type?.max_texts || 0}`
      existingDetail.defaultTexts = info.params_type?.default_texts || []
      existingDetail.argsType = info.params_type?.args_type || null
      existingDetail.argsExamples = info.params_type?.args_type?.args_examples || []
      existingDetail.previewImage = existingDetail.previewImage || null
      existingDetail.isLoadingPreview = existingDetail.previewImage ? false : true
      templateDetails.value.set(key, existingDetail)
      return existingDetail
    } catch (error) {
      console.error(`获取模板 ${key} 详情失败:`, error)
      return null
    }
  }

  const fetchMemePreview = async (key, background = false) => {
    try {
      if (previewImageCache.value.has(key)) {
        const cached = previewImageCache.value.get(key)
        const t = templateDetails.value.get(key)
        if (t) {
          t.previewImage = cached
          t.isLoadingPreview = false
        }
        return cached
      }
      if (loadingStates.value.get(key)) return null
      loadingStates.value.set(key, true)
      const previewImage = await getTemplatePreviewPath(key, background)
      previewImageCache.value.set(key, previewImage)
      // Keep path references bounded too; protected visible keys survive eviction.
      if (previewImageCache.value.size > 72) {
        const stale = [...previewImageCache.value.keys()].find(k => !currentPageKeys.value.includes(k))
        if (stale) { previewImageCache.value.delete(stale); const old = templateDetails.value.get(stale); if (old) old.previewImage = null }
      }
      const detail = templateDetails.value.get(key)
      if (detail) {
        detail.previewImage = previewImage
        detail.isLoadingPreview = false
      }
      return previewImage
    } catch (error) {
      console.error(`获取模板 ${key} 预览图片失败:`, error)
      return null
    } finally {
      loadingStates.value.delete(key)
    }
  }

  const ensurePageLoaded = async (uiCategoryKey, pageNumber, background = false) => {
    const rawKeys = categoryKeys.value[CATEGORY_UI_TO_API[uiCategoryKey]] || []
    const keys = sortMode.value === 'explore' ? [...rawKeys].sort((a,b) => a.localeCompare(b)) : rawKeys
    if (pageNumber < 1) return
    const pageKeys = keys.slice((pageNumber - 1) * templatesPerPage, pageNumber * templatesPerPage)
    if (!background) setThumbnailWindow([...pageKeys,...keys.slice(0,3)])
    if (!pageKeys.length || pageKeys.every(key => previewImageCache.value.has(key))) return
    const taskKey = `${uiCategoryKey}:${pageNumber}`
    if (!background) { visibleLoads++; isLoadingTemplates.value = true }
    try {
      if (!pageTasks.has(taskKey)) {
        const task = Promise.allSettled(pageKeys.map(key => {
          if (!templateDetails.value.has(key)) templateDetails.value.set(key, { key, name: key, previewImage: null, isLoadingPreview: true })
          // Old backends without a card manifest still load names correctly.
          if (templateDetails.value.get(key).name === key) fetchMemeInfo(key)
          return fetchMemePreview(key, background)
        })).finally(() => pageTasks.delete(taskKey))
        pageTasks.set(taskKey, task)
      }
      await pageTasks.get(taskKey)
    } finally {
      if (!background) { visibleLoads--; isLoadingTemplates.value = visibleLoads > 0 }
    }
  }

  const prefetchAdjacent = (category, page) => {
    // No loading spinner or navigation blocking for speculative downloads.
    return Promise.allSettled([page + 1, page - 1, page + 2].map(p => ensurePageLoaded(category, p, true)))
  }

  const selectCategory = async (categoryKey) => {
    selectedCategory.value = categoryKey
    currentPage.value = 1
    showStatusMessage && showStatusMessage(`已切换到${categories.value.find(c => c.key === categoryKey)?.name}分类`)
    await ensurePageLoaded(categoryKey, 1)
  }

  const prevPage = () => { if (currentPage.value > 1) currentPage.value-- }
  const nextPage = () => { if (currentPage.value < totalPages.value) currentPage.value++ }

  return {
    // state
    isLoadingTemplates,
    loadError,
    templateDetails,
    previewImageCache,
    loadingStates,
    selectedCategory,
    categories,
    currentPage,
    totalPages,
    currentPageTemplates,
    sortMode,
    spotlight: computed(() => currentCategoryAllKeys.value.slice(0,3).map(key => templateDetails.value.get(key)).filter(Boolean)),
    // actions
    fetchMemeCategories,
    fetchMemeInfo,
    fetchMemePreview,
    ensurePageLoaded,
    prefetchAdjacent,
    selectCategory,
    prevPage,
    nextPage,
  }
}
