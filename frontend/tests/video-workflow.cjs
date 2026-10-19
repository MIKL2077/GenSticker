const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm')
const source=fs.readFileSync(path.join(__dirname,'../src/services/videoWorkflow.js'),'utf8').replace(/^import .*$/gm,'').replace(/export /g,'')
async function verify(){
 let picked,editOptions,owner='alice',tracked,resolveJob,uploadOptions,progress
 const c={Promise,Error,Object,JSON,API_BASE_URL:'https://example.test/api',uniqueKey:()=> 'fixture-key',albumMotion:async()=>{throw Error('静态照片没有动态分量')},localVideoInfo:async()=>({width:1080,height:1920,duration:8.2}),trackStudioJob:(job,id)=>{tracked={job,id};return job},apiRequest:()=>new Promise(resolve=>resolveJob=resolve),uni:{getStorageSync:()=>({profile:{id:owner}}),uploadFile:options=>{uploadOptions=options;options.success({statusCode:201,data:'{"asset_id":"asset"}'});return {onProgressUpdate:fn=>fn({progress:75}),abort:()=>{}}}},wx:{chooseMedia:options=>{picked=options;options.success({tempFiles:[{tempFilePath:'/original.mov',duration:25,width:1080,height:1920,fileType:'video'}]})},openVideoEditor:options=>{editOptions=options;options.success({tempFilePath:'/trimmed.mp4',tempThumbPath:'/poster.jpg',duration:8200,size:12000})}}}
 vm.createContext(c);vm.runInContext(source,c)
 const original=await c.chooseAlbumVideo();assert.equal(picked.sourceType[0],'album')
 const trimmed=await c.nativeTrim(original);assert.equal(trimmed.trimmed,true);assert.equal(trimmed.file.duration,8.2);assert.equal(trimmed.file.tempFilePath,'/trimmed.mp4');assert.equal(editOptions.filePath,'/original.mov');assert.equal(editOptions.maxDuration,'9')
 c.wx.openVideoEditor=options=>options.fail({errMsg:'not supported'});assert.equal((await c.nativeTrim(original)).trimmed,false)
 c.wx.openVideoEditor=options=>options.fail({errMsg:'cancel'});await assert.rejects(c.nativeTrim(original),/./)
 c.wx.chooseMedia=options=>options.success({tempFiles:[{tempFilePath:'/static.jpg',fileType:'image'}]});await assert.rejects(c.chooseAlbumVideo(true),/动态分量/)
 const ingress=c.uploadLiveSource('/trimmed.mp4','owner-token',v=>progress=v);assert.equal((await ingress.promise).asset_id,'asset');assert.equal(uploadOptions.header.Authorization,'Bearer owner-token');assert.equal(progress,75)
 const pending=c.submitVideoJob({asset_id:'asset'},{start:0,duration:8.2},'stable-key','owner-token');owner='bob';resolveJob({id:'job',kind:'livegif',status:'queued'});await pending;assert.equal(tracked.id,'alice','late submissions retain the submitting account identity')
 const page=fs.readFileSync(path.join(__dirname,'../src/pages/live/index.vue'),'utf8');assert.ok(!page.includes('renderLocalGif('));assert.ok(page.includes("uni.navigateTo({url:'/pages/queue/index'})"));assert.ok(!page.includes('使用兼容模式'))
 console.log('PASS native timeline trimming, millisecond duration, cancellation, honest Live detection, upload progress, durable queue and stale-account isolation')
}
verify().catch(e=>{console.error(e);process.exitCode=1})
