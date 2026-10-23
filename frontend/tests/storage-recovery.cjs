const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path')
const removed=[],evicted=[]
const files=['gensticker_edit_stale.png','gensticker_edit_active.png','gensticker_material_cached.png','generated_meme_kept.png','original-photo.jpg','avatar_alice.jpg']
const storage={'gensticker.manual.local.alice.v1':[{created_at:Date.now()/1000,localPath:'/user/generated_meme_kept.png',editDraft:{paths:['/user/gensticker_draft_kept.png']}}]}
const c={uni:{env:{USER_DATA_PATH:'/user'},getStorageInfoSync:()=>({keys:Object.keys(storage)}),getStorageSync:key=>storage[key],getFileSystemManager:()=>({readdir:o=>setImmediate(()=>o.success({files})),stat:o=>o.success({stats:{size:200,lastModifiedTime:1}}),unlink:o=>{removed.push(o.filePath);o.success?.()}})},URL:{revokeObjectURL:()=>{}}}
vm.createContext(c);vm.runInContext(fs.readFileSync(path.join(__dirname,'../src/services/ownedFiles.js'),'utf8').replace(/export /g,'')+'\nthis.register=registerTemporary',c)
;(async()=>{
 c.register('/user/gensticker_edit_active.png');c.registerCacheFile('/tmp/public-preview.png',{bytes:100,onEvict:()=>evicted.push(true)})
 let attempts=0;const output=await c.withStorageRecovery(async()=>{if(!attempts++)throw {errMsg:'canvasToTempFilePath:fail the maximum size of the file storage limit is exceeded'};return'/new-result.png'})
 assert.equal(output,'/new-result.png');assert.equal(attempts,2);assert.deepEqual(evicted,[true]);assert.ok(removed.includes('/tmp/public-preview.png'));assert.ok(removed.includes('/user/gensticker_edit_stale.png'));assert.ok(removed.includes('/user/gensticker_material_cached.png'))
 assert.ok(!removed.some(file=>/active|kept|original-photo|avatar/.test(file)),'source photos, active work and valid queue items survive recovery')
 let tries=0;const permission=Error('permission denied')
 await assert.rejects(c.withStorageRecovery(async()=>{if(!tries++)throw {errMsg:'storage quota exceeded'};throw permission}),error=>error===permission,'retry errors retain their real cause')
 await assert.rejects(c.withStorageRecovery(async()=>{throw {errMsg:'disk full'}}),error=>error.code==='LOCAL_STORAGE_FULL'&&!/微信存储|重新打开/.test(error.message))
 console.log('PASS silent canvas/file recovery, reusable-cache eviction, async filesystem scanning, original/queue protection and accurate retry errors')
})().catch(error=>{console.error(error);process.exitCode=1})
