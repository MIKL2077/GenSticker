import { ref } from 'vue'
import { prepareImages } from '@/services/imagePreparation'
import { parseRange } from '@/utils/validationUtils'
import { editImage, removeImageBackground, disposeEditedImage } from '@/services/imageEditing'

export function useTemplateInput() {
  const templateImages = ref([])
  const textInputs = ref([])
  const selectedTemplateDetail = ref(null)
  const extractSubject = ref(false)
  const activeImageIndex = ref(0), showImageEditor = ref(false), editorBusy = ref(false), editorError = ref(''), editorCanUndo = ref(false)
  let editEpoch = 0
  const records = [], owned = new Set()
  const release = path => { if(owned.delete(path))disposeEditedImage(path) }
  const syncUndo = () => { editorCanUndo.value=!!records[activeImageIndex.value]?.history.length }
  const cleanupImages = () => { editEpoch++;for(const path of owned)disposeEditedImage(path);owned.clear();records.length=0;showImageEditor.value=false;editorBusy.value=false;editorError.value='';editorCanUndo.value=false;activeImageIndex.value=0 }

  const getImageInputCount = () => {
    const info = selectedTemplateDetail.value
    if (!info) return 0
    const { min, max } = parseRange(info.imageCount)
    return Math.max(max, 0)
  }

  const getImageUploadText = () => {
    const info = selectedTemplateDetail.value
    if (!info) return '请上传图片'
    const { min, max } = parseRange(info.imageCount)
    if (max === 0) return '此模板不需要图片'
    if (!templateImages.value.length) return '选择图片或拍照，随后可裁剪、翻转和去背景'
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
    cleanupImages()
    selectedTemplateDetail.value = detail || null
    templateImages.value = []
    extractSubject.value = false
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
    if(editorBusy.value)return false
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
    const epoch=editEpoch

    uni.chooseImage({
      count: remaining,
      sizeType: ['compressed'],
      sourceType: ['album', 'camera'],
      success: (res) => {
        if(epoch!==editEpoch)return
        for(const path of res.tempFilePaths){records.push({original:path,history:[]});if(path.startsWith('blob:'))owned.add(path)}
        const firstNew=templateImages.value.length
        const newImages = [...templateImages.value, ...res.tempFilePaths]
        templateImages.value = newImages
        openImageEditor(firstNew)
        prepareImages(res.tempFilePaths).catch(() => {})
      },
    })
  }

  const openImageEditor = index => {
    if(editorBusy.value || !templateImages.value[index])return
    activeImageIndex.value=index;editorError.value='';showImageEditor.value=true;syncUndo()
  }
  const closeImageEditor = () => {editEpoch++;showImageEditor.value=false;editorBusy.value=false;editorError.value=''}
  const applyImageEdit = async operation => {
    const index=activeImageIndex.value, path=templateImages.value[index]
    if(editorBusy.value || !path)return
    const epoch=++editEpoch;editorBusy.value=true;editorError.value=''
    try {
      const output=operation.type==='background' ? await removeImageBackground(path) : await editImage(path,operation)
      if(epoch!==editEpoch || templateImages.value[index]!==path){disposeEditedImage(output);return}
      owned.add(output)
      const record=records[index] || (records[index]={original:path,history:[]})
      record.history.push(path)
      if(record.history.length>4){const old=record.history.shift();if(old!==record.original)release(old)}
      templateImages.value[index]=output;extractSubject.value=false;syncUndo();if(operation.complete)closeImageEditor();return true
    } catch(e) {if(epoch===editEpoch)editorError.value=e.message || e.errMsg || '编辑失败，原图已保留'}
    finally {if(epoch===editEpoch)editorBusy.value=false}
  }
  const undoImageEdit = () => {
    if(editorBusy.value)return
    const index=activeImageIndex.value,record=records[index]
    if(!record?.history.length)return
    const current=templateImages.value[index];templateImages.value[index]=record.history.pop();release(current);editorError.value='';syncUndo()
  }
  const restoreImage = () => {
    if(editorBusy.value)return
    const index=activeImageIndex.value,record=records[index]
    if(!record)return
    for(const path of [...record.history,templateImages.value[index]])if(path!==record.original)release(path)
    record.history=[];templateImages.value[index]=record.original;editorError.value='';syncUndo()
  }

  const removeTemplateImage = (index) => {
    if(editorBusy.value)return
    const record=records[index]
    if(record)for(const path of [...record.history,templateImages.value[index],record.original])release(path)
    records.splice(index,1);templateImages.value.splice(index,1);activeImageIndex.value=Math.max(0,Math.min(activeImageIndex.value,templateImages.value.length-1));syncUndo()
  }

  const resetInputs = () => {
    cleanupImages()
    extractSubject.value = false
    templateImages.value = []
    textInputs.value = []
    selectedTemplateDetail.value = null
  }

  return {
    templateImages,
    textInputs,
    selectedTemplateDetail,
    extractSubject,
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
    activeImageIndex, showImageEditor, editorBusy, editorError, editorCanUndo,
    openImageEditor, closeImageEditor, applyImageEdit, undoImageEdit, restoreImage,
    resetInputs,
  }
}
