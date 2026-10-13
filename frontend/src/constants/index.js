// API 与应用常量
let defaultBaseUrl = '/api'
// #ifdef MP-WEIXIN
defaultBaseUrl = 'https://www.shangkun.uk/gensticker/api'
// #endif
export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || defaultBaseUrl).replace(/\/$/, '')

export const PAGINATION = {
  templatesPerPage: 9,
}

export const CATEGORY_UI_TO_API = {
  all: 'all',
  text: 'text_only',
  image: 'image_only',
  mixed: 'mixed',
}
