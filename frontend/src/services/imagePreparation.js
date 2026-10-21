import {displayImageSize} from '@/services/imageGeometry'

const preparing = new Map()
const prepared = new Map()

export async function prepareImage(originalPath) {
  if(typeof originalPath!=='string' || !originalPath)throw new Error('请重新选择图片')
  if (prepared.has(originalPath)) { const hit=prepared.get(originalPath);prepared.delete(originalPath);prepared.set(originalPath,hit);return hit }
  if (preparing.has(originalPath)) return preparing.get(originalPath)
  const task = (async () => {
    let path = originalPath
    if (uni.getImageInfo && uni.compressImage) {
      const info = await new Promise(resolve => uni.getImageInfo({ src:originalPath, success:resolve, fail:()=>resolve(null) }))
      if (info && /^(jpeg|jpg)$/i.test(info.type || '') && (info.width>1280 || info.height>1280)) {
        const scale = Math.min(1280/info.width,1280/info.height)
        path = await new Promise((resolve,reject) => uni.compressImage({src:originalPath,quality:82,compressedWidth:Math.round(displayImageSize(info).width*scale),compressedHeight:Math.round(displayImageSize(info).height*scale),success:r=>resolve(r.tempFilePath),fail:reject}))
      }
    }
    prepared.set(originalPath,path)
    while(prepared.size>16) { const key=prepared.keys().next().value; const old=prepared.get(key); prepared.delete(key); if(old!==key) uni.getFileSystemManager?.().unlink({filePath:old,fail:()=>{}}) }
    return path
  })().finally(()=>preparing.delete(originalPath))
  preparing.set(originalPath,task)
  return task
}

export async function prepareImages(paths) {
  const result=[]
  for(const path of paths) result.push(await prepareImage(path))
  return result
}
