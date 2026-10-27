import { API_BASE_URL } from '@/constants'

// A versioned 5:4 cover is fetched by WeChat; it adds no images to the mini-
// program package and needs no image generation or canvas work on the device.
const covers=['cover-v2.jpg','cover-v3.jpg','cover-v4.jpg','cover-v5.jpg']
let previousCover=-1

function randomCover() {
  // Select on each share callback, rather than once at page load. After the
  // first share, sample uniformly from the other covers to avoid repeats.
  const available=covers.map((_,index)=>index).filter(index=>index!==previousCover)
  const index=available[Math.floor(Math.random()*available.length)]
  previousCover=index
  return `${API_BASE_URL}/share/${covers[index]}`
}

export function shareCard({template='',image=''}={}) {
  return {
    title:image?'我刚造的梗，你也来整一张？':'让世界更有趣，来做你的专属表情包',
    path:'/pages/index/index'+(template?'?template='+encodeURIComponent(template):''),
    imageUrl:image || randomCover(),
  }
}
