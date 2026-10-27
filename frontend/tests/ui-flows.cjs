const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const { ref, computed } = require('vue')
const flush = () => new Promise(resolve => setImmediate(resolve))
const clone = value => JSON.parse(JSON.stringify(value))
function page(file, extra) {
  let code = fs.readFileSync(path.join(__dirname, '../src/pages', file), 'utf8').split('<script>')[1].split('</script>')[0]
  code = code.replace(/^import .*$/gm, '').replace('export default', 'const component =')
  const c = { onShareAppMessage:()=>{},shareCard:()=>({}), GenerationNotice:{}, notifyGeneration:()=>{}, takeCompletedResult:()=>null, FirstUseGuide:{}, SelectedResultsModal:{}, choosePhotos:o=>c.uni.chooseImage(o), createResultCollage:async()=>'/collage.jpg',disposeEditedImage:()=>{},loadRecommendationEdit:async()=>{},openEditDraft:()=>{},disposeEditDraft:()=>{}, BottomTabs:{}, DataControls:{}, AccountActionCard:{}, MoodToy:{}, UiIcon:{}, PreviewModal:{}, SubjectPicker:{}, ref, computed, watch:()=>{}, nextTick:()=>{}, unreadCount:ref(0),refreshUnread:async()=>{},getCurrentInstance:()=>({proxy:{}}), onUnmounted:()=>{}, onShow:()=>{}, onHide:()=>{}, onUnload:()=>{}, console, setTimeout, clearTimeout, ...extra, uni:{$on:()=>{},$off:()=>{},...extra.uni} }
  vm.createContext(c); vm.runInContext(code + '\nthis.app = component.setup()', c)
  return c.app
}
async function verify() {
  let logins = 0, saves = 0, exits = 0
  const session = ref(null)
  const account = {session,loggingIn:ref(false),library:ref({}),syncLibrary:()=>{},prefetchLogin:async()=>{},loginWeChat:async()=>{logins++;session.value={profile:{id:'a',name:'微信用户'}}},saveProfile:async(name)=>{saves++;session.value.profile.name=name},logout:()=>{exits++;session.value=null}}
  const app = page('my/index.vue', {useLibrary:()=>account,openRecommend:()=>{},uni:{showToast:()=>{},removeStorageSync:()=>{}}})
  await app.login()
  assert.equal(logins,1);assert.equal(saves,0,'login must not require a second profile request')
  assert.equal(session.value.profile.name,'微信用户')
  app.showProfile();assert.equal(app.nickname.value,'微信用户')
  app.nickname.value='新的小表情';await app.saveProfile();assert.equal(saves,1)
  app.signOut();assert.equal(exits,1);assert.equal(session.value,null)

  const storage = new Map(), requests = []
  const source = fs.readFileSync(path.join(__dirname,'../src/composables/useLibrary.js'),'utf8').replace(/^import .*$/gm,'').replace('export function useLibrary','function useLibrary').replace(/\/\/ #ifndef MP-WEIXIN[\s\S]*?\/\/ #endif/g,'')
  let oldResolve, delay = false
  const c={ref,computed,console,uni:{getStorageSync:k=>storage.get(k),setStorageSync:(k,v)=>storage.set(k,clone(v)),removeStorageSync:k=>storage.delete(k),login:o=>o.success({code:'code'})},apiRequest:async(url,options={})=>{requests.push({url,options});if(url==='/account/config')return{login_enabled:true};if(url==='/auth/wechat')return{access_token:'token-a',profile:{id:'a',name:'微信用户'}};if(url==='/account/library' && delay)return new Promise(resolve=>oldResolve=resolve);if(url==='/account/library')return{favorite_keys:['current'],history:[]};if(url==='/auth/session')throw Object.assign(Error('offline'),{statusCode:503})}}
  vm.createContext(c);vm.runInContext(source,c)
  const library=c.useLibrary();await library.loginWeChat();await library.syncLibrary()
  delay=true;const pending=library.syncLibrary(true);await flush()
  library.logout();assert.equal(library.session.value,null,'logout clears state before remote requests finish')
  delay=false;await library.loginWeChat();await library.syncLibrary()
  oldResolve({favorite_keys:['stale-private-data'],history:[]});await pending
  assert.deepEqual(clone(library.library.value.favorite_keys),['current'],'a response from a previous session must never overwrite a re-login')
  assert.equal(library.syncError.value,'')
  assert.ok(requests.some(r=>r.url==='/auth/session' && r.options.header.Authorization==='Bearer token-a'))

  let failSlot = 1, writes = [], downloads = [], collageInputs,shared=[],editRequests=[],openedDraft
  const rec = page('recommend/index.vue',{createResultCollage:async paths=>{collageInputs=Array.from(paths);return'/collage.jpg'},shareOriginalImage:path=>shared.push(path),loadRecommendationEdit:async(id,slot)=>{editRequests.push({id,slot});return{kind:'manual',template_key:'actual-result-template',paths:['/worker-subject.png'],temporaryPaths:[]}},openEditDraft:draft=>openedDraft=draft,useLibrary:()=>({session:ref({profile:{id:'a'}}),loggingIn:ref(false)}),getQuota:async()=>({limit:3,remaining:2,personalization:true}),listJobs:async()=>[],getJob:async()=>{},createJob:async()=>{},uploadPhoto:async()=>{},removeJob:async()=>{},setPersonalization:async()=>{},selectResults:async()=>{throw Error('telemetry unavailable')},downloadResult:async url=>{const slot=Number(url.split('/').pop());downloads.push(slot);if(slot===failSlot){failSlot=-1;throw Error('network failed')}return'/result-'+slot},uni:{getStorageSync:()=>null,setStorageSync:()=>{},removeStorageSync:()=>{},showToast:()=>{},saveImageToPhotosAlbum:async({filePath})=>writes.push(filePath),chooseImage:options=>options.success({tempFilePaths:['/group-original.jpg']})}})
  rec.activeId.value='job';rec.job.value={status:'completed',results:[{slot:0},{slot:1},{slot:2}]};rec.selected.value=[0,1,2]
  await rec.save();assert.deepEqual(writes,['/result-0']);assert.match(rec.error.value,/剩余/)
  await rec.save();assert.deepEqual(writes,['/result-0','/result-1','/result-2']);assert.deepEqual(downloads,[0,1,1,2]);assert.equal(rec.saving.value,false)
  rec.choose();assert.equal(rec.subjectPicker.value,true);assert.equal(rec.photo.value,'','photo is not submitted before explicit subject confirmation');rec.confirmSubject({path:'/selected-head.jpg',rect:[0.2,0.1,0.3,0.4]});assert.equal(rec.photo.value,'/selected-head.jpg');assert.equal(rec.subjectPicker.value,false)
  rec.previews.value[0]='/small-preview.gif';rec.selected.value=[0,2];await rec.shareSelected();assert.equal(rec.shareItems.value.length,2,'all selected images stay in the share preview');assert.equal(rec.shareImage.value,'/result-0','sharing uses the full animated result instead of a thumbnail');await rec.changeShare(1);assert.equal(rec.shareImage.value,'/result-2','switching uses the next selected original');rec.closeShare();assert.equal(rec.shareSlot.value,null)
  rec.selected.value=[2,0];await rec.shareSelected();await rec.shareCollage();assert.deepEqual(collageInputs,['/result-2','/result-0']);assert.equal(shared.at(-1),'/collage.jpg');rec.photoOriginal.value='/unrelated-new-photo.jpg';await rec.editShared();assert.deepEqual(editRequests,[{id:'job',slot:2}]);assert.equal(openedDraft.template_key,'actual-result-template');assert.equal(openedDraft.paths[0],'/worker-subject.png');assert.equal(rec.shareSlot.value,null)
  const batches=[], activeSession=ref({profile:{id:'a'}})
  let rejectNext=true,uploads=0
  const variations=page('recommend/index.vue',{useLibrary:()=>({session:activeSession,loggingIn:ref(false)}),getQuota:async()=>({limit:0,remaining:null,unlimited:true,personalization:true,features:{reroll:true}}),listJobs:async()=>[],getJob:async()=>({status:'completed',results:[],selected_slots:[]}),createJob:async(asset,key,parent)=>{batches.push({asset,key,parent});if(rejectNext){rejectNext=false;throw Error('temporary network failure')}return{job_id:'next-batch',status:'queued'}},uploadPhoto:async()=>{uploads++;return{asset_id:'photo'}},removeJob:async()=>{},setPersonalization:async()=>{},selectResults:async()=>{},downloadResult:async()=>'',uni:{getStorageSync:()=>null,setStorageSync:()=>{},removeStorageSync:()=>{},showToast:()=>{}}})
  await variations.refresh()
  assert.equal(variations.quotaAvailable.value,true,'null remaining must allow unlimited generation')
  variations.activeId.value='previous';variations.job.value={status:'completed',results:[{slot:0}]};variations.selected.value=[0]
  await variations.reroll()
  assert.equal(variations.activeId.value,'previous','failed submission keeps the previous batch visible')
  assert.deepEqual(clone(variations.selected.value),[0])
  await variations.reroll();await flush()
  assert.equal(batches[0].key,batches[1].key,'retry must reuse the idempotency key')
  assert.equal(batches[1].parent,'previous');assert.equal(batches[1].asset,undefined)
  assert.equal(uploads,0,'reroll must work from restored history without uploading again')
  variations.activeId.value='next-batch';variations.job.value={status:'running',results:[]}
  await variations.reroll();assert.equal(batches.length,2,'cannot reroll an active task')
  variations.quota.value={limit:3,remaining:0};assert.equal(variations.quotaAvailable.value,false,'explicit operator limits remain compatible')
  variations.quota.value={limit:0,remaining:null,unlimited:true};variations.job.value={status:'completed',results:[],reroll_available:false}
  await variations.reroll();assert.equal(batches.length,2,'expired source photos must not submit reroll jobs')
  variations.quota.value={limit:0,remaining:null,unlimited:true};variations.job.value={status:'completed',results:[{slot:0}]}
  assert.equal(variations.rerollSupported.value,false,'legacy server must not advertise unsupported reroll')
  await variations.reroll();assert.equal(batches.length,2,'legacy backend must not receive unsupported requests')
  const historyRows=Array.from({length:12},(_,i)=>({job_id:'history-'+i,source_preview_url:'/source-preview/'+i,count:9,status:'completed'}))
  const loaded=[]
  const historyApp=page('recommend/index.vue',{useLibrary:()=>({session:ref({profile:{id:'a'}}),loggingIn:ref(false)}),getQuota:async()=>({limit:0,remaining:null,unlimited:true}),listJobs:async()=>historyRows,downloadResult:async url=>{loaded.push(url);return'/local'+url},uni:{getStorageSync:()=>null}})
  await historyApp.refresh();await flush()
  assert.equal(historyApp.visibleHistory.value.length,5);assert.equal(historyApp.historyPages.value,3)
  assert.equal(loaded.length,5,'only five source thumbnails are fetched for the first page')
  historyApp.changeHistoryPage(1);await flush();assert.equal(historyApp.visibleHistory.value[0].job_id,'history-5');assert.equal(loaded.length,10)
  historyApp.changeHistoryPage(1);await flush();assert.equal(historyApp.visibleHistory.value.length,2);assert.equal(loaded.length,12)
  historyApp.changeHistoryPage(-1);await flush();assert.equal(loaded.length,12,'returning to a page reuses the source thumbnails')
  console.log('PASS one-click default login, optional profile editing, immediate offline logout, stale-session isolation, batch save continuation, unlimited generation, stable reroll retry and no duplicate upload')
}
verify().catch(e=>{console.error(e);process.exitCode=1})
