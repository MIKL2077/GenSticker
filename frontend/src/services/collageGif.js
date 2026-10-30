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
export function collageTimeline(sources) {
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
  if (ordered.length<=MAX_COLLAGE_FRAMES+1) return ordered
  const step=Math.ceil(duration/MAX_COLLAGE_FRAMES/10)*10
  return [...Array.from({length:Math.ceil(duration/step)},(_,index)=>index*step),duration]
}
