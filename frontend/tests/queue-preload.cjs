const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path')
const source=fs.readFileSync(path.join(__dirname,'../src/services/studioService.js'),'utf8').replace(/^import .*$/gm,'').replace(/export /g,'')
const flush=()=>new Promise(resolve=>setImmediate(resolve))
;(async()=>{
 const store=new Map();let owner='alice',token='token-a',requests=0,resolveList,downloads=[],active=0,maxActive=0
 const imageFinishes=[]
 const c={ref:value=>({value}),console,Date,Math,Map,Set,Promise,Object,JSON,Error,setInterval:()=>0,clearInterval:()=>{},uni:{getStorageSync:key=>key==='gensticker.session.v1'?(owner?{access_token:token,profile:{id:owner}}:null):store.get(key),setStorageSync:(k,v)=>store.set(k,JSON.parse(JSON.stringify(v)))},apiRequest:()=>{requests++;return new Promise(resolve=>resolveList=resolve)},downloadResult:url=>{downloads.push(url);active++;maxActive=Math.max(active,maxActive);return new Promise(resolve=>imageFinishes.push(()=>{active--;resolve('/thumb-'+url.split('/')[3])}))}}
 vm.createContext(c);vm.runInContext(source,c)
 const rows=Array.from({length:9},(_,i)=>({id:'job-'+i,kind:'livegif',status:'completed',created_at:Date.now()/1000,viewed:false,result_url:'/studio/jobs/job-'+i+'/image'}))
 const before=c.preloadStudioQueue(),second=c.listStudioJobs();assert.equal(requests,1,'entry preload and queue navigation coalesce metadata requests');resolveList(rows)
 const loaded=await before;await second;assert.equal(loaded.length,9);await flush();assert.ok(downloads.length<=3);assert.ok(downloads.every(url=>url.endsWith('/thumbnail')),'preload never downloads full GIFs')
 assert.equal(c.cachedStudioJobs().length,9,'metadata is available while thumbnails are still pending');await c.listStudioJobs();assert.equal(requests,1)
 let delivered=0;const warming=c.warmQueueThumbnails(rows,()=>delivered++)
 for(let i=0;i<15;i++){for(const finish of imageFinishes.splice(0))finish();await flush()}
 await warming;assert.equal(maxActive,3,'all concurrent preload callers share one three-download budget');assert.equal(delivered,9);assert.ok(c.cachedQueueThumbnail(rows[0]))
 const delayed=c.listStudioJobs({force:true});owner='bob';token='token-b';assert.equal(c.cachedStudioJobs().length,0);resolveList(rows);await delayed;assert.equal(c.cachedStudioJobs().length,0,'late previous-account list is discarded')
 owner='alice';token='new-token-a';assert.equal(c.cachedStudioJobs().length,9,'same owner can show persisted small metadata immediately');assert.equal(c.cachedQueueThumbnail(rows[0]),'','private image cache does not cross sessions')
 const refresh=c.listStudioJobs();resolveList(rows.slice(1));await refresh;assert.equal(c.cachedStudioJobs().length,8)
 console.log('PASS queue preload deduplication, immediate cached metadata, bounded thumbnail-only downloads, persistence and account/session isolation')
})().catch(error=>{console.error(error);process.exitCode=1})
