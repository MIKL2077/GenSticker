const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path')
const source=fs.readFileSync(path.join(__dirname,'../src/services/memeService.js'),'utf8').replace(/^import .*$/gm,'').replace(/export /g,'').replace(/  \/\/ #ifdef H5[\s\S]*?  \/\/ #endif/,'')
const storage=new Map(),files=new Set();let network=0,downloads=0,resolveCatalog,version=1
const card=()=>({cards:[{key:'animated',version,animated:true}],all:['animated']})
function session(){
 const c={Map,Set,Date,Promise,Error,setTimeout,encodeURIComponent,API_BASE_URL:'https://public.test',registerCacheFile:()=>{},apiImageRequest:()=>{},
 apiRequest:()=>{network++;return new Promise(resolve=>{resolveCatalog=()=>resolve(card())})},
 uni:{env:{USER_DATA_PATH:'/owned'},getStorageSync:key=>storage.get(key),setStorageSync:(key,value)=>storage.set(key,JSON.parse(JSON.stringify(value))),
 getFileSystemManager:()=>({access:o=>files.has(o.path)?o.success():o.fail(),copyFile:o=>{files.add(o.destPath);o.success()},stat:o=>o.success({stats:{size:2000}}),unlink:o=>{files.delete(o.filePath);o.success?.()}}),
 downloadFile:o=>{downloads++;o.success({statusCode:200,tempFilePath:'/temp.gif'})}}}
 vm.createContext(c);vm.runInContext(source,c);return c
}
;(async()=>{
 let c=session();let task=c.getCategories();resolveCatalog();await task
 let path=await c.getTemplatePreviewPath('animated');assert.match(path,/\.gif$/);assert.equal(downloads,1)
 c=session();let refreshed=false;let immediate=await c.getCategories(false,()=>{refreshed=true});assert.equal(immediate.cards[0].version,1);assert.equal(refreshed,false)
 assert.equal(await c.getTemplatePreviewPath('animated'),path);assert.equal(downloads,1,'new session uses persistent public GIF')
 version=2;resolveCatalog();await new Promise(r=>setImmediate(r));assert.equal(refreshed,true)
 assert.notEqual(await c.getTemplatePreviewPath('animated'),path);assert.equal(downloads,2,'new version cannot return an old public file')
 files.clear();c=session();task=c.getCategories(true);resolveCatalog();await task
 await c.getTemplatePreviewPath('animated');assert.equal(downloads,3,'missing persistent files redownload normally')
 const count=downloads;for(let i=0;i<50;i++)await c.getTemplatePreviewPath('public_'+i)
 const beforeReturn=downloads;await c.getTemplatePreviewPath('public_0');assert.equal(downloads,beforeReturn+1,'disk eviction invalidates memory paths before a later page revisit')
 console.log('PASS persistent public GIF/catalog, immediate reopen, live refresh, version invalidation and missing-file recovery')
})().catch(error=>{console.error(error);process.exitCode=1})
