import { ref } from 'vue'
import { parseRange } from '@/utils/validationUtils'

export function useTemplateInput() {
  const templateImages = ref([])
  const textInputs = ref([])
  const selectedTemplateDetail = ref(null)

  const getImageInputCount = () => {
    const info = selectedTemplateDetail.value
    if (!info) return 0
    const { min, max } = parseRange(info.imageCount)
    return Math.max(min, 0)
  }

  const getImageUploadText = () => {
    const info = selectedTemplateDetail.value
    if (!info) return '请上传图片'
    const { min, max } = parseRange(info.imageCount)
    if (max === 0) return '此模板不需要图片'
    const current = templateImages.value.length
    if (current >= max) return `已上传 ${current} 张图片（最多${max}张）`
    if (min > 0 && current < min) return `还需要上传 ${min - current} 张图片（最少${min}张，最多${max}张）`
    return `已上传 ${current} 张图片（最多${max}张）`
  }

  const getTextInputRange = () => {
    const info = selectedTemplateDetail.value
    if (!info) return { min: 0, max: 0 }
    return parseRange(info.textCount)
  }

  const getTextInputMax = () => getTextInputRange().max

  const getTextPlaceholder = (index) => {
    const defaults = selectedTemplateDetail.value?.defaultTexts || []
    return defaults[index] || `请输入文本${index + 1}`
  }

  const getTextMaxLength = () => 100

  const initializeTemplateInputs = (detail) => {
    selectedTemplateDetail.value = detail || null
    templateImages.value = []
    const { max } = getTextInputRange()
    const defaults = selectedTemplateDetail.value?.defaultTexts || []
    if (max > 0) {
      const arr = new Array(max).fill('')
      for (let i = 0; i < Math.min(max, defaults.length); i++) arr[i] = defaults[i]
      textInputs.value = arr
    } else {
      textInputs.value = []
    }
  }

  const isTemplateInputValid = () => {
    const info = selectedTemplateDetail.value
    if (!info) return false
    const { min: imgMin, max: imgMax } = parseRange(info.imageCount)
    if (imgMax > 0) {
      const n = templateImages.value.length
      if (n < imgMin || n > imgMax) return false
    }
    const { min: textMin, max: textMax } = getTextInputRange()
    if (textMax > 0) {
      const filled = textInputs.value.filter(t => (t || '').trim().length > 0).length
      if (filled < textMin || filled > textMax) return false
    }
    return true
  }

  const chooseImagesForTemplate = () => {
    const info = selectedTemplateDetail.value
    if (!info) return
    const { min, max } = parseRange(info.imageCount)
    if (max === 0) return
    const remaining = max - templateImages.value.length
    if (remaining <= 0) return

    uni.chooseImage({
      count: remaining,
      sizeType: ['compressed'],
      sourceType: ['album', 'camera'],
      success: (res) => {
        const newImages = [...templateImages.value, ...res.tempFilePaths]
        templateImages.value = newImages
      },
    })
  }

  const removeTemplateImage = (index) => { templateImages.value.splice(index, 1) }

  const resetInputs = () => {
    templateImages.value = []
    textInputs.value = []
    selectedTemplateDetail.value = null
  }

  return {
    templateImages,
    textInputs,
    selectedTemplateDetail,
    getImageInputCount,
    getImageUploadText,
    getTextInputRange,
    getTextInputMax,
    getTextPlaceholder,
    getTextMaxLength,
    initializeTemplateInputs,
    isTemplateInputValid,
    chooseImagesForTemplate,
    removeTemplateImage,
    resetInputs,
  }
} 