import { API_BASE_URL } from '@/constants'

export async function apiRequest(url, options = {}, retries = 3) {
  for (let i = 0; i < retries; i++) {
    try {
      const response = await uni.request({
        url: `${API_BASE_URL}${url}`,
        method: options.method || 'GET',
        data: options.data,
        header: options.header || {},
        timeout: options.timeout || 10000,
      })

      if (response.statusCode === 200) {
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
        throw new Error(`API请求失败: ${response.statusCode}`)
      }
    } catch (error) {
      if (i === retries - 1) throw error
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