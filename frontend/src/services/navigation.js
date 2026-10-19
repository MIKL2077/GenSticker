export function openRecommend() {
  const pages = typeof getCurrentPages === 'function' ? getCurrentPages() : []
  if (pages[pages.length - 1]?.route === 'pages/recommend/index') return
  const previous = pages.map(p => p.route).lastIndexOf('pages/recommend/index')
  if (previous >= 0) return uni.navigateBack({ delta: pages.length - 1 - previous })
  return uni.navigateTo({ url: '/pages/recommend/index',animationType:'none' })
}
