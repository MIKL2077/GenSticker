const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm')
const source=fs.readFileSync(path.join(__dirname,'../src/services/editSession.js'),'utf8').replace(/^import .*$/gm,'').replace(/export /g,'')
async function verify(){
 let token='alice',request,finishWrite
 const writes=[],released=[],navigations=[]
 const c={console,Date,Math,apiRequest:async url=>{request=url;return{kind:'manual',draft:{template_key:'universal',images:['encoded-image'],texts:['原来的文字'],args:{mode:'normal'}}}},downloadResult:async()=>'/video-source',registerTemporary:p=>p,releaseTemporary:p=>released.push(p),writeOwnedFile:async(...args)=>writes.push(args),uni:{env:{USER_DATA_PATH:'/private'},getStorageSync:()=>({access_token:token}),switchTab:o=>navigations.push(o),navigateTo:o=>navigations.push(o),showToast:()=>{}}}
 vm.createContext(c);vm.runInContext(source,c)
 const draft=await c.loadEditDraft({id:'job'})
 assert.equal(request,'/studio/jobs/job/edit');assert.equal(writes[0][1],'encoded-image');assert.equal(draft.texts[0],'原来的文字');assert.equal(draft.args.mode,'normal')
 c.openEditDraft(draft);assert.equal(navigations[0].url,'/pages/index/index');assert.equal(c.takeEditDraft('livegif'),null);assert.equal(c.takeEditDraft('manual').paths[0],writes[0][0]);assert.equal(c.takeEditDraft('manual'),null)
 c.openEditDraft(draft);token='bob';assert.equal(c.takeEditDraft('manual'),null);assert.ok(released.includes(draft.paths[0]))
 token='alice';await c.loadRecommendationEdit('batch-older',7);assert.equal(request,'/recommend/jobs/batch-older/results/7/edit','editing follows the result job and slot, not the currently selected upload')
 token='alice';const local=await c.loadEditDraft({kind:'manual',editDraft:{paths:['/saved-input'],texts:['本机旧文字']}});assert.equal(local.paths[0],'/saved-input');assert.equal(local.texts[0],'本机旧文字')
 c.writeOwnedFile=()=>new Promise(resolve=>finishWrite=resolve)
 const stale=c.loadEditDraft({id:'stale'});await new Promise(resolve=>setImmediate(resolve));token='bob';finishWrite();await assert.rejects(stale,/账号已切换/)
 token='alice';c.apiRequest=async()=>({kind:'livegif',draft:{source_url:'/owned-video',source:{width:320,height:240,duration:8},start:2,duration:3,crop:[.1,.2,.5,.5],rotation:90,text:'原字幕',caption_style:{size:.15}}})
 const video=await c.loadEditDraft({id:'video'});c.openEditDraft(video);assert.equal(navigations.at(-1).url,'/pages/live/index?edit=1');assert.equal(video.mediaPath,'/video-source');assert.equal(video.rotation,90);assert.equal(video.text,'原字幕');assert.equal(video.caption_style.size,.15)
 navigations.at(-1).fail();assert.equal(c.takeEditDraft('livegif'),null);assert.ok(released.includes('/video-source'))
 c.getCurrentPages=()=>[{route:'pages/live/index'},{route:'pages/queue/index'}];c.uni.navigateBack=options=>navigations.push(options)
 c.openEditDraft({kind:'livegif',mediaPath:'/existing-video'});assert.equal(navigations.at(-1).delta,1,'return to an existing video editor');assert.equal(c.takeEditDraft('livegif').mediaPath,'/existing-video')
 const preview=fs.readFileSync(path.join(__dirname,'../src/components/PreviewModal.vue'),'utf8')
 assert.match(preview,/重新编辑/);assert.doesNotMatch(preview,/配好文案，发朋友圈|再生成一张|shareToMoments|regeneratable/)
 console.log('PASS owned draft restoration, text/args/video settings, local inputs, one-shot navigation, account isolation and cleanup')
}
verify().catch(error=>{console.error(error);process.exitCode=1})
