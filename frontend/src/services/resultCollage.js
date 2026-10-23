import {registerTemporary,withStorageRecovery} from '@/services/ownedFiles'

// Draw one image at a time, cap the output to ~1 MP, and release its canvas.
// Animated originals remain untouched; a collage deliberately uses still frames.
export async function createResultCollage(paths) {
  if(!paths.length || paths.length>9)throw Error('请选择 1 至 9 张表情')
  const columns=paths.length===1?1:paths.length<=4?2:3,edge=320,gap=16
  const width=columns*edge+(columns+1)*gap,height=Math.ceil(paths.length/columns)*edge+(Math.ceil(paths.length/columns)+1)*gap
  const browser=typeof document!=='undefined'
  const canvas=browser?document.createElement('canvas'):wx.createOffscreenCanvas?.({type:'2d',width,height})
  if(!canvas)throw Error('当前微信暂不支持拼图，请逐张分享或保存到相册')
  canvas.width=width;canvas.height=height
  try{
    const ctx=canvas.getContext('2d');ctx.fillStyle='#fffaf4';ctx.fillRect(0,0,width,height)
    for(const [index,path] of paths.entries()){
      const image=browser?new Image():canvas.createImage()
      await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('拼图读取图片超时，请重试')),10000);image.onload=()=>{clearTimeout(timer);resolve()};image.onerror=()=>{clearTimeout(timer);reject(Error('拼图读取图片失败，请重试'))};image.src=path})
      const scale=Math.min(edge/image.width,edge/image.height),w=image.width*scale,h=image.height*scale
      ctx.drawImage(image,gap+(index%columns)*(edge+gap)+(edge-w)/2,gap+Math.floor(index/columns)*(edge+gap)+(edge-h)/2,w,h)
    }
    if(browser){
      const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/jpeg',.9))
      if(!blob)throw Error('拼图导出失败，请重试')
      return registerTemporary(URL.createObjectURL(blob))
    }
    const result=await withStorageRecovery(()=>new Promise((resolve,reject)=>wx.canvasToTempFilePath({canvas,fileType:'jpg',quality:.9,success:resolve,fail:reject})))
    return registerTemporary(result.tempFilePath)
  }finally{canvas.width=canvas.height=1}
}
