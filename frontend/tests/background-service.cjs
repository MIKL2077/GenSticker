const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path')
const source=fs.readFileSync(path.join(__dirname,'../src/services/imageEditing.js'),'utf8').replace(/^import .*$/gm,'').replace(/export /g,'')
;(async()=>{
 let owner='alice',mode='local';const requests=[],released=[],saved=[],writes=[]
 const c={API_BASE_URL:'https://example.test',ArrayBuffer,Math,Date,Error,prepareImage:async path=>path,prepareForeground:async()=>mode==='local'?{path:'/local-cutout.png'}:{upload:'/small-upload.jpg'},visitorHeaders:()=>({Authorization:'Bearer '+owner}),registerTemporary:path=>{saved.push(path);return path},releaseTemporary:path=>released.push(path),writeOwnedFile:async(path,data)=>writes.push([path,data]),uni:{env:{USER_DATA_PATH:'/user'},getStorageSync:()=>({profile:{id:owner}}),getFileSystemManager:()=>({stat:o=>o.success({stats:{size:100}}),readFile:o=>o.success({data:'encoded'})}),request:async options=>{requests.push(options);return {statusCode:200,data:new ArrayBuffer(4)}}}}
 vm.createContext(c);vm.runInContext(source,c)
 assert.equal(await c.removeImageBackground('/photo'),'/local-cutout.png');assert.equal(requests.length,0,'device cutout does not upload the photo')
 mode='server';const output=await c.removeImageBackground('/photo');assert.match(output,/gensticker_edit_.*\.png$/);assert.equal(requests.length,1);assert.equal(requests[0].responseType,'arraybuffer');assert.equal(requests[0].data.delivery,'binary');assert.equal(writes.length,1);assert.ok(released.includes('/small-upload.jpg'),'compressed upload is temporary')
 c.prepareForeground=async()=>{owner='bob';return {upload:'/previous-owner-upload.jpg'}}
 await assert.rejects(c.removeImageBackground('/photo'),/账号已切换/);assert.equal(requests.length,1,'account change prevents upload under a different identity');assert.ok(released.includes('/previous-owner-upload.jpg'))
 console.log('PASS no upload after local cutout, one binary fallback request, bounded temporary upload cleanup and account-switch isolation')
})().catch(error=>{console.error(error);process.exitCode=1})
