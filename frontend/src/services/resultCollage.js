import { GIFEncoder, quantize, applyPalette } from 'gifenc'
import {registerTemporary,releaseTemporary,writeOwnedFile,withStorageRecovery} from '@/services/ownedFiles'
import {isGif,openCollageGif,collageTimeline} from '@/services/collageGif'

const MAX_INPUT_BYTES=8*1024*1024, MAX_TOTAL_BYTES=24*1024*1024
export const MAX_COLLAGE_BYTES=2*1024*1024
const pause=()=>new Promise(resolve=>setTimeout(resolve,0))
function deadline(promise) {
  let timer
  return Promise.race([promise,new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('拼图读取图片超时，请重试')),10000)})]).finally(()=>clearTimeout(timer))
}
function makeCanvas(width=1,height=1) {
  const result=typeof document!=='undefined'?document.createElement('canvas'):
    typeof wx!=='undefined'&&wx.createOffscreenCanvas?.({type:'2d',width,height})
  if (!result) throw Error('当前微信暂不支持拼图，请逐张分享或保存到相册')
  result.width=width;result.height=height;return result
}
async function readBytes(path) {
  if (typeof document!=='undefined') {
    const response=await fetch(path)
    if (!response.ok) throw Error('拼图读取图片失败，请重试')
    const blob=await response.blob()
    if (blob.size>MAX_INPUT_BYTES) throw Error('单张拼图原图不能超过 8 MB')
    return new Uint8Array(await blob.arrayBuffer())
  }
  const fs=uni.getFileSystemManager(),stat=await new Promise((resolve,reject)=>fs.stat({path,success:r=>resolve(r.stats),fail:reject}))
  if (stat.size>MAX_INPUT_BYTES) throw Error('单张拼图原图不能超过 8 MB')
  return new Uint8Array(await new Promise((resolve,reject)=>fs.readFile({filePath:path,success:r=>resolve(r.data),fail:reject})))
}
async function loadStill(path,canvas) {
  const image=typeof document!=='undefined'?new Image():canvas.createImage()
  await deadline(new Promise((resolve,reject)=>{
    image.onload=resolve;image.onerror=()=>reject(Error('拼图读取图片失败，请重试'));image.src=path
  }))
  if (!image.width || !image.height || image.width*image.height>4000000) throw Error('有一张图片尺寸过大，请换一张后重试')
  return image
}
export function collageLayout(count,animated,edge=240) {
  const columns=count===1?1:count<=4?2:3,rows=Math.ceil(count/columns),gap=animated?12:16
  const cell=animated?Math.min(edge,Math.floor((600-(columns+1)*gap)/columns)):320
  return {columns,cell,gap,width:columns*cell+(columns+1)*gap,height:rows*cell+(rows+1)*gap}
}
function drawSources(output,sources,layout,time) {
  const ctx=output.getContext('2d'),{width,height,cell,gap,columns}=layout
  ctx.fillStyle='#fffaf4';ctx.fillRect(0,0,width,height)
  sources.forEach((source,index)=>{
    const scale=Math.min(cell/source.width,cell/source.height),w=Math.max(1,Math.round(source.width*scale)),h=Math.max(1,Math.round(source.height*scale))
    let image=source.image
    if (source.gif) {
      const pixels=source.gif.at(time),surface=source.surface
      if (!source.imageData || surface.width!==w || surface.height!==h) {
        surface.width=w;surface.height=h;source.imageData=surface.getContext('2d').createImageData(w,h)
      }
      const data=source.imageData.data
      for (let y=0;y<h;y++) for (let x=0;x<w;x++) {
        const start=(Math.floor(y*source.height/h)*source.width+Math.floor(x*source.width/w))*4,out=(y*w+x)*4
        data[out]=pixels[start];data[out+1]=pixels[start+1];data[out+2]=pixels[start+2];data[out+3]=pixels[start+3]
      }
      surface.getContext('2d').putImageData(source.imageData,0,0);image=surface
    }
    ctx.drawImage(image,gap+(index%columns)*(cell+gap)+(cell-w)/2,gap+Math.floor(index/columns)*(cell+gap)+(cell-h)/2,w,h)
  })
}
async function exportStill(canvas) {
  if (typeof document!=='undefined') {
    const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/jpeg',.9))
    if (!blob) throw Error('拼图导出失败，请重试')
    return registerTemporary(URL.createObjectURL(blob))
  }
  const result=await withStorageRecovery(()=>new Promise((resolve,reject)=>wx.canvasToTempFilePath({canvas,fileType:'jpg',quality:.9,success:resolve,fail:reject})))
  return registerTemporary(result.tempFilePath)
}
async function exportGif(bytes) {
  if (typeof document!=='undefined') return registerTemporary(URL.createObjectURL(new Blob([bytes],{type:'image/gif'})))
  const path=`${uni.env.USER_DATA_PATH}/gensticker_edit_collage_${Date.now()}_${Math.random().toString(36).slice(2,8)}.gif`
  // Register first so cancellation/quota errors also clean partial files.
  registerTemporary(path)
  try {await writeOwnedFile(path,bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength));return path}
  catch (error) {releaseTemporary(path);throw error}
}

export async function createResultCollage(paths,{onProgress=()=>{},cancelled=()=>false}={}) {
  if (!paths.length || paths.length>9) throw Error('请选择 1 至 9 张表情')
  const expires=Date.now()+60000
  const check=()=>{
    if (cancelled()) throw Error('拼图制作已取消')
    if (Date.now()>expires) throw Error('这组动图制作耗时较长，请减少所选图片后重试')
  }
  const output=makeCanvas(),sources=[]
  let totalBytes=0,totalPixels=0,resultPath=''
  try {
    for (const [index,path] of paths.entries()) {
      check();onProgress(`正在读取表情 · ${index+1} / ${paths.length}`)
      let bytes=await deadline(readBytes(path));check()
      totalBytes+=bytes.length
      if (totalBytes>MAX_TOTAL_BYTES) throw Error('所选原图合计超过 24 MB，请减少所选图片')
      if (isGif(bytes)) {
        const gif=openCollageGif(bytes),source={gif,width:gif.width,height:gif.height}
        sources.push(source);source.surface=makeCanvas();totalPixels+=gif.width*gif.height
      } else {
        bytes=null
        const image=await loadStill(path,output);check()
        sources.push({image,width:image.width,height:image.height})
        totalPixels+=image.width*image.height
      }
      if (totalPixels>3000000) throw Error('这组图片尺寸过大，请减少所选图片后重试')
      await pause()
    }
    const gifs=sources.filter(source=>source.gif).map(source=>source.gif)
    const animated=gifs.some(gif=>gif.animated),timeline=collageTimeline(gifs),duration=animated?timeline[timeline.length-1]:0
    if (gifs.reduce((sum,gif)=>sum+Math.ceil((duration||gif.duration)/gif.duration)*gif.framePixels,0)>150000000)
      throw Error('这组动图画面较多，请减少所选图片后重试')
    if (!animated) {
      const layout=collageLayout(paths.length,false)
      output.width=layout.width;output.height=layout.height;drawSources(output,sources,layout,0)
      resultPath=await exportStill(output);check();onProgress('拼图已完成')
      return {path:resultPath,animated:false,width:layout.width,height:layout.height,duration:0}
    }
    // Retry size/color only. Every attempt retains the same full timeline.
    const attempts=[[240,128],[192,96],[144,64],[112,48],[96,32]]
    for (const [attempt,[edge,colors]] of attempts.entries()) {
      check();const layout=collageLayout(paths.length,true,edge),encoder=GIFEncoder()
      output.width=layout.width;output.height=layout.height
      let oversized=false,previous=null
      for (let frame=0;frame<timeline.length-1;frame++) {
        check();drawSources(output,sources,layout,timeline[frame])
        const rgba=output.getContext('2d').getImageData(0,0,layout.width,layout.height).data
        const palette=quantize(rgba,previous?colors-1:colors),indices=applyPalette(rgba,palette)
        const pixels=new Uint32Array(rgba.buffer,rgba.byteOffset,indices.length)
        if (previous) {
          // Preserve unchanged pixels from the prior displayed frame. This
          // avoids re-encoding static tiles/backgrounds and prevents flicker.
          palette.unshift([0,0,0])
          for (let pixel=0;pixel<indices.length;pixel++) indices[pixel]=pixels[pixel]===previous[pixel]?0:indices[pixel]+1
        }
        encoder.writeFrame(indices,layout.width,layout.height,{palette,delay:timeline[frame+1]-timeline[frame],repeat:0,dispose:1,transparent:!!previous,transparentIndex:0})
        previous=pixels
        onProgress(`${attempt?'正在压缩动态拼图':'正在制作动态拼图'} · ${Math.round(100*(frame+1)/(timeline.length-1))}%`)
        if (encoder.bytesView().length>MAX_COLLAGE_BYTES) {oversized=true;break}
        await pause()
      }
      if (oversized) continue
      encoder.finish();const bytes=encoder.bytesView()
      if (bytes.length>MAX_COLLAGE_BYTES) continue
      check();resultPath=await exportGif(bytes);check();onProgress('动态拼图已完成')
      return {path:resultPath,animated:true,width:layout.width,height:layout.height,duration,bytes:bytes.length}
    }
    throw Error('动态拼图体积仍然较大，请减少所选图片后重试')
  } catch (error) {
    if (resultPath) releaseTemporary(resultPath)
    throw error
  } finally {
    for (const source of sources) {
      source.gif?.close()
      if (source.surface) source.surface.width=source.surface.height=1
      source.image=null;source.imageData=null
    }
    sources.length=0;output.width=output.height=1
  }
}
