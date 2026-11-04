// Repeatable simulator timings. Values are not physical-device FPS claims.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os'),net=require('node:net')
const automator=require('miniprogram-automator')
const output=path.resolve(process.argv[2]||'/tmp/gensticker-interaction-performance')
async function main(){
 fs.mkdirSync(output,{recursive:true})
 const project=fs.mkdtempSync(path.join(os.tmpdir(),'gensticker-performance-'))
 fs.cpSync(path.resolve(__dirname,'../dist/build/mp-weixin'),project,{recursive:true,filter:f=>path.basename(f)!=='project.private.config.json'})
 const config=JSON.parse(fs.readFileSync(path.join(project,'project.config.json')));assert.equal(config.setting.urlCheck,true)
 config.projectname='GenSticker-performance-'+Date.now();fs.writeFileSync(path.join(project,'project.config.json'),JSON.stringify(config))
 const port=await new Promise((resolve,reject)=>{const s=net.createServer();s.once('error',reject);s.listen(0,'127.0.0.1',()=>{const p=s.address().port;s.close(()=>resolve(p))})})
 const app=await automator.launch({projectPath:project,port,cliPath:process.env.WECHAT_DEVTOOLS_CLI_PATH||'/Applications/wechatwebdevtools.app/Contents/MacOS/cli',timeout:60000})
 const errors=[];app.on('exception',e=>errors.push(e.message||String(e)))
 try{
  const until=Date.now()+60000
  while(Date.now()<until){if(await app.evaluate(()=>!!getCurrentPages().at(-1)?.$vm?.currentPageTemplates?.length&&!getCurrentPages().at(-1)?.$vm?.isLoadingTemplates))break;await new Promise(r=>setTimeout(r,200))}
  assert.ok(await app.evaluate(()=>getCurrentPages().at(-1)?.$vm?.currentPageTemplates?.length))
  const report=await app.evaluate(async()=>{
   const page=getCurrentPages().at(-1),vm=page.$vm,rows=[],setData=[],gaps=[]
   const previousSetData=page.setData;page.setData=function(data,callback){setData.push({at:Date.now(),characters:JSON.stringify(data).length,fields:Object.keys(data).length});return previousSetData.call(this,data,callback)}
   let last=Date.now();const timer=setInterval(()=>{const t=Date.now();gaps.push(t-last);last=t},16)
   const render=()=>new Promise(resolve=>vm.$nextTick(()=>wx.nextTick(resolve)))
   const measure=async(name,run)=>{const t=Date.now(),start=setData.length;await run();await render();rows.push({name,elapsedMs:Date.now()-t,setDataCalls:setData.length-start,maxSetDataCharacters:Math.max(0,...setData.slice(start).map(r=>r.characters))})}
   const generated=[]
   try{
    for(const q of ['奶龙','主内','中文','猫咪快乐动图','ASCII','不存在XYZ987',''])await measure('search:'+q,()=>vm.setSearchQuery(q))
    await measure('page:next',()=>vm.nextPage());await measure('page:previous',()=>vm.prevPage())
    await measure('category:text',()=>vm.onSelectCategory('text'));await measure('category:all',()=>vm.onSelectCategory('all'))
    await measure('detail:first',()=>vm.onSelectTemplate('erised_mirror'));await measure('detail:close',()=>vm.closeTemplateDetail())
    await measure('detail:cached',()=>vm.onSelectTemplate('erised_mirror'));vm.closeTemplateDetail()
    const edits=require('services/imageEditing.js'),upload=require('services/generationUpload.js')
    for(const type of ['flip','rotate'])await measure('image:'+type,async()=>{generated.push(await edits.editImage('/static/logo-subject.png',{type}))})
    await measure('image:encode-upload',()=>upload.encodeGenerationImages(['/static/logo-subject.png']))
    await new Promise(r=>setTimeout(r,500))
    return {scope:'WeChat DevTools SDK 3.17.5; elapsed inside logic thread through Vue nextTick and wx.nextTick; instrumentation overhead included; no physical-device FPS',rows,timer:{intervalMs:16,samples:gaps.length,maxGapMs:Math.max(0,...gaps),p95GapMs:[...gaps].sort((a,b)=>a-b)[Math.floor(gaps.length*.95)]},bridge:{calls:setData.length,maxCharacters:Math.max(0,...setData.map(r=>r.characters)),note:'JSON character count, not UTF-8 byte count'},catalogCount:vm.searchResultCount}
   }finally{clearInterval(timer);page.setData=previousSetData;for(const p of generated)require('services/imageEditing.js').disposeEditedImage(p)}
  })
  assert.deepEqual(errors,[]);assert.ok(report.rows.length>=16)
  report.status='passed';report.runtimeErrors=errors
  fs.writeFileSync(path.join(output,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report))
 }finally{await app.close()}
}
const watchdog=setTimeout(()=>{console.error('Interaction verification timed out');process.exit(1)},180000);watchdog.unref()
main().catch(e=>{console.error(e);process.exitCode=1}).finally(()=>clearTimeout(watchdog))
