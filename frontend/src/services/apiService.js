import { API_BASE_URL } from '@/constants'
import { requestError } from '@/services/networkErrors'

export async function apiRequest(url, options = {}, retries = 3) {
  for (let i = 0; i < retries; i++) {
    try {
      const response = await uni.request({
        url: `${API_BASE_URL}${url}`,
        method: options.method || 'GET',
        data: options.data,
        header: {
          ...((url === '/account' || url === '/templates/reports' || url.startsWith('/account/') || url.startsWith('/auth/') || url.startsWith('/recommend/') || url.startsWith('/studio/')) && options.auth !== false && uni.getStorageSync('gensticker.session.v1')?.access_token
            ? { Authorization: `Bearer ${uni.getStorageSync('gensticker.session.v1').access_token}` } : {}),
          ...options.header,
        },
        timeout: options.timeout || 10000,
      })

      if (response.statusCode >= 200 && response.statusCode < 300) {
        if (response.statusCode === 204) return null
        if (typeof response.data === 'string') {
          const text = response.data.trim()
          if (text.startsWith('<!DOCTYPE') || text.startsWith('<html')) {
            throw new Error('服务器返回了HTML页面，可能是路径错误或服务未启动')
          }
          try {
            return JSON.parse(text)
          } catch (e) {
            throw new Error('API返回数据格式错误，无法解析为JSON')
          }
        }
        return response.data
      } else if (response.statusCode >= 500 && i < retries - 1) {
        await new Promise(r => setTimeout(r, 1000 * (i + 1)))
        continue
      } else {
        if(url.startsWith('/studio/') && response.statusCode===404 && (!response.data?.detail || response.data.detail==='Not Found')){const unavailable=new Error('模板工作室还在等待服务器更新，基础表情生成可继续使用');unavailable.statusCode=404;throw unavailable}
        const error = new Error(typeof response.data?.detail === 'string' ? response.data.detail : `请求失败: ${response.statusCode}`)
        error.statusCode = response.statusCode
        error.retryAfter = Number(response.header?.['Retry-After'] || response.header?.['retry-after']) || 0
        throw error
      }
    } catch (failure) {
      const error=requestError(failure)
      if (i === retries - 1 || error.retryable===false || (error.statusCode >= 400 && error.statusCode < 500)) throw error
      await new Promise(r => setTimeout(r, 1000 * (i + 1)))
    }
  }
}

export async function apiImageRequest(url, options = {}, retries = 3) {
  for (let i = 0; i < retries; i++) {
    try {
      const response = await uni.request({
        url: `${API_BASE_URL}${url}`,
        method: 'GET',
        responseType: 'arraybuffer',
        header: options.header || {},
        timeout: options.timeout || 15000,
      })

      if (response.statusCode === 200) {
        return response.data
      } else if (response.statusCode >= 500 && i < retries - 1) {
        await new Promise(r => setTimeout(r, 1000 * (i + 1)))
        continue
      } else {
        throw new Error(`获取图片失败: ${response.statusCode}`)
      }
    } catch (error) {
      if (i === retries - 1) throw error
      await new Promise(r => setTimeout(r, 1000 * (i + 1)))
    }
  }
}
