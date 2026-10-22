const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path')
let version=1;const pending=[],removed=[]
const context={Map,Set,Array,Promise,Date,Error,encodeURIComponent,setTimeout,API_BASE_URL:'https://example.test/api',
 apiRequest:async()=>({cards:[{key:'same',version}]}),apiImageRequest:()=>{},
 uni:{downloadFile:args=>pending.push(args),getFileSystemManager:()=>({unlink:args=>removed.push(args.filePath)})}}
vm.createContext(context)
const source=fs.readFileSync(path.join(__dirname,'../src/services/memeService.js'),'utf8')
 .replace(/^import .*$/gm,'').replace(/export /g,'')
 .replace(/  \/\/ #ifdef H5[\s\S]*?  \/\/ #endif/,'')
vm.runInContext(source,context)
;(async()=>{
 await context.getCategories();const old=context.getTemplatePreviewPath('same').catch(error=>error)
 assert.match(pending[0].url,/v=1$/)
 version=2;await context.getCategories(true);const current=context.getTemplatePreviewPath('same')
 assert.match(pending[1].url,/v=2$/)
 pending[0].success({statusCode:200,tempFilePath:'/old.png'})
 assert.ok(await old instanceof Error);assert.ok(removed.includes('/old.png'))
 pending[1].success({statusCode:200,tempFilePath:'/current.png'})
 assert.equal(await current,'/current.png');assert.equal(await context.getTemplatePreviewPath('same'),'/current.png')
 version=3;await context.getCategories(true);assert.ok(removed.includes('/current.png'))
 console.log('PASS catalog version changes invalidate cached and in-flight thumbnails without stale completion overwrites')
})().catch(error=>{console.error(error);process.exitCode=1})
