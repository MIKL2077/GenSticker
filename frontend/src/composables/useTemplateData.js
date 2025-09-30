import { ref, computed } from 'vue'
import { PAGINATION, CATEGORY_UI_TO_API } from '@/constants'
import { getCategories, getTemplateInfo, getTemplatePreviewData } from '@/services/memeService'

export function useTemplateData(showStatusMessage) {
  const isLoadingTemplates = ref(false)
  const templateDetails = ref(new Map())
  const previewImageCache = ref(new Map())
  const loadingStates = ref(new Map())

  const selectedCategory = ref('all')
  const categories = ref([
    { key: 'all', name: '全部', icon: '🎭', count: 0 },
    { key: 'text', name: '仅文字', icon: '📝', count: 0 },
    { key: 'image', name: '仅图片', icon: '📷', count: 0 },
    { key: 'mixed', name: '图文混合', icon: '📝+📷', count: 0 },
  ])

  const currentPage = ref(1)

  const categoryKeys = ref({ all: [], text_only: [], image_only: [], mixed: [] })
  const categoryLoadedPages = ref(new Map()) // Map<uiCategoryKey, Set<number>>

  const templatesPerPage = PAGINATION.templatesPerPage

  const currentCategoryAllKeys = computed(() => {
    const apiKey = CATEGORY_UI_TO_API[selectedCategory.value]
    return categoryKeys.value[apiKey] || []
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
      const data = await getCategories()
      categoryKeys.value = {
        all: Array.isArray(data.all) ? data.all : [],
        text_only: Array.isArray(data.text_only) ? data.text_only : [],
        image_only: Array.isArray(data.image_only) ? data.image_only : [],
        mixed: Array.isArray(data.mixed) ? data.mixed : [],
      }
      categories.value = categories.value.map(c => {
        const apiKey = CATEGORY_UI_TO_API[c.key]
        const len = categoryKeys.value[apiKey]?.length || 0
        return { ...c, count: len }
      })
    } catch (error) {
      console.error('获取分类失败:', error)
      showStatusMessage && showStatusMessage(`获取分类失败: ${error.message}`)
    } finally {
      isLoadingTemplates.value = false
    }
  }

  const fetchMemeInfo = async (key) => {
    try {
      if (templateDetails.value.has(key)) {
        const existing = templateDetails.value.get(key)
        if (existing && (existing.textCount !== '0-0' || existing.imageCount !== '0-0')) return existing
      }
      const info = await getTemplateInfo(key)
      const existingDetail = templateDetails.value.get(key) || { key }
      existingDetail.key = info.key
      existingDetail.name = info.key
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

  const fetchMemePreview = async (key) => {
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
      const imageData = await getTemplatePreviewData(key)
      const base64 = uni.arrayBufferToBase64(imageData)
      const previewImage = `data:image/gif;base64,${base64}`
      previewImageCache.value.set(key, previewImage)
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

  const ensurePageLoaded = async (uiCategoryKey, pageNumber) => {
    const apiCategoryKey = CATEGORY_UI_TO_API[uiCategoryKey]
    const keys = categoryKeys.value[apiCategoryKey] || []
    if (!keys.length) return
    if (!categoryLoadedPages.value.has(uiCategoryKey)) {
      categoryLoadedPages.value.set(uiCategoryKey, new Set())
    }
    const loadedSet = categoryLoadedPages.value.get(uiCategoryKey)
    if (loadedSet.has(pageNumber)) return

    const start = (pageNumber - 1) * templatesPerPage
    const end = start + templatesPerPage
    const pageKeys = keys.slice(start, end)
    if (!pageKeys.length) return

    isLoadingTemplates.value = true
    try {
      pageKeys.forEach((key) => {
        if (!templateDetails.value.has(key)) {
          templateDetails.value.set(key, {
            key,
            name: key,
            keywords: [],
            tags: [],
            imageCount: '0-0',
            textCount: '0-0',
            defaultTexts: [],
            previewImage: null,
            isLoadingPreview: true,
          })
        }
      })
      const detailPromises = pageKeys.map((key) => fetchMemeInfo(key))
      const previewPromises = pageKeys.map((key) => fetchMemePreview(key))
      await Promise.allSettled([
        Promise.allSettled(detailPromises),
        Promise.allSettled(previewPromises),
      ])
      loadedSet.add(pageNumber)
    } catch (e) {
      console.error('分页加载失败:', e)
    } finally {
      isLoadingTemplates.value = false
    }
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
    templateDetails,
    previewImageCache,
    loadingStates,
    selectedCategory,
    categories,
    currentPage,
    totalPages,
    currentPageTemplates,
    // actions
    fetchMemeCategories,
    fetchMemeInfo,
    fetchMemePreview,
    ensurePageLoaded,
    selectCategory,
    prevPage,
    nextPage,
  }
} 