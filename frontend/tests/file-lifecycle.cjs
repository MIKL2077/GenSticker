const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm')
const source=fs.readFileSync(path.join(__dirname,'../src/services/ownedFiles.js'),'utf8').replace(/export /g,'')
const INDEX='gensticker.files.v1',files=new Map(),storage=new Map(),removed=[],warnings=[],failures=new Set()
let now=1793090000000,afterRemove=()=>{}
const add=(path,bytes=100)=>files.set(path,{size:bytes,lastModifiedTime:(now-120000)/1000})
const flush=()=>new Promise(resolve=>setImmediate(resolve))
function session(){
 const c={setTimeout,Date:class extends Date{static now(){return now}},console:{warn:(...args)=>warnings.push(args)},URL:{revokeObjectURL:()=>{}},uni:{env:{USER_DATA_PATH:'/user'},
 getStorageSync:key=>storage.get(key),setStorageSync:(key,value)=>storage.set(key,JSON.parse(JSON.stringify(value))),getStorageInfoSync:()=>({keys:[...storage.keys()]}),
 getFileSystemManager:()=>({readdir:o=>setImmediate(()=>o.success({files:[...files.keys()].filter(p=>p.startsWith(o.dirPath+'/')).map(p=>p.slice(o.dirPath.length+1)).filter(p=>!p.includes('/'))})),
 stat:o=>setImmediate(()=>files.has(o.path)?o.success({stats:files.get(o.path)}):o.fail({errMsg:'stat:fail no such file'})),
 unlink:o=>setImmediate(()=>{if(failures.has(o.filePath))return o.fail({errMsg:'unlink:fail permission denied'});if(!files.has(o.filePath))return o.fail({errMsg:'unlink:fail no such file'});files.delete(o.filePath);removed.push(o.filePath);afterRemove(o.filePath);o.success()})})}}
 vm.createContext(c);vm.runInContext(source,c);return c
}
;(async()=>{
 const original='/tmp/album-original.jpg',unknown='/tmp/unidentified.png',model='/user/gensticker_u2netp_309c8469.onnx',avatar='/user/avatar_alice.jpg'
 for(const p of [original,unknown,model,avatar,'/tmp/orphan-cutout.png','/tmp/unfinished.png','/tmp/current-edit.png','/tmp/queue-alice.gif','/user/gensticker_draft_alice_0.png','/tmp/queue-guest.gif','/tmp/live-source.mp4','/tmp/public.gif','/user/gensticker_edit_legacy.png'])add(p)
 storage.set('gensticker.manual.local.alice.v1',[{localPath:'/tmp/queue-alice.gif',created_at:now/1000,editDraft:{paths:['/user/gensticker_draft_alice_0.png'],mediaPath:'/tmp/live-source.mp4'}}])
 storage.set('gensticker.manual.local.guest.v1',[{localPath:'/tmp/queue-guest.gif',created_at:now/1000}])
 let first=session()
 for(const p of ['/tmp/orphan-cutout.png','/tmp/unfinished.png','/tmp/queue-alice.gif','/tmp/live-source.mp4'])first.registerTemporary(p)
 first.registerCacheFile('/tmp/public.gif',{bytes:100})
 assert.ok(storage.get(INDEX).files.some(f=>f.path==='/tmp/orphan-cutout.png'),'ownership persists before a crash/recompile')
 now+=120000
 let current=session();current.registerTemporary('/tmp/current-edit.png');current.registerCacheFile('/tmp/public.gif',{bytes:100,protected:()=>true})
 await current.trimOwnedFiles({materials:true})
 assert.ok(!files.has('/tmp/orphan-cutout.png')&&!files.has('/tmp/unfinished.png')&&!files.has('/user/gensticker_edit_legacy.png'))
 for(const p of [original,unknown,model,avatar,'/tmp/current-edit.png','/tmp/queue-alice.gif','/user/gensticker_draft_alice_0.png','/tmp/queue-guest.gif','/tmp/live-source.mp4','/tmp/public.gif'])assert.ok(files.has(p),'must preserve '+p)
 current.registerTemporary('/tmp/queue-alice.gif');current.releaseTemporary('/tmp/queue-alice.gif');await flush();assert.ok(files.has('/tmp/queue-alice.gif'),'queue reference wins over producer release')
 add('/tmp/a.gif');add('/tmp/b.gif');let showingB=false
 current.registerCacheFile('/tmp/a.gif',{bytes:100});current.registerCacheFile('/tmp/b.gif',{bytes:100,protected:()=>showingB})
 afterRemove=p=>{if(p==='/tmp/a.gif')showingB=true}
 await current.trimOwnedFiles({materials:true});assert.ok(!files.has('/tmp/a.gif'));assert.ok(files.has('/tmp/b.gif'),'visibility is checked again during a sweep')
 afterRemove=()=>{}
 add('/tmp/stubborn.png');current.registerTemporary('/tmp/stubborn.png');failures.add('/tmp/stubborn.png');current.releaseTemporary('/tmp/stubborn.png');await flush();await flush()
 assert.ok(storage.get(INDEX).files.some(f=>f.path==='/tmp/stubborn.png'))
 failures.clear();now+=120000;current=session();await current.trimOwnedFiles();assert.ok(!files.has('/tmp/stubborn.png'))
 now+=8*86400000;current=session();await current.trimOwnedFiles()
 for(const p of ['/tmp/queue-alice.gif','/user/gensticker_draft_alice_0.png','/tmp/queue-guest.gif','/tmp/live-source.mp4'])assert.ok(!files.has(p),'expired work follows its existing seven-day retention')
 for(const p of [original,unknown,model,avatar])assert.ok(files.has(p))
 add('/tmp/pause-a.png');add('/tmp/pause-b.png');current.registerTemporary('/tmp/pause-a.png');current.registerTemporary('/tmp/pause-b.png');now+=120000;current=session();let idle=true
 afterRemove=()=>{idle=false};const paused=await current.trimOwnedFiles({materials:true,canContinue:()=>idle});assert.equal(paused.removed,1);assert.ok(files.has('/tmp/pause-a.png')||files.has('/tmp/pause-b.png'))
 afterRemove=()=>{};await current.trimOwnedFiles({materials:true});assert.ok(!files.has('/tmp/pause-a.png')&&!files.has('/tmp/pause-b.png'))
 add('/tmp/leased-source.png');current.registerTemporary('/tmp/leased-source.png');now+=120000;current=session();const unpin=current.retainFile('/tmp/leased-source.png');await current.trimOwnedFiles();assert.ok(files.has('/tmp/leased-source.png'));unpin();unpin();await current.trimOwnedFiles();assert.ok(!files.has('/tmp/leased-source.png'),'reader lease protects an existing source without taking ownership');
 let attempts=0;const permission={errMsg:'writeFile:fail permission denied in storage'}
 await assert.rejects(current.withStorageRecovery(async()=>{attempts++;throw permission}),e=>e===permission);assert.equal(attempts,1)
 await assert.rejects(current.withStorageRecovery(async()=>{throw {errMsg:'writeFile:fail the maximum size of the file storage limit is exceeded'}}),e=>e.code==='LOCAL_STORAGE_FULL'&&e.cause.errMsg.includes('storage limit'))
 assert.ok(warnings.at(-1)[1].errMsg.includes('writeFile:fail'))
 console.log('PASS persisted ownership, crash recovery, original protection, all-account results, live edit sources, visibility races, deletion retry, idle cancellation and original SDK errors')
})().catch(e=>{console.error(e);process.exitCode=1})
