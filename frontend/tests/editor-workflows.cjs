const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm')
const read=file=>fs.readFileSync(path.join(__dirname,'../src',file),'utf8').replace(/^import .*$/gm,'').replace(/export /g,'')
async function verify(){
 const removed=[],files=['gensticker_edit_old.png','gensticker_edit_active.png','gensticker_material_'+ 'a'.repeat(64)+'.png','generated_meme_kept.gif','generated_meme_expired.gif','my-photo.jpg','avatar-a.png']
 let attempts=0
 const fsMock={readdir:o=>o.success({files}),stat:o=>o.success({stats:{size:20,lastModifiedTime:1}}),unlink:o=>{removed.push(o.filePath);o.success?.()},writeFile:o=>{attempts++;attempts===1?o.fail({errMsg:'writeFile:fail the maximum size of the file storage limit is exceeded'}):o.success()}}
 const storage={'gensticker.manual.local.guest.v1':[{localPath:'/user/generated_meme_kept.gif',created_at:Date.now()/1000},{localPath:'/user/generated_meme_expired.gif',created_at:0}]}
 const c={uni:{env:{USER_DATA_PATH:'/user'},getFileSystemManager:()=>fsMock,getStorageInfoSync:()=>({keys:Object.keys(storage)}),getStorageSync:k=>storage[k]},URL:{revokeObjectURL:()=>{}}}
 vm.createContext(c);vm.runInContext(read('services/ownedFiles.js')+'\nthis.register=registerTemporary',c)
 c.register('/user/gensticker_edit_active.png');await c.trimOwnedFiles()
 assert.deepEqual(removed.sort(),['/user/generated_meme_expired.gif','/user/gensticker_edit_old.png'].sort())
 assert.ok(!removed.some(p=>/my-photo|avatar|active|material|kept/.test(p)),'originals, active editor outputs and current queue results survive cleanup')
 await c.writeOwnedFile('/user/gensticker_edit_new.png',new ArrayBuffer(10));assert.equal(attempts,2,'quota failure cleans owned files and retries once')
 removed.length=0;await c.trimOwnedFiles({materials:true});assert.ok(removed.some(p=>p.includes('material_')))
 const actions=[],share={uni:{setClipboardData:o=>o.success()},wx:{showShareImageMenu:o=>actions.push(['menu',o]),getEnterOptionsSync:()=>({apiCategory:'default'}),shareEmojiToGroup:o=>actions.push(['emoji',o])}}
 vm.createContext(share);vm.runInContext(read('services/wechatSharing.js'),share)
 share.shareOriginalImage('/result.png');assert.equal(actions[0][0],'menu');assert.equal(actions[0][1].needShowEntrance,false)
 share.wx.getEnterOptionsSync=()=>({apiCategory:'chatTool'});share.shareOriginalImage('/result.gif');assert.equal(actions[1][0],'emoji')
 actions[1][1].fail({errMsg:'cancel'});assert.equal(actions.length,2,'cancel must never reopen another sharing menu')
 actions[1][1].fail({errMsg:'not supported'});assert.equal(actions[2][0],'menu','unsupported direct sharing falls back to the native image menu')
 console.log('PASS cache quota retry, original/active/queue preservation, native image sharing and cancellation')
}
verify().catch(e=>{console.error(e);process.exitCode=1})
