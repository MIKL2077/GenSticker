const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm')
const saved=new Map(),events=[];let session=null
const ctx={visitorHeaders:()=>({}),uni:{getStorageSync:key=>key==='gensticker.session.v1'?session:saved.get(key),setStorageSync:(key,value)=>saved.set(key,value),$emit:(...a)=>events.push(a)},apiRequest:async()=>({key:'next'})}
vm.createContext(ctx);vm.runInContext(fs.readFileSync('src/services/trialService.js','utf8').replace(/^import .*$/gm,'').replace(/export /g,''),ctx)
;(async()=>{
 assert.equal(ctx.hasUsedTrial('a'),false);ctx.markTrialUsed('a');assert.equal(ctx.hasUsedTrial('a'),true);assert.equal(ctx.hasUsedTrial('new'),false)
 session={profile:{id:'another-account'}};assert.equal(ctx.hasUsedTrial('a'),false);ctx.markTrialUsed('b');assert.equal(ctx.hasUsedTrial('b'),true)
 session=null;assert.equal(ctx.hasUsedTrial('b'),false);assert.equal(ctx.hasUsedTrial('a'),true)
 for(let i=0;i<180;i++)ctx.markTrialUsed('t'+i)
 assert.equal(saved.get('gensticker.trial.used.v1.guest').length,128)
 assert.equal((await ctx.getCurrentTrial()).key,'next');assert.ok(events.length)
 ctx.API_BASE_URL='https://public.example';ctx.requestError=e=>e
 const headers=[];ctx.uni.request=async options=>{headers.push(options.header);return {statusCode:options.method==='POST'?204:200,data:{key:'next'}}}
 vm.runInContext(fs.readFileSync('src/services/apiService.js','utf8').replace(/^import .*$/gm,'').replace(/export /g,''),ctx)
 session={profile:{id:'account-a'},access_token:'test-account-a-token'}
 await ctx.getCurrentTrial();await ctx.apiRequest('/templates/trial/use',{method:'POST'},1)
 assert.equal(headers[0].Authorization,'Bearer test-account-a-token');assert.equal(headers[1].Authorization,'Bearer test-account-a-token')
 console.log('PASS used trial hides persistently, next template appears, account isolation, bounded records and authenticated trial requests')
})().catch(e=>{console.error(e);process.exitCode=1})
