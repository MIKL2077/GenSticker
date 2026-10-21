const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path')
const source=fs.readFileSync(path.join(__dirname,'../src/services/imageEditing.js'),'utf8').replace(/^import .*$/gm,'').replace(/export /g,'')
;(async()=>{
 let owner='alice',mode='local';const requests=[],downloads=[],released=[],saved=[],edits=[]
 const ticket='/images/subject-results/'+'a'.repeat(40)
 const c={setTimeout,clearTimeout,requestError:e=>Error(e.statusCode===403?'服务入口拒绝访问':'连接模板服务超时'),Uint8Array,decodeURIComponent,API_BASE_URL:'https://example.test',ArrayBuffer,Math,Date,Error,prepareImage:async path=>path,prepareForeground:async()=>mode==='local'?{path:'/local-cutout.png'}:{upload:'/small-upload.jpg'},visitorHeaders:()=>({Authorization:'Bearer '+owner}),registerTemporary:path=>{saved.push(path);return path},releaseTemporary:path=>released.push(path),uni:{getStorageSync:()=>({profile:{id:owner}}),getFileSystemManager:()=>({stat:o=>o.success({stats:{size:100}}),readFile:o=>o.success({data:'encoded'})}),uploadFile:options=>{requests.push(options);options.success({statusCode:200,data:JSON.stringify({image_url:ticket})})},downloadFile:o=>{downloads.push(o);o.success({statusCode:200,tempFilePath:'/downloaded.png'});return{abort(){}}}}}
 vm.createContext(c);vm.runInContext(source,c)
 c.editImage=async(path,op)=>{edits.push({path,op});return '/normalized.png'}
 assert.equal(await c.removeImageBackground('/photo'),'/local-cutout.png');assert.equal(requests.length,0,'device cutout never uploads')
 mode='server';assert.equal(await c.removeImageBackground('/photo'),'/normalized.png')
 assert.equal(requests.length,1);assert.equal(requests[0].filePath,'/small-upload.jpg')
 assert.equal(downloads[0].url,'https://example.test'+ticket);assert.equal(downloads[0].header.Authorization,'Bearer alice')
 assert.equal(edits[0].op.fileType,'png');assert.ok(released.includes('/downloaded.png'));assert.ok(released.includes('/small-upload.jpg'))
 c.uni.uploadFile=o=>o.success({statusCode:200,data:JSON.stringify({image_url:'https://attacker.test/image'})})
 await assert.rejects(c.removeImageBackground('/photo'),/地址无效/);assert.equal(downloads.length,1,'credentials are never sent to external download URLs')
 c.uni.uploadFile=o=>o.success({statusCode:422,data:JSON.stringify({detail:'先框选主体再试试'})});await assert.rejects(c.removeImageBackground('/photo'),/先框选主体/,'binary error details remain readable')
 c.uni.uploadFile=o=>o.fail({errMsg:'uploadFile:fail timeout'});await assert.rejects(c.removeImageBackground('/photo'),/连接模板服务超时/,'native plain-object errors are translated')
 c.uni.uploadFile=o=>o.success({statusCode:200,data:JSON.stringify({image_url:ticket})});c.uni.downloadFile=o=>o.fail({errMsg:'downloadFile:fail timeout'})
 await assert.rejects(c.removeImageBackground('/photo'),/连接模板服务超时/)
 c.prepareForeground=async()=>{owner='bob';return {upload:'/previous-owner-upload.jpg'}}
 await assert.rejects(c.removeImageBackground('/photo'),/账号已切换/);assert.equal(requests.length,1);assert.ok(released.includes('/previous-owner-upload.jpg'))
 // Explicit download deadlines abort the task and discard late cache files.
 let expire,late,aborted=false;c.setTimeout=fn=>{expire=fn;return 1};c.clearTimeout=()=>{};c.uni.downloadFile=o=>{late=o;return{abort(){aborted=true}}}
 const pending=c.downloadSubjectPreview(ticket,{});expire();await assert.rejects(pending,/连接模板服务超时/);assert.equal(aborted,true)
 late.success({statusCode:200,tempFilePath:'/late.png'});assert.ok(released.includes('/late.png'))
 console.log('PASS local cutout, private bounded result download, PNG normalization, safe URL/identity checks, error details and deadline cleanup')
})().catch(error=>{console.error(error);process.exitCode=1})
