const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path')
const source=fs.readFileSync(path.join(__dirname,'../src/composables/useMemeGeneration.js'),'utf8').replace(/^import .*$/gm,'').replace(/export /g,'')
async function verify(){
 const statuses=[],submitted=[],downloads=[],saved=[];let resolveJob
 const c={ref:value=>({value}),console,setTimeout:fn=>{fn()},supportsStudio:async()=>true,viewStudioJob:async()=>{},rememberGuestMeme:p=>saved.push(p),submitManual:async(...args)=>{submitted.push(args);return{id:'owned-job',status:'queued'}},getStudioJob:()=>new Promise(resolve=>resolveJob=resolve),privateImage:async url=>{downloads.push(url);return'/private-result'},uni:{getStorageSync:()=>({access_token:'token',profile:{id:'alice'}})}}
 vm.createContext(c);vm.runInContext(source,c)
 const app=c.useMemeGeneration(s=>statuses.push(s)),run=app.generateFromTemplate('always',['/photo'],[],{},{})
 await new Promise(resolve=>setImmediate(resolve));assert.equal(submitted.length,1);app.closePreview();assert.equal(app.showPreview.value,false)
 resolveJob({id:'owned-job',status:'running'});assert.equal(await run,true);assert.equal(app.isGenerating.value,false);assert.equal(downloads.length,0);assert.equal(saved.length,0,'authenticated jobs are not mixed into guest history')
 c.getStudioJob=async()=>({id:'owned-job',status:'completed',result_url:'/studio/jobs/owned-job/image'})
 const complete=await app.generateFromTemplate('always',['/photo'],[],{},{})
 assert.equal(complete,true);assert.equal(app.generatedMeme.value,'/private-result');assert.equal(downloads[0],'/studio/jobs/owned-job/image')
 console.log('PASS durable manual jobs keep running when sheet closes, completed results download through auth and guest records stay separate')
}
verify().catch(e=>{console.error(e);process.exitCode=1})
