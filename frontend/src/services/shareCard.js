import { API_BASE_URL } from '@/constants'

// A versioned 5:4 cover is fetched by WeChat; it adds no images to the mini-
// program package and needs no image generation or canvas work on the device.
export function shareCard({template='',image=''}={}) {
  return {
    title:image?'我刚造的梗，你也来整一张？':'让世界更有趣，来做你的专属表情包',
    path:'/pages/index/index'+(template?'?template='+encodeURIComponent(template):''),
    imageUrl:image || `${API_BASE_URL}/share/cover-v2.jpg`,
  }
}
