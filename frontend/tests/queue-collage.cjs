const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path')
const {ref,computed,watch,nextTick}=require('vue')
const flush=()=>new Promise(resolve=>setImmediate(resolve))
function queue(extra={}){
 const session=ref({profile:{id:'alice'}}),lifecycle={}
 const source=fs.readFileSync(path.join(__dirname,'../src/pages/queue/index.vue'),'utf8').split('<script setup>')[1].split('</script>')[0].replace(/^import .*$/gm,'')
 const c={ref,computed,watch,console,Date,Map,Promise,setTimeout,clearTimeout,setInterval:()=>0,clearInterval:()=>{},onShow:fn=>lifecycle.show=fn,onHide:fn=>lifecycle.hide=fn,onUnload:()=>{},onReachBottom:()=>{},onShareAppMessage:()=>{},shareCard:()=>({}),useLibrary:()=>({session,loggingIn:ref(false)}),unreadCount:ref(0),refreshUnread:()=>{},guestResults:()=>[],cachedQueueThumbnail:()=>'',cachedStudioJobs:()=>[],warmQueueThumbnails:async()=>{},listStudioJobs:async()=>[],takeCompletedResult:()=>null,privateImage:async url=>'/original'+url,viewStudioJob:async()=>{},disposeEditedImage:()=>{},createResultCollage:async()=>({path:'/collage.gif',animated:true}),createStudioCollage:async()=>{},shareOriginalImage:()=>{},...extra,uni:{$on:()=>{},$off:()=>{},showToast:()=>{},showLoading:()=>{},hideLoading:()=>{},saveImageToPhotosAlbum:async()=>{},...extra.uni}}
 vm.createContext(c);vm.runInContext(source+'\nthis.app={jobs,images,fullImages,selected,selecting,selectableJobs,allSelected,showJobs,toggleSelection,openItem,selectAll,openCollage,closeCollage,makeCollage,collageOpen,collageJobs,collageItems,collage,showCollage,collageError,preparingCollage,collageProgress,changeCollageImage,shareCollage,saveCollage,ensureOriginal,opened,touchStart,touchMove}',c)
 return {app:c.app,session,lifecycle}
}
const rows=Array.from({length:12},(_,i)=>({id:i.toString(16).padStart(32,'0'),kind:i%2?'livegif':'manual',status:'completed',created_at:100-i,result_url:'/image/'+i}))
;(async()=>{
 const disposed=[],shared=[],saved=[],calls=[],toasts=[];let downloads=0
 const {app:q,session,lifecycle}=queue({disposeEditedImage:p=>disposed.push(p),privateImage:async url=>{downloads++;return '/original'+url},shareOriginalImage:p=>shared.push(p),createResultCollage:async(paths,options)=>{calls.push({paths:Array.from(paths),options});return {path:'/collage.gif',animated:true}},uni:{showToast:o=>toasts.push(o.title),saveImageToPhotosAlbum:async({filePath})=>saved.push(filePath)}})
 q.showJobs([...rows,{id:'running',kind:'manual',status:'running',created_at:0},{id:'failed',kind:'manual',status:'failed',created_at:0}])
 q.toggleSelection();await q.openItem(q.jobs.value.find(x=>x.id==='running'));assert.equal(q.selected.value.length,0)
 for(const item of rows.slice(0,10))await q.openItem(item)
 assert.equal(q.selected.value.length,9);assert.match(toasts.at(-1),/最多/)
 q.touchStart({clientX:100,clientY:0},rows[0]);q.touchMove({clientX:0,clientY:0,buttons:1},rows[0]);assert.equal(q.opened.value,'','selection disables swipe deletion')
 q.selectAll();assert.equal(q.selected.value.length,0);q.selectAll();assert.equal(q.selected.value.length,9)
 q.toggleSelection();q.toggleSelection();await q.openItem(rows[2]);await q.openItem(rows[1]);assert.equal(downloads,0,'selection never downloads full originals')
 await q.openCollage();assert.deepEqual(calls[0].paths,['/original/image/2','/original/image/1']);assert.equal(q.showCollage.value,true);assert.equal(shared.length,0,'preview before share')
 assert.equal(q.collageItems.value[1].animated,true);q.shareCollage();await q.saveCollage();assert.deepEqual(shared,['/collage.gif']);assert.deepEqual(saved,['/collage.gif']);assert.equal(typeof calls[0].options.remote,'function','cross-job owned originals use server compositor')
 q.showCollage.value=false;await q.makeCollage();assert.equal(calls.length,1,'return to preview reuses collage')
 q.closeCollage();assert.deepEqual(disposed,['/collage.gif'])
 q.showJobs(rows.slice(3));assert.equal(q.selected.value.length,0,'expired/deleted entries leave selection on refresh')
 await q.openItem(rows[3]);await q.openItem(rows[4]);await q.openCollage();session.value={profile:{id:'bob'}};await nextTick();assert.equal(q.selecting.value,false);assert.equal(q.collageOpen.value,false);assert.equal(q.jobs.value.length,0,'account switch clears private previews and selections')
 let finish,options
 const late=queue({disposeEditedImage:p=>disposed.push(p),createResultCollage:async(paths,o)=>{options=o;return new Promise(resolve=>finish=resolve)}}).app
 late.showJobs(rows);late.toggleSelection();await late.openItem(rows[0]);await late.openItem(rows[1]);const pending=late.openCollage();await flush();late.closeCollage();assert.equal(options.cancelled(),true);options.onProgress('stale');finish({path:'/late.gif',animated:true});await pending;assert.equal(late.collage.value,null);assert.equal(late.collageProgress.value,'');assert.ok(disposed.includes('/late.gif'))
 let finishSave
 const album=queue({disposeEditedImage:p=>disposed.push(p),uni:{saveImageToPhotosAlbum:()=>new Promise(resolve=>finishSave=resolve)}}).app
 album.collage.value={path:'/saving.gif',animated:true};album.showCollage.value=true;const saving=album.saveCollage();album.closeCollage();assert.ok(!disposed.includes('/saving.gif'));finishSave();await saving;assert.ok(disposed.includes('/saving.gif'))
 const local=queue({guestResults:()=>[{id:'local',localPath:'/local.gif',kind:'livegif',status:'completed',created_at:200}]}).app
 local.showJobs(rows);local.toggleSelection();await local.openItem(local.jobs.value[0]);await local.openItem(rows[0]);let usedRemote='unset'
 const mixed=queue({createResultCollage:async(paths,o)=>{usedRemote=o.remote;return {path:'/mixed.gif',animated:true}},guestResults:()=>[{id:'local',localPath:'/local.gif',kind:'livegif',status:'completed',created_at:200}]}).app
 mixed.showJobs(rows);mixed.toggleSelection();await mixed.openItem(mixed.jobs.value[0]);await mixed.openItem(rows[0]);await mixed.openCollage();assert.equal(usedRemote,undefined,'unsynced local results remain local')
 let finishImage
 const stale=queue({privateImage:()=>new Promise(resolve=>finishImage=resolve),disposeEditedImage:p=>disposed.push(p)})
 const loading=stale.app.ensureOriginal(rows[0]);stale.lifecycle.hide();finishImage('/late-original.gif');await assert.rejects(loading,/切换/);assert.ok(disposed.includes('/late-original.gif'))
 console.log('PASS queue selection order/limit, inactive jobs, thumbnail-only selection, server/local choice, preview/share/save, reuse, refresh pruning, cancellation, account isolation and in-flight file cleanup')
})().catch(e=>{console.error(e);process.exitCode=1})
