import { GifReader } from 'omggif'

export const MAX_COLLAGE_DURATION = 15000
export const MAX_COLLAGE_FRAMES = 300
export const MAX_SOURCE_PIXELS = 1500000

export const isGif = bytes => bytes.length >= 6 &&
  bytes[0] === 71 && bytes[1] === 73 && bytes[2] === 70 &&
  bytes[3] === 56 && (bytes[4] === 55 || bytes[4] === 57) && bytes[5] === 97

// GIF frames are often transparent patches, rather than independent pictures.
// Keep only the current composited frame and the disposal-3 restore buffer.
export function openCollageGif(bytes) {
  let reader
  try {
    if (bytes[bytes.length-1]!==59) throw Error('Missing GIF trailer')
    reader = new GifReader(bytes)
  } catch (_) { throw Error('有一张动图无法读取，请换一张后重试') }
  const {width,height} = reader, count = reader.numFrames()
  if (!width || !height || width*height > MAX_SOURCE_PIXELS || count < 1 || count > 300)
    throw Error('有一张动图尺寸或帧数过大，请减少所选图片或换一张')
  const frames = Array.from({length:count}, (_,index) => reader.frameInfo(index))
  if (frames.some(frame => !frame.width || !frame.height || frame.x+frame.width > width || frame.y+frame.height > height || frame.data_offset+frame.data_length>bytes.length-1))
    throw Error('有一张动图的画面数据不完整，请换一张后重试')
  // Match browser playback for an unspecified/one-centisecond GIF delay.
  const delays = frames.map(frame => frame.delay < 2 ? 100 : frame.delay*10)
  const duration = delays.reduce((sum,delay) => sum+delay,0)
  if (duration > MAX_COLLAGE_DURATION) throw Error('单张动图最长支持 15 秒，请换一张较短的动图')
  let pixels = new Uint8ClampedArray(width*height*4), previous = null, index = -1, cycle = -1
  const hasBackground = !!(bytes[10]&128), offset = 13+bytes[11]*3
  const background = hasBackground ? [bytes[offset],bytes[offset+1],bytes[offset+2],255] : [0,0,0,0]
  const clear = (frame, transparent) => {
    const color = transparent ? [0,0,0,0] : background
    for (let y=frame.y;y<frame.y+frame.height;y++) {
      const start=(y*width+frame.x)*4, end=start+frame.width*4
      if (!color[3]) pixels.fill(0,start,end)
      else for (let p=start;p<end;p+=4) pixels.set(color,p)
    }
  }
  const reset = () => {
    pixels.fill(0)
    if (frames[0].transparent_index === null) clear({x:0,y:0,width,height},false)
    index=-1
  }
  return {
    width,height,delays,duration,animated:count>1,
    framePixels:frames.reduce((sum,frame)=>sum+frame.width*frame.height,0),
    at(milliseconds) {
      const nextCycle=Math.floor(milliseconds/duration), time=milliseconds%duration
      let target=0,end=delays[0]
      while (target<count-1 && time>=end) end+=delays[++target]
      if (nextCycle!==cycle || target<index) {reset();cycle=nextCycle}
      while (index<target) {
        const last=frames[index]
        if (last?.disposal===2) clear(last,last.transparent_index!==null)
        else if (last?.disposal===3 && previous) pixels.set(previous)
        const next=frames[++index]
        if (next.disposal===3) {
          if (!previous) previous=new Uint8ClampedArray(pixels.length)
          previous.set(pixels)
        }
        reader.decodeAndBlitFrameRGBA(index,pixels)
      }
      return pixels
    },
    close() {reader=null;pixels=null;previous=null},
  }
}

// Every GIF keeps its own timing. Shorter GIFs repeat until the longest has
// completed a cycle. Bound dense timelines without shortening their duration.
export function collageTimeline(sources,maxFrames=MAX_COLLAGE_FRAMES) {
  const animated=sources.filter(source=>source.animated)
  const duration=Math.max(0,...animated.map(source=>source.duration))
  if (!duration) return [0]
  const times=new Set([0,duration])
  for (const source of animated) {
    for (let base=0;base<duration;base+=source.duration) {
      let time=base
      for (const delay of source.delays) {time+=delay;if(time<duration)times.add(time)}
    }
  }
  const ordered=[...times].sort((a,b)=>a-b)
  // Combining valid timelines can introduce 10 ms gaps, which our decoder
  // normalizes to 100 ms. Keep output timing consistent with its playback rules.
  const playable=times=>{
    const result=[0]
    for(const time of times.slice(1,-1))if(time-result[result.length-1]>=20&&duration-time>=20)result.push(time)
    result.push(duration);return result
  }
  if (ordered.length<=maxFrames+1) return playable(ordered)
  const step=Math.ceil(duration/maxFrames/10)*10
  return playable([...Array.from({length:Math.ceil(duration/step)},(_,index)=>index*step),duration])
}

// A shared color cube covers later scene changes too. Cache the nearest index
// per RGB555 bucket across ALL frames, rather than clustering every frame.
export function collagePalette(colors=256) {
  const palette=[[0,0,0]],levels=Math.max(2,Math.floor(Math.cbrt(colors-2)))
  for(let r=0;r<levels;r++)for(let g=0;g<levels;g++)for(let b=0;b<levels;b++)
    palette.push([r,g,b].map(v=>Math.round(v*255/(levels-1))))
  const paper=palette.length;palette.push([255,250,244])
  const grayStart=palette.length,grays=colors-grayStart
  for(let i=0;i<grays;i++){const v=Math.round(i*255/Math.max(1,grays-1));palette.push([v,v,v])}
  const cache=new Uint16Array(32768);cache.fill(65535)
  return {palette,map(rgba,previous){
    const indices=new Uint8Array(rgba.length/4),pixels=new Uint32Array(rgba.buffer,rgba.byteOffset,indices.length)
    for(let i=0;i<indices.length;i++){
      if(previous&&pixels[i]===previous[i])continue
      const p=i*4,r=rgba[p],g=rgba[p+1],b=rgba[p+2]
      if(r===255&&g===250&&b===244){indices[i]=paper;continue}
      const key=(r>>3)<<10|(g>>3)<<5|b>>3
      let index=cache[key]
      if(index===65535){
        const rr=(r&248)+4,gg=(g&248)+4,bb=(b&248)+4
        index=1+Math.round(rr*(levels-1)/255)*levels*levels+Math.round(gg*(levels-1)/255)*levels+Math.round(bb*(levels-1)/255)
        if(grays){
          const gray=grayStart+Math.round(((rr+gg+bb)/3)*(grays-1)/255),c=palette[index],v=palette[gray][0]
          if((rr-v)**2+(gg-v)**2+(bb-v)**2<(rr-c[0])**2+(gg-c[1])**2+(bb-c[2])**2)index=gray
        }
        cache[key]=index
      }
      indices[i]=index
    }
    return {indices,pixels}
  }}
}
