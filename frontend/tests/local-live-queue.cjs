const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm')
const source=fs.readFileSync(path.join(__dirname,'../src/services/studioService.js'),'utf8').replace(/^import .*$/gm,'').replace(/export /g,'')
async function verify(){
 let owner='alice',fail=true,options,finish;const storage=new Map(),events=[]
 const c={ref:value=>({value}),Date,Math,Promise,Set,Error,JSON,setInterval:()=>0,clearInterval:()=>{},API_BASE_URL:'https://example.test',downloadResult:()=>{},apiRequest:async()=>({count:0}),uni:{getStorageSync:key=>key==='gensticker.session.v1'?{access_token:owner+'-token',profile:{id:owner}}:storage.get(key),setStorageSync:(key,value)=>storage.set(key,value),$emit:(...args)=>events.push(args),uploadFile:args=>{options=args;if(fail)args.fail({errMsg:'uploadFile:fail timeout'});else finish=()=>args.success({statusCode:201,data:'{"id":"cloud-job"}'});return{}}}}
 Object.assign(c,require('./helpers/owned-files.cjs')(c));vm.createContext(c);vm.runInContext(source,c)
 const job=c.beginLocalLive();c.updateLocalResult(job.id,{status:'completed',localPath:'/owned/local.gif'})
 await c.syncLocalLiveResults();let saved=c.guestResults()[0];assert.equal(saved.status,'completed');assert.equal(saved.localPath,'/owned/local.gif');assert.match(saved.message,/本地已完成/);assert.equal(options.formData.idempotency_key,job.id)
 c.updateLocalResult(job.id,{syncAttempt:0});fail=false;const syncing=c.syncLocalLiveResults();assert.equal(options.header.Authorization,'Bearer alice-token');owner='bob';finish();await syncing;assert.equal(c.guestResults().length,0)
 owner='alice';assert.equal(c.guestResults()[0].serverId,undefined,'late upload cannot link a result into another account');c.updateLocalResult(job.id,{syncAttempt:0});const retry=c.syncLocalLiveResults();finish();await retry;assert.equal(c.guestResults()[0].serverId,'cloud-job');assert.equal(options.formData.idempotency_key,job.id)
 c.removeGuestMeme('cloud-job');assert.equal(c.guestResults().length,0)
 const interrupted=c.beginLocalLive();c.updateLocalResult(interrupted.id,{created_at:Date.now()/1000-121});assert.equal(c.guestResults()[0].status,'failed')
 console.log('PASS local GIF remains usable after sync timeout, idempotent retry, account switch isolation, linked deletion and interrupted job recovery')
}
verify().catch(error=>{console.error(error);process.exitCode=1})
