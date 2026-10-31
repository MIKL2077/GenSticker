const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path')
const {GifReader,GifWriter}=require('omggif')
const buffer=new Uint8Array(20000),writer=new GifWriter(buffer,2,1,{palette:[0,0xffffff,0xff0000,0x00ff00],loop:0})
writer.addFrame(0,0,2,1,Uint8Array.of(1,2),{delay:10});writer.addFrame(0,0,2,1,Uint8Array.of(3,1),{delay:20})
const bytes=buffer.slice(0,writer.end()),requests=[],released=[]
let session={access_token:'token',profile:{id:'alice'}},cancelled=false,aborted=0
const context={GifReader,Uint8Array,Uint8ClampedArray,Uint16Array,Uint32Array,Math,Promise,Date,Error,setTimeout,clearTimeout,
 API_BASE_URL:'https://example.test/api',exportGif:async()=>'/server.gif',releaseTemporary:p=>released.push(p),
 uni:{getStorageSync:()=>session,request:o=>{requests.push(o);o.success({statusCode:200,data:bytes.buffer});return {abort(){aborted++}}}}}
vm.createContext(context)
for(const name of ['collageGif.js','recommendService.js'])vm.runInContext(fs.readFileSync(path.join(__dirname,'../src/services',name),'utf8').replace(/^import .*$/gm,'').replace(/export /g,''),context)
;(async()=>{
 const result=await context.createRecommendationCollage('job-id',[3,0],()=>cancelled)
 assert.equal(result.path,'/server.gif');assert.equal(result.animated,true);assert.equal(result.duration,300)
 assert.equal(requests[0].header.Authorization,'Bearer token');assert.equal(requests[0].responseType,'arraybuffer')
 assert.deepEqual(Array.from(requests[0].data.slots),[3,0]);assert.equal(requests[0].timeout,60000)
 context.uni.request=o=>{o.success({statusCode:401,data:new ArrayBuffer(0)});return {}}
 await assert.rejects(context.createRecommendationCollage('job-id',[0]),error=>error.statusCode===401)
 context.uni.request=o=>{o.success({statusCode:200,data:Uint8Array.of(71,73,70).buffer});return {}}
 await assert.rejects(context.createRecommendationCollage('job-id',[0]),/无法读取/)
 context.uni.request=o=>{o.success({statusCode:200,data:bytes.buffer});return {}}
 context.exportGif=async()=>{session={profile:{id:'bob'}};return '/late.gif'}
 await assert.rejects(context.createRecommendationCollage('job-id',[0]),/取消/)
 assert.ok(released.includes('/late.gif'))
 session={access_token:'token',profile:{id:'alice'}};context.uni.request=()=>{cancelled=true;return {abort(){aborted++}}}
 await assert.rejects(context.createRecommendationCollage('job-id',[0],()=>cancelled),/取消/)
 assert.equal(aborted,1)
 console.log('PASS authenticated binary collage, ordered slots, corrupt reply refusal, account isolation, cancellation and late file cleanup')
})().catch(error=>{console.error(error);process.exitCode=1})
