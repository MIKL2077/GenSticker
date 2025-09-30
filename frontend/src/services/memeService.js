import { apiRequest, apiImageRequest } from '@/services/apiService'

export async function getCategories() {
  return await apiRequest('/memes/categories')
}

export async function getTemplateInfo(key) {
  return await apiRequest(`/memes/${key}/info`)
}

export async function getTemplatePreviewData(key) {
  return await apiImageRequest(`/memes/${key}/preview`)
}

// 生成接口仅提供 URL，具体上传在组合式中按平台处理
export function getGenerateUrl(templateKey) {
  return `/memes/${templateKey}/`
} 