const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path')
const source=fs.readFileSync(path.join(__dirname,'../src/services/templateExample.js'),'utf8').replace(/^import .*$/gm,'').replace(/export /g,'')
const sharing=fs.readFileSync(path.join(__dirname,'../src/services/wechatSharing.js'),'utf8').replace(/export /g,'')
function runtime(){
 const released=[],registered=[],downloads=[],caches=[];let menu,bytes=new Uint8Array([71,73,70,56,57,97,0,0,0,0,0,0])
 const c={Promise,Date,Math,Error,Uint8Array,API_BASE_URL:'https://example.test',registerCacheFile:(path,options)=>caches.push({path,...options}),registerTemporary:p=>(registered.push(p),p),releaseTemporary:p=>released.push(p),downloadResult:async url=>(downloads.push(url),'/download'),
 uni:{env:{USER_DATA_PATH:'/owned'},getFileSystemManager:()=>({stat:o=>o.success({stats:{size:500}}),readFile:o=>o.success({data:bytes.buffer}),copyFile:o=>o.success()}),showShareImageMenu:o=>menu=o}}
 vm.createContext(c);vm.runInContext(source+'\n'+sharing,c)
 return {c,released,registered,downloads,caches,get menu(){return menu},corrupt(){bytes=new Uint8Array([123,34,100,101,116,97,105,108])}}
}
;(async()=>{
 const r=runtime(),file=await r.c.loadTemplateExample({key:'auto_example',version:3})
 assert.equal(r.downloads[0],'/memes/auto_example/example?v=3');assert.match(file,/\.gif$/);assert.deepEqual(r.released,['/download'])
 const sharing=r.c.shareOriginalImage(file);assert.equal(r.menu.path,file);assert.equal(r.caches[0].protected(),true);let finished=false;sharing.then(()=>finished=true);await Promise.resolve();assert.equal(finished,false,'file stays alive while the native menu is open');r.menu.success();await sharing;assert.equal(finished,true)
 const privateFile=await r.c.loadTemplateExample({key:'private-id',ownPreview:'/studio/templates/private-id/preview'})
 assert.equal(r.downloads.at(-1),'/studio/templates/private-id/preview');assert.equal(r.caches[0].protected(),false);assert.equal(r.caches.at(-1).protected(),true);assert.match(privateFile,/\.gif$/)
 let current=true;r.c.downloadResult=async()=>{current=false;return '/late-download'};await assert.rejects(r.c.loadTemplateExample({key:'old'},()=>current),/已取消/);assert.equal(r.released.at(-1),'/late-download')
 const corrupt=runtime();corrupt.corrupt();await assert.rejects(corrupt.c.loadTemplateExample({key:'broken'}),/未完整/);assert.equal(corrupt.released.at(-1),'/download')
 const closed=runtime();let alive=true;closed.c.uni.getFileSystemManager=()=>({stat:o=>o.success({stats:{size:50}}),readFile:o=>o.success({data:new Uint8Array([255,216,255]).buffer}),copyFile:o=>{alive=false;o.success()}})
 await assert.rejects(closed.c.loadTemplateExample({key:'closed'},()=>alive),/已取消/);assert.ok(closed.released.some(p=>p.endsWith('.jpg')),'late copied files are cleaned too')
 const direct=runtime();let emoji,image;direct.c.wx={getEnterOptionsSync:()=>({apiCategory:'chatTool'}),shareEmojiToGroup:o=>emoji=o,shareImageToGroup:o=>image=o};const task=direct.c.shareOriginalImage('/full.gif');emoji.fail({errMsg:'not supported'});assert.equal(image.imagePath,'/full.gif');image.fail({errMsg:'not supported'});direct.menu.fail({errMsg:'cancel'});await task
 console.log('PASS full GIF example route, private preview, native share lifetime/fallback, corrupt replies and cancellation cleanup')
})().catch(e=>{console.error(e);process.exitCode=1})
