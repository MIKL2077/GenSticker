import {ref} from 'vue'
export const generationNotice=ref(null)
export const generationNoticeVisible=ref(false)
let fadeTimer=null,clearTimer=null,pending=null,sequence=0
const seen=new Map()
const identity=()=>{const session=uni.getStorageSync('gensticker.session.v1');return JSON.stringify([session?.profile?.id||'guest',session?.access_token||''])}
export const noticeIdentity=identity
export function dismissGenerationNotice(){clearTimeout(fadeTimer);clearTimeout(clearTimer);generationNotice.value=null;generationNoticeVisible.value=false}
export function noticeBelongsToAccount(){return !generationNotice.value || generationNotice.value.owner===identity()}
export function notifyGeneration({item,image='',recommendId='',message='表情生成成功！',owner:expectedOwner}){
 const owner=identity();if(expectedOwner && expectedOwner!==owner)return
 const key=owner+':'+(recommendId||item?.id||image)
 if(seen.has(key)&&Date.now()-seen.get(key)<60000)return
 seen.set(key,Date.now());while(seen.size>50)seen.delete(seen.keys().next().value)
 dismissGenerationNotice()
 const notice={sequence:++sequence,owner,item,image,recommendId,message}
 generationNotice.value=notice;generationNoticeVisible.value=true
 fadeTimer=setTimeout(()=>{if(generationNotice.value?.sequence===notice.sequence)generationNoticeVisible.value=false},4200)
 clearTimer=setTimeout(()=>{if(generationNotice.value?.sequence===notice.sequence)dismissGenerationNotice()},5000)
}
export function openGenerationNotice(){
 const notice=generationNotice.value
 if(!notice||notice.owner!==identity()){dismissGenerationNotice();return}
 pending=notice;dismissGenerationNotice()
 const fail=()=>{if(pending===notice)pending=null}
 const target=notice.recommendId?'pages/recommend/index':'pages/queue/index'
 const pages=typeof getCurrentPages==='function'?getCurrentPages():[]
 const existing=pages.map(page=>page.route).lastIndexOf(target)
 if(existing===pages.length-1&&existing>=0){uni.$emit('gensticker:open-result');return}
 if(existing>=0){uni.navigateBack({delta:pages.length-1-existing,fail});return}
 uni.navigateTo({url:'/'+target,fail})
}
export function takeCompletedResult(type){
 if(!pending)return null
 if(pending.owner!==identity()){pending=null;return null}
 if((type==='recommend')!==!!pending.recommendId)return null
 const result=pending;pending=null;return result
}
