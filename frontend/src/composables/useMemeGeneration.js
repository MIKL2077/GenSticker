import { ref } from 'vue'
import { API_BASE_URL } from '@/constants'
import { getGenerateUrl } from '@/services/memeService'
import { toDataUri, arrayBufferToDataUri, h5PathToBlob, downloadDataUriInH5, getFileExtensionFromContentType } from '@/utils/fileUtils'

export function useMemeGeneration(showStatusMessage) {
  const showPreview = ref(false)
  const isGenerating = ref(false)
  const generatedMeme = ref('')

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
    const resp = await fetch(url, { method: 'POST', body: form })
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

  const generateFromTemplate = async (templateKey, imagesToUpload, texts = [], args = {}) => {
    showPreview.value = true
    isGenerating.value = true
    generatedMeme.value = ''
    try {
      const isH5 = typeof window !== 'undefined' && typeof document !== 'undefined'
      const targetUrl = `${API_BASE_URL}${getGenerateUrl(templateKey)}`
      if (imagesToUpload.length > 0) {
        if (isH5) {
          const dataUri = await h5UploadMultipart(targetUrl, imagesToUpload, { args, texts })
          generatedMeme.value = dataUri
        } else {
          const files = imagesToUpload.map((imagePath) => ({ name: 'images', filePath: imagePath }))
          const formData = {}
          if (Object.keys(args).length > 0) formData.args = JSON.stringify(args)
          if (texts.length > 0) formData.texts = JSON.stringify(texts)
          const uploadRes = await new Promise((resolve, reject) => {
            uni.uploadFile({
              url: targetUrl,
              files,
              formData,
              header: {},
              timeout: 60000,
              success: (res) => resolve(res),
              fail: (err) => reject(err),
            })
          })
          if (uploadRes.statusCode === 200) {
            const contentType = uploadRes.header?.['Content-Type'] || uploadRes.header?.['content-type'] || ''
            const data = uploadRes.data
            if (typeof data === 'string') {
              try {
                const parsed = JSON.parse(data)
                const maybeBase64 = parsed?.data || parsed?.image || parsed?.base64
                const ct = parsed?.content_type || contentType
                if (maybeBase64) generatedMeme.value = toDataUri(maybeBase64, ct)
                else if (parsed?.dataUri) generatedMeme.value = parsed.dataUri
                else generatedMeme.value = data.startsWith('data:image/') ? data : toDataUri(data, contentType)
              } catch (_) {
                generatedMeme.value = data.startsWith('data:image/') ? data : toDataUri(data, contentType)
              }
            } else if (data) {
              if (typeof data === 'string') {
                generatedMeme.value = data.startsWith('data:image/') ? data : toDataUri(data, contentType)
              } else {
                generatedMeme.value = toDataUri(uni.arrayBufferToBase64(data), contentType)
              }
            } else {
              throw new Error('服务器返回数据为空')
            }
          } else {
            throw new Error(`上传失败: ${uploadRes.statusCode}`)
          }
        }
      } else {
        if (isH5) {
          const dataUri = await h5UploadMultipart(targetUrl, [], { args, texts })
          generatedMeme.value = dataUri
        } else {
          const response = await uni.request({
            url: targetUrl,
            method: 'POST',
            data: { texts, args },
            header: { 'Content-Type': 'application/json' },
            timeout: 30000,
            responseType: 'arraybuffer',
          })
          if (response.statusCode === 200) {
            const contentType = response.header?.['Content-Type'] || response.header?.['content-type'] || 'image/gif'
            const data = response.data
            if (typeof data === 'string') generatedMeme.value = data.startsWith('data:image/') ? data : toDataUri(data, contentType)
            else generatedMeme.value = arrayBufferToDataUri(data, contentType)
          } else {
            throw new Error(`请求失败: ${response.statusCode}`)
          }
        }
      }
      isGenerating.value = false
      showStatusMessage && showStatusMessage('表情包生成成功！')
    } catch (error) {
      console.error('生成表情包失败:', error)
      isGenerating.value = false
      showStatusMessage && showStatusMessage(`生成失败: ${error.message}`)
    }
  }

  const closePreview = () => { showPreview.value = false; isGenerating.value = false; generatedMeme.value = '' }

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
      uni.share({
        provider: 'weixin',
        scene: 'WXSceneSession',
        type: 2,
        imageUrl: generatedMeme.value,
        success: () => showStatusMessage && showStatusMessage('分享成功！'),
        fail: () => showStatusMessage && showStatusMessage('分享失败，请重试'),
      })
    }
  }

  return { showPreview, isGenerating, generatedMeme, generateFromTemplate, closePreview, saveMeme, shareMeme }
} 