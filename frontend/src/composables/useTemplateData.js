import { ref, computed, onUnmounted } from 'vue'
import { PAGINATION, CATEGORY_UI_TO_API } from '@/constants'
import { getCategories, getTemplateInfo, getTemplatePreviewPath, setThumbnailWindow, onThumbnailEvict } from '@/services/memeService'
import { seedClientRecipes } from '@/services/clientRenderer'
import {listMyTemplates,privateImage} from '@/services/studioService'

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
  const searchQuery=ref('')
  const normalizeSearch=value=>String(value||'').normalize('NFKC').toLowerCase().replace(/\s+/g,' ').trim()
  const setSearchQuery=value=>{searchQuery.value=String(value||'').slice(0,80);currentPage.value=1}
  const libraryMode=ref('warehouse'),mineKeys=ref([]),favoriteKeys=ref([]),mineTemplates=ref([])

  const categoryKeys = ref({ all: [], text_only: [], image_only: [], mixed: [] })
  // Ranking is global and independent of the template library's filters.
  const spotlight = computed(() => categoryKeys.value.all.map(key => templateDetails.value.get(key)).filter(item => item && item.heat > 0).sort((a,b) => b.heat - a.heat || a.key.localeCompare(b.key)).slice(0,3))
  const categoryLoadedPages = ref(new Map()) // Map<uiCategoryKey, Set<number>>

  const pageTasks = new Map()
  let visibleLoads = 0
  const templatesPerPage = PAGINATION.templatesPerPage

  const orderedKeys=(category)=>{
    let keys=categoryKeys.value[CATEGORY_UI_TO_API[category]] || []
    if(libraryMode.value==='mine'){
      const combined=[...new Set([...mineKeys.value,...favoriteKeys.value])]
      keys=category==='all'?combined:combined.filter(key=>{
        const d=templateDetails.value.get(key),im=Number(d?.imageCount?.split('-')[1]||0),tx=Number(d?.textCount?.split('-')[1]||0)
        return category==='image'?im>0&&!tx:category==='text'?tx>0&&!im:im>0&&tx>0
      })
    }
    const terms=normalizeSearch(searchQuery.value).split(' ').filter(Boolean)
    if(terms.length)keys=keys.filter(key=>{
      const d=templateDetails.value.get(key)||{}
      const text=normalizeSearch([key,d.templateId,d.name,...(d.keywords||[]),...(d.tags||[]),d.animated?'动图 GIF 动态':'静图 静态'].join(' '))
      return terms.every(term=>text.includes(term))
    })
    return [...keys].sort((a,b)=>{
      const x=templateDetails.value.get(a)||{},y=templateDetails.value.get(b)||{}
      if(sortMode.value==='hot')return (y.heat||0)-(x.heat||0)||a.localeCompare(b)
      if(sortMode.value==='cold')return (x.heat||0)-(y.heat||0)||a.localeCompare(b)
      if(sortMode.value==='old')return (x.createdAt||0)-(y.createdAt||0)||a.localeCompare(b)
      return (y.createdAt||0)-(x.createdAt||0)||a.localeCompare(b)
    })
  }
  const currentCategoryAllKeys=computed(()=>orderedKeys(selectedCategory.value))
  const searchResultCount=computed(()=>currentCategoryAllKeys.value.length)
  let mineOwner=''
  const loadMine=async favorites=>{
    const nextOwner=uni.getStorageSync('gensticker.session.v1')?.profile?.id||'guest'
    if(mineOwner!==nextOwner){for(const key of mineKeys.value){previewImageCache.value.delete(key);templateDetails.value.delete(key)}mineKeys.value=[];mineTemplates.value=[];mineOwner=nextOwner}
    favoriteKeys.value=favorites||[]
    if(!uni.getStorageSync('gensticker.session.v1')?.access_token){mineKeys.value=[];mineTemplates.value=[];return}
    const owner=uni.getStorageSync('gensticker.session.v1')?.profile?.id
    const data=await listMyTemplates();if(owner!==uni.getStorageSync('gensticker.session.v1')?.profile?.id)return;mineTemplates.value=data;mineKeys.value=data.map(t=>t.id)
    for(const item of data){const p=item.params_type;templateDetails.value.set(item.id,{...templateDetails.value.get(item.id),key:item.id,name:item.name,keywords:[item.name],tags:['我的模板'],metadataLoaded:true,imageCount:`${p.min_images}-${p.max_images}`,textCount:`${p.min_texts}-${p.max_texts}`,defaultTexts:p.default_texts,creator:item.creator,createdAt:item.created_at,status:item.status,message:item.message,ownPreview:item.preview_url,isLoadingPreview:true})}
  }

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

  const fetchMemeCategories = async (force=false) => {
    try {
      isLoadingTemplates.value = true
      loadError.value = ''
      const data = await getCategories(force)
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
        templateDetails.value.set(card.key, { ...existing, name:card.name, animated:!!card.animated, featuredTrial:!!card.featured_trial, inputHint:card.input_hint || '', keywords:card.keywords || [], tags:card.tags || [], heat:card.heat || 0, createdAt:card.created_at || 0, creator:card.creator, counts:card.counts || {}, localCapable:localKeys.has(card.key), ...(params ? {metadataLoaded:true, templateId:card.template_id, version:card.version, attribution:card.attribution || {}, imageCount:`${params.min_images}-${params.max_images}`, textCount:`${params.min_texts}-${params.max_texts}`, defaultTexts:params.default_texts || []} : {}) })
      }
      for(const card of data.cards || [])if(card.featured_trial)fetchMemePreview(card.key, true)
      spotlight.value.forEach(item => fetchMemePreview(item.key, true))
      categoryLoadedPages.value.clear()
      categories.value = categories.value.map(c => {
        const apiKey = CATEGORY_UI_TO_API[c.key]
        const len = categoryKeys.value[apiKey]?.length || 0
        return { ...c, count: len }
      })
    } catch (error) {
      console.error('获取分类失败:', error)
      loadError.value = `${error.message || error.errMsg || '模板暂时无法加载，请检查网络后重试'}${error.code ? '（'+error.code+'）' : ''}`
      showStatusMessage && showStatusMessage('模板加载失败，可查看页面提示后重试')
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
      existingDetail.creator=info.creator
      existingDetail.createdAt=info.created_at || 0
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
      const owned=templateDetails.value.get(key)?.ownPreview
      const previewImage = owned ? await privateImage(owned) : await getTemplatePreviewPath(key, background)
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
    const keys=orderedKeys(uiCategoryKey)
    if (pageNumber < 1) return
    const pageKeys = keys.slice((pageNumber - 1) * templatesPerPage, pageNumber * templatesPerPage)
    if (!background) setThumbnailWindow([...pageKeys,...spotlight.value.map(item=>item.key)])
    if (!pageKeys.length || pageKeys.every(key => previewImageCache.value.has(key))) return
    const taskKey = JSON.stringify([uiCategoryKey,pageNumber,libraryMode.value,sortMode.value,normalizeSearch(searchQuery.value)])
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
    searchQuery,setSearchQuery,searchResultCount,
    libraryMode,loadMine,mineTemplates,
    spotlight,
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
