export function toDataUri(base64Str, contentTypeHint) {
  const normalizedType = (contentTypeHint || '').toLowerCase()
  let mime = 'image/gif'
  if (normalizedType.startsWith('image/')) mime = normalizedType
  if (typeof base64Str === 'string' && base64Str.startsWith('data:image/')) return base64Str
  return `data:${mime};base64,${base64Str}`
}

export function arrayBufferToDataUri(arrayBuf, contentType = 'image/gif') {
  const base64 = uni.arrayBufferToBase64(arrayBuf)
  return toDataUri(base64, contentType)
}

export async function h5PathToBlob(path) {
  const resp = await fetch(path)
  if (!resp.ok) throw new Error(`读取本地图片失败: ${resp.status}`)
  return await resp.blob()
}

export function downloadDataUriInH5(dataUri, filename = 'meme.png') {
  try {
    const link = document.createElement('a')
    link.href = dataUri
    link.download = filename
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  } catch (e) {
    console.error('H5 下载失败:', e)
  }
}

export function getFileExtensionFromContentType(ct) {
  if (!ct) return 'png'
  const map = {
    'image/png': 'png',
    'image/jpeg': 'jpg',
    'image/jpg': 'jpg',
    'image/gif': 'gif',
    'image/webp': 'webp',
  }
  const key = String(ct).toLowerCase()
  return map[key] || 'png'
} 