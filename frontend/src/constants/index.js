// API 与应用常量
let baseUrl = import.meta.env.VITE_API_BASE_URL || '/api'
// #ifdef MP-WEIXIN
// Scan-code previews and real devices always use the public HTTPS backend.
// A local H5 test environment must not override a mini-program build.
baseUrl = 'https://www.shangkun.uk/gensticker/api'
// #endif
export const API_BASE_URL = baseUrl.replace(/\/$/, '')

export const PAGINATION = {
  templatesPerPage: 9,
}

export const CATEGORY_UI_TO_API = {
  all: 'all',
  text: 'text_only',
  image: 'image_only',
  mixed: 'mixed',
}
