const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm')
const source=fs.readFileSync(path.join(__dirname,'../src/services/subjectSelection.js'),'utf8').replace(/^import .*$/gm,'').replace(/export /g,'')
async function verify(){
 const calls=[],disposed=[],edits=[];const c={API_BASE_URL:'https://example.test',Promise,Error,Math,Number,String,Date,Map,visitorHeaders:()=>({Authorization:'Bearer owner-token','X-Gensticker-Visitor':'fixture-visitor-0001'}),imageEditError:e=>Error(e.errMsg||e.message),setTimeout,clearTimeout,disposeEditedImage:path=>disposed.push(path),editImage:async(path,op)=>{edits.push(op);return path+'-small'},uni:{getStorageSync:()=>({access_token:'owner-token'}),uploadFile:options=>{calls.push(options);options.success({statusCode:200,data:'{"candidates":[{"id":"server","box":[0,0,0.5,0.5]}]}'})}}}
 vm.createContext(c);vm.runInContext(source,c)
 assert.equal(c.paddedFaceBox({x:1,y:2,width:0,height:3},640,480),null)
 const box=c.paddedFaceBox({originX:.9,originY:.9,width:.2,height:.2},640,480);assert.ok(box[0]+box[2]<=1);assert.ok(box[1]+box[3]<=1)
 assert.equal((await c.detectSubjects('/photo')).candidates.length,1);assert.equal(calls[0].header.Authorization,'Bearer owner-token')
 assert.equal(calls[0].filePath,'/photo-small');assert.equal(calls[0].formData.fast,'true');assert.equal(edits[0].maxEdge,640);assert.ok(disposed.includes('/photo-small'))
 await c.detectSubjects('/photo');assert.equal(calls.length,1,'reopening the same photo reuses coordinates without another upload')
 c.wx={createOffscreenCanvas:()=>({width:1,height:1,createImage:()=>({width:640,height:480,set src(_){this.onload()}}),getContext:()=>({drawImage:()=>{},getImageData:()=>({data:new Uint8Array(640*480*4)})})}),initFaceDetect:options=>options.success({}),faceDetect:options=>{assert.equal(options.enableMultiFace,true);options.success({faceInfo:[{detectRect:{originX:80,originY:40,width:80,height:100}}]})},stopFaceDetect:()=>{}}
 const local=await c.detectSubjects('/local-photo');assert.equal(local.method,'device-wechat');assert.equal(local.candidates.length,1);assert.equal(calls.length,1,'successful device detection does not upload or compress the original');assert.equal(edits.length,1)
 c.uni.getDeviceInfo=()=>({platform:'devtools'});await c.detectSubjects('/photo',{force:true,extended:true});assert.equal(calls.length,2,'DevTools skips deprecated face API and uses the server immediately');assert.equal(calls.at(-1).formData.fast,'false','expensive foreground search is explicit')
 c.uni.getStorageSync=()=>null;await c.detectSubjects('/guest-photo');assert.equal(calls.length,3,'visitors can detect subjects without a login');assert.ok(calls.at(-1).header['X-Gensticker-Visitor'])
 let owner='alice';c.uni.getStorageSync=()=>({access_token:owner+'-token',profile:{id:owner}});c.editImage=async path=>{owner='bob';return path+'-small'};await c.detectSubjects('/previous-owner-photo');assert.equal(calls.length,3,'account switching must not upload the previous photo under the new account');assert.ok(disposed.includes('/previous-owner-photo-small'))
 let now=10000,expire,lateInit,stops=0;c.Date={now:()=>now};c.setTimeout=fn=>{expire=fn;return 1};c.clearTimeout=()=>{};c.uni.getDeviceInfo=()=>({platform:'ios'})
 c.wx.initFaceDetect=options=>{lateInit=options.success};c.wx.stopFaceDetect=()=>{stops++}
 const pending=c.nativeDetect('/slow-init',()=>true);await new Promise(resolve=>setImmediate(resolve));assert.equal(typeof lateInit,'function')
 now+=1000;expire();await assert.rejects(pending,/本机检测/);lateInit({});assert.equal(stops,1,'late native initialization releases the face engine after the total deadline')
 console.log('PASS bounded face boxes, manual/server fallback, authenticated transient upload and device detection without photo upload')
}
verify().catch(error=>{console.error(error);process.exitCode=1})
