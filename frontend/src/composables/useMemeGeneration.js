import { ref } from 'vue'
import { prepareImage, prepareImages } from '@/services/imagePreparation'
import { tryClientRender } from '@/services/clientRenderer'
import { visitorHeaders } from '@/services/popularityService'
import { API_BASE_URL } from '@/constants'
import { getGenerateUrl } from '@/services/memeService'
import { toDataUri, arrayBufferToDataUri, h5PathToBlob, downloadDataUriInH5, getFileExtensionFromContentType } from '@/utils/fileUtils'

export function useMemeGeneration(showStatusMessage) {
  const showPreview = ref(false)
  const isGenerating = ref(false)
  const generatedMeme = ref('')
  let lastGeneratedFile = ''
  let generationEpoch = 0

  const h5UploadMultipart = async (url, localPaths, extra) => {
    const form = new FormData()
    for (let i = 0; i < localPaths.length; i++) {
      const blob = await h5PathToBlob(localPaths[i])
      const ext = blob.type?.split('/')[1] || 'jpg'
      const fileName = `image_${i}.${ext}`
      form.append('images', blob, fileName)
    }
    if (extra?.texts && Array.isArray(extra.texts)) {
      for (const t of extra.texts) form.append('texts', t)
    }
    if (extra?.args && Object.keys(extra.args).length > 0) {
      form.append('args', JSON.stringify(extra.args))
    }
    form.append('extract_subject', String(!!extra?.options?.extractSubject))
    const resp = await fetch(url, { method: 'POST', body: form, headers:visitorHeaders() })
    const ct = resp.headers.get('content-type') || ''
    if (!resp.ok) throw new Error(`上传失败: ${resp.status}`)
    if (ct.startsWith('image/')) {
      const blob = await resp.blob()
      const arrayBuf = await blob.arrayBuffer()
      return toDataUri(uni.arrayBufferToBase64(arrayBuf), ct)
    } else if (ct.includes('application/json') || ct.includes('text/plain')) {
      const text = await resp.text()
      try {
        const parsed = JSON.parse(text)
        const maybeBase64 = parsed?.data || parsed?.image || parsed?.base64
        const pct = parsed?.content_type || ct
        if (maybeBase64) return toDataUri(maybeBase64, pct)
        if (parsed?.dataUri) return parsed.dataUri
        return text.startsWith('data:image/') ? text : toDataUri(text, ct)
      } catch (_) {
        return text.startsWith('data:image/') ? text : toDataUri(text, ct)
      }
    } else {
      const blob = await resp.blob()
      const arrayBuf = await blob.arrayBuffer()
      return toDataUri(uni.arrayBufferToBase64(arrayBuf), ct || 'image/gif')
    }
  }

  const weixinGenerate = async (templateKey, localPaths, texts, args, epoch, options) => {
    const fs = uni.getFileSystemManager()
    const images = []
    let totalSize = 0
    for (const originalPath of localPaths) {
      const filePath = await prepareImage(originalPath)
      const info = await new Promise((resolve, reject) => fs.stat({ path: filePath, success: resolve, fail: reject }))
      totalSize += info.stats.size
      if (totalSize > 10 * 1024 * 1024) throw new Error('图片总大小不能超过 10 MB')
      const image = await new Promise((resolve, reject) => fs.readFile({ filePath, encoding: 'base64', success: r => resolve(r.data), fail: reject }))
      images.push(image)
    }
    const response = await uni.request({
      url: `${API_BASE_URL}/memes/${encodeURIComponent(templateKey)}/generate`,
      method: 'POST',
      data: { images, texts, args, extract_subject:!!options?.extractSubject },
      header: { 'Content-Type': 'application/json', ...visitorHeaders() },
      timeout: 60000,
      responseType: 'arraybuffer',
    })
    if(epoch!==generationEpoch)return ''
    const ct = response.header?.['Content-Type'] || response.header?.['content-type'] || ''
    if (response.statusCode !== 200 || !ct.startsWith('image/')) {
      let detail = ''
      try { detail = JSON.parse(decodeURIComponent(Array.from(new Uint8Array(response.data).slice(0, 8192), b => '%' + b.toString(16).padStart(2, '0')).join(''))).detail || '' } catch (_) {}
      throw new Error(response.statusCode === 503 ? '服务繁忙，请稍后重试' : response.statusCode === 429 ? '操作太频繁，请稍后再生成' : detail || `生成请求失败: ${response.statusCode}`)
    }
    const filePath = `${uni.env.USER_DATA_PATH}/generated_meme_${Date.now()}.${getFileExtensionFromContentType(ct)}`
    await new Promise((resolve, reject) => fs.writeFile({ filePath, data: response.data, success: resolve, fail: reject }))
    if(epoch!==generationEpoch){fs.unlink({filePath,fail:()=>{}});return ''}
    if (lastGeneratedFile) fs.unlink({ filePath: lastGeneratedFile, fail: () => {} })
    lastGeneratedFile = filePath
    return filePath
  }

  const generateFromTemplate = async (templateKey, imagesToUpload, texts = [], args = {}, options = {}) => {
    if (isGenerating.value) return false
    const epoch = ++generationEpoch
    showPreview.value = true; isGenerating.value = true; generatedMeme.value = ''
    try {
      const isH5 = typeof window !== 'undefined' && typeof document !== 'undefined'
      if (!isH5 && !options.extractSubject) {
        const local = await tryClientRender(templateKey, await prepareImages(imagesToUpload), texts, args)
        if(epoch!==generationEpoch){if(local)uni.getFileSystemManager().unlink({filePath:local,fail:()=>{}});return false}
        if (local) {
          if (lastGeneratedFile) uni.getFileSystemManager().unlink({filePath:lastGeneratedFile,fail:()=>{}})
          lastGeneratedFile = local; generatedMeme.value = local; isGenerating.value = false
          showStatusMessage && showStatusMessage('表情已在本机生成！'); return true
        }
      }
      const output = isH5
        ? await h5UploadMultipart(`${API_BASE_URL}${getGenerateUrl(templateKey)}`, imagesToUpload, { args, texts, options })
        : await weixinGenerate(templateKey, imagesToUpload, texts, args, epoch, options)
      if(epoch!==generationEpoch)return false
      generatedMeme.value = output; isGenerating.value = false
      showStatusMessage && showStatusMessage('表情包生成成功！')
      return true
    } catch (error) {
      if(epoch!==generationEpoch)return false
      console.error('生成表情包失败:', error)
      isGenerating.value = false; showPreview.value = false
      const message = /timeout/i.test(error.errMsg || error.message || '') ? '网络传输超时，请检查连接后重试；大图会自动压缩' : error.message || error.errMsg || '请稍后重试'
      showStatusMessage && showStatusMessage(`生成失败: ${message}`)
      return false
    }
  }

  const closePreview = () => { generationEpoch++; showPreview.value = false; isGenerating.value = false; generatedMeme.value = '' }

  const saveMeme = () => {
    if (!generatedMeme.value) return
    const val = generatedMeme.value
    // #ifdef H5
    const mH5 = val.match(/^data:(image\/[a-zA-Z0-9.+-]+);base64,/)
    const extH5 = getFileExtensionFromContentType(mH5 ? mH5[1] : 'image/png')
    downloadDataUriInH5(val, `meme_${Date.now()}.${extH5}`)
    showStatusMessage && showStatusMessage('已开始下载')
    return
    // #endif

    // #ifdef MP-WEIXIN
    const mWX = val.match(/^data:(image\/[a-zA-Z0-9.+-]+);base64,(.+)$/)
    if (mWX) {
      const fs = uni.getFileSystemManager()
      const ext = getFileExtensionFromContentType(mWX[1])
      const filePath = `${uni.env.USER_DATA_PATH}/meme_${Date.now()}.${ext}`
      fs.writeFile({
        filePath,
        data: mWX[2],
        encoding: 'base64',
        success: () => {
          uni.saveImageToPhotosAlbum({
            filePath,
            success: () => showStatusMessage && showStatusMessage('已保存到相册！'),
            fail: () => showStatusMessage && showStatusMessage('保存失败，请检查权限设置'),
          })
        },
        fail: () => showStatusMessage && showStatusMessage('保存失败，请重试'),
      })
      return
    }
    uni.saveImageToPhotosAlbum({
      filePath: val,
      success: () => showStatusMessage && showStatusMessage('已保存到相册！'),
      fail: () => showStatusMessage && showStatusMessage('保存失败，请重试'),
    })
    return
    // #endif

    // #ifdef APP-PLUS
    const mAPP = val.match(/^data:(image\/[a-zA-Z0-9.+-]+);base64,(.+)$/)
    if (mAPP) {
      const ext = getFileExtensionFromContentType(mAPP[1])
      const bitmap = new plus.nativeObj.Bitmap(`meme_${Date.now()}`)
      bitmap.loadBase64Data(val, () => {
        const filePath = `_doc/meme_${Date.now()}.${ext}`
        bitmap.save(filePath, {}, () => {
          plus.gallery.save(filePath, () => {
            showStatusMessage && showStatusMessage('已保存到相册！')
            bitmap.clear()
          }, () => {
            showStatusMessage && showStatusMessage('保存失败，请重试')
            bitmap.clear()
          })
        }, () => {
          showStatusMessage && showStatusMessage('保存失败，请重试')
          bitmap.clear()
        })
      }, () => {
        showStatusMessage && showStatusMessage('保存失败，请重试')
      })
      return
    }
    uni.saveImageToPhotosAlbum({
      filePath: val,
      success: () => showStatusMessage && showStatusMessage('已保存到相册！'),
      fail: () => showStatusMessage && showStatusMessage('保存失败，请重试'),
    })
    return
    // #endif

    uni.saveImageToPhotosAlbum({
      filePath: val,
      success: () => showStatusMessage && showStatusMessage('已保存到相册！'),
      fail: () => showStatusMessage && showStatusMessage('保存失败，请重试'),
    })
  }

  const shareMeme = () => {
    if (generatedMeme.value) {
      // #ifdef MP-WEIXIN
      uni.showShareImageMenu({
        path: generatedMeme.value,
        fail: () => showStatusMessage && showStatusMessage('请先保存到相册，再从微信发送图片'),
      })
      return
      // #endif
      // #ifndef MP-WEIXIN
      uni.share({
        provider: 'weixin',
        scene: 'WXSceneSession',
        type: 2,
        imageUrl: generatedMeme.value,
        success: () => showStatusMessage && showStatusMessage('分享成功！'),
        fail: () => showStatusMessage && showStatusMessage('分享失败，请重试'),
      })
      // #endif
    }
  }

  return { showPreview, isGenerating, generatedMeme, generateFromTemplate, closePreview, saveMeme, shareMeme }
}
