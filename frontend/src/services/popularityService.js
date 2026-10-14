import { apiRequest } from '@/services/apiService'

export function visitorHeaders() {
  let id = uni.getStorageSync('gensticker.visitor.v1')
  if (!id) { id = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}-${Math.random().toString(36).slice(2)}`; uni.setStorageSync('gensticker.visitor.v1', id) }
  const token = uni.getStorageSync('gensticker.session.v1')?.access_token
  return { 'X-Gensticker-Visitor': id, ...(token ? { Authorization: `Bearer ${token}` } : {}) }
}

export function trackTemplate(key, kind, receipt = '') {
  return apiRequest('/templates/events', { method: 'POST', data: { key, kind, receipt }, header: visitorHeaders() }, 1).catch(() => {})
}
