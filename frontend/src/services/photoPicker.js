import {holdBackgroundWork} from '@/services/backgroundActivity'
// Open the native picker immediately. Model initialization, image decoding and
// compression belong after selection, never on this user-gesture path.
let opening=false
let timing=null
export const photoPickerTiming=()=>timing && {...timing}
export function choosePhotos(options={}) {
  if(opening)return
  opening=true
  const resume=holdBackgroundWork()
  const start=Date.now()
  const modern=typeof wx!=='undefined' && typeof wx.chooseMedia==='function'
  timing={api:modern?'chooseMedia':'chooseImage',invokeMs:null,callbackMs:null}
  const sample=timing
  const done=()=>{resume();opening=false;sample.callbackMs=Date.now()-start}
  const success=result=>{
    done()
    const paths=modern?(result.tempFiles||[]).map(file=>file.tempFilePath):(result.tempFilePaths||[])
    if(paths.length)options.success?.({...result,tempFilePaths:paths})
  }
  const fail=error=>{done();options.fail?.(error)}
  try {
    const settings={count:Math.max(1,Math.min(9,options.count||1)),sizeType:['compressed'],sourceType:['album','camera'],success,fail}
    if(modern)wx.chooseMedia({...settings,mediaType:['image']})
    else uni.chooseImage(settings)
  }catch(error){fail(error)}
  finally{sample.invokeMs=Date.now()-start}
}
