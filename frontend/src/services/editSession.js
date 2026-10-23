// Transfer one owned edit draft between pages, without putting photos in route
// parameters or shared storage. A token change invalidates an in-flight read.
import {apiRequest} from '@/services/apiService'
import {downloadResult} from '@/services/recommendService'
import {writeOwnedFile,registerTemporary,releaseTemporary} from '@/services/ownedFiles'

let pending=null
const identity=()=>uni.getStorageSync('gensticker.session.v1')?.access_token || 'guest'
export function disposeEditDraft(draft){for(const path of draft?.temporaryPaths||[])releaseTemporary(path)}
export function openEditDraft(draft) {
  disposeEditDraft(pending?.draft)
  const transfer={owner:identity(),draft}
  pending=transfer
  const fail=()=>{if(pending!==transfer)return;disposeEditDraft(draft);pending=null;uni.showToast({title:'编辑页暂时无法打开，请重试',icon:'none'})}
  const url=draft.kind==='livegif'?'/pages/live/index?edit=1':'/pages/index/index'
  if(draft.kind==='livegif'){
    const pages=typeof getCurrentPages==='function'?getCurrentPages():[]
    const previous=pages.map(page=>page.route).lastIndexOf('pages/live/index')
    if(previous>=0 && previous<pages.length-1){uni.navigateBack({delta:pages.length-1-previous,fail});return}
  }
  const navigation=draft.kind==='livegif'?uni.navigateTo:uni.switchTab
  navigation({url,fail})
}
export function takeEditDraft(kind) {
  if(!pending)return null
  if(pending.owner!==identity()){disposeEditDraft(pending.draft);pending=null;return null}
  if(pending.draft.kind!==kind)return null
  const draft=pending.draft;pending=null;return draft
}
export async function loadEditDraft(item) {
  const owner=identity()
  const value=item.editDraft?{kind:item.kind,draft:item.editDraft}:await apiRequest(`/studio/jobs/${item.serverId||item.id}/edit`,{timeout:60000},1)
  return materializeDraft(value,owner)
}
export async function loadRecommendationEdit(id,slot){
  const owner=identity()
  const value=await apiRequest(`/recommend/jobs/${id}/results/${slot}/edit`,{timeout:30000},1)
  return materializeDraft(value,owner)
}
async function materializeDraft(value,owner){
  if(owner!==identity())throw Error('账号已切换，请重新打开作品')
  const draft={...value.draft,kind:value.kind,temporaryPaths:[]}
  try {
    if(draft.kind==='manual' && !draft.paths){
      draft.paths=[]
      for(const [index,image] of (draft.images||[]).entries()) {
        if(typeof document!=='undefined')draft.paths.push('data:image/png;base64,'+image)
        else {
          const path=`${uni.env.USER_DATA_PATH}/gensticker_edit_${Date.now()}_${index}_${Math.random().toString(36).slice(2)}.png`
          await writeOwnedFile(path,image,'base64');draft.paths.push(registerTemporary(path));draft.temporaryPaths.push(path)
        }
      }
      delete draft.images
    }
    if(draft.kind==='livegif' && !draft.mediaPath){draft.mediaPath=registerTemporary(await downloadResult(draft.source_url,120000));draft.temporaryPaths.push(draft.mediaPath)}
    if(owner!==identity())throw Error('账号已切换，请重新打开作品')
    return draft
  } catch(error){disposeEditDraft(draft);throw error}
}
