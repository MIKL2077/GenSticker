// Use real queue taps, WeChat rendering, canvas and filesystem. Only fixtures
// and outbound share/album APIs are replaced, so no user photos are sent.
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),net=require('node:net'),crypto=require('node:crypto')
const automator=require('miniprogram-automator'),{GifReader,GifWriter}=require('omggif')
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms))
const output=path.resolve(process.argv[2]||fs.mkdtempSync(path.join(os.tmpdir(),'gensticker-queue-proof-')))
function gif(color,delay){const bytes=new Uint8Array(20000),w=new GifWriter(bytes,64,64,{palette:[0xfffaf4,color,0x283c44,0xffffff],loop:0});for(let i=0;i<6;i++){const pixels=new Uint8Array(4096);for(let y=12;y<52;y++)for(let x=8+i*3;x<28+i*3;x++)pixels[y*64+x]=1;w.addFrame(0,0,64,64,pixels,{delay})}return Buffer.from(bytes.subarray(0,w.end()))}
async function verify(){
 fs.mkdirSync(output,{recursive:true})
 const project=fs.mkdtempSync(path.join(os.tmpdir(),'gensticker-queue-project-')),build=path.resolve(__dirname,'../dist/build/mp-weixin')
 fs.cpSync(build,project,{recursive:true,filter:file=>path.basename(file)!=='project.private.config.json'})
 const configPath=path.join(project,'project.config.json'),config=JSON.parse(fs.readFileSync(configPath));config.projectname='GenSticker-queue-'+path.basename(project).split('-').pop();fs.writeFileSync(configPath,JSON.stringify(config))
 const marker=crypto.randomUUID();fs.appendFileSync(path.join(project,'app.js'),'\nsetTimeout(function(){getApp().__queueBuild='+JSON.stringify(marker)+'},0);\n')
 const port=await new Promise(resolve=>{const server=net.createServer();server.listen(0,'127.0.0.1',()=>{const port=server.address().port;server.close(()=>resolve(port))})})
 const app=await automator.launch({projectPath:project,port,cliPath:'/Applications/wechatwebdevtools.app/Contents/MacOS/cli',timeout:60000}),errors=[],mocked=[],created=[]
 app.on('exception',e=>errors.push(String(e.message||e)))
 async function waitFor(check,label,timeout=30000){const end=Date.now()+timeout;do{assert.deepEqual(errors,[]);if(await check())return;await pause(200)}while(Date.now()<end);throw Error('Timed out: '+label)}
 const modalState=()=>app.evaluate(()=>{const vm=getCurrentPages().slice(-1)[0].selectComponent('.selected-results-host')?.$vm;return vm?{show:vm.show,busy:vm.busy,collage:vm.collage,error:vm.error,items:vm.items}:null})
 try{
  await waitFor(()=>app.evaluate(marker=>getApp().__queueBuild===marker&&!!getCurrentPages().slice(-1)[0]?.$vm,marker),'build startup',60000)
  await app.mockWxMethod('showShareImageMenu',function(o){getApp().__queueShare=o.path;return {errMsg:'showShareImageMenu:ok'}});mocked.push('showShareImageMenu')
  await app.mockWxMethod('saveImageToPhotosAlbum',function(o){getApp().__queueSave=o.filePath;return {errMsg:'saveImageToPhotosAlbum:ok'}});mocked.push('saveImageToPhotosAlbum')
  const fixtures=[gif(0xf37557,10),gif(0x82b79b,20)]
  const paths=await app.evaluate(base64s=>{
   const fs=wx.getFileSystemManager(),paths=base64s.map((data,i)=>{const p=wx.env.USER_DATA_PATH+'/gensticker_edit_queue_fixture_'+Date.now()+'_'+i+'.gif';fs.writeFileSync(p,data,'base64');return p})
   const canvas=wx.createOffscreenCanvas({type:'2d',width:64,height:64}),ctx=canvas.getContext('2d');ctx.fillStyle='#749ec9';ctx.fillRect(0,0,64,64)
   return new Promise((resolve,reject)=>wx.canvasToTempFilePath({canvas,fileType:'png',success:r=>resolve([...paths,r.tempFilePath]),fail:reject}))
  },fixtures.map(b=>b.toString('base64')));created.push(...paths)
  await app.evaluate(paths=>{
   const service=require('services/studioService.js');getApp().__queueOriginals={guestResults:service.guestResults,cachedStudioJobs:service.cachedStudioJobs,listStudioJobs:service.listStudioJobs}
   const items=paths.map((p,i)=>({id:'queue-fixture-'+i,local:true,kind:i<2?'livegif':'manual',localPath:p,status:'completed',created_at:Date.now()/1000-i,message:'拼图功能验收素材'}))
   items.push({id:'pending-fixture',local:true,kind:'manual',status:'running',created_at:Date.now()/1000-10,message:'制作中的图片不可选'})
   service.guestResults=()=>items;service.cachedStudioJobs=()=>[];service.listStudioJobs=async()=>[]
  },paths)
  await app.reLaunch('/pages/queue/index');await waitFor(async()=>{const p=await app.currentPage();return p?.path==='pages/queue/index'&&!!await p.$('.selection-toggle')},'queue page')
  const page=await app.currentPage();await app.screenshot({path:path.join(output,'queue-entry.png')});await (await page.$('.selection-toggle')).tap();await pause(300)
  const cards=await page.$$('.job-card');assert.equal(cards.length,4)
  await cards[3].tap();assert.match(await (await page.$('.selection-bar')).text(),/已选 0/)
  for(const [index,card] of [cards[1],cards[0],cards[2]].entries()){await card.tap();await waitFor(async()=>new RegExp('已选 '+(index+1)).test(await (await page.$('.selection-bar')).text()),'selection '+(index+1))}
  await app.screenshot({path:path.join(output,'queue-selection.png')})
  await (await page.$('.make-collage')).tap();await waitFor(async()=>{const s=await modalState();return s?.show&&!s.busy&&(s.collage||s.error)},'mixed collage export',60000)
  const state=await modalState();assert.equal(state.error,'');assert.equal(state.collage.animated,true);assert.equal(state.collage.duration,1200);assert.deepEqual(state.items.map(i=>i.path),[paths[1],paths[0],paths[2]])
  const bytes=Buffer.from(await app.evaluate(p=>wx.getFileSystemManager().readFileSync(p,'base64'),state.collage.path),'base64'),reader=new GifReader(bytes);assert.ok(reader.numFrames()>1);assert.equal(reader.loopCount(),0);assert.ok(bytes.length<2*1024*1024);fs.writeFileSync(path.join(output,'queue-collage.gif'),bytes)
  await app.screenshot({path:path.join(output,'queue-collage-preview.png')})
  const modal=await page.$('components\\/SelectedResultsModal');assert.ok(modal)
  await (await modal.$('.selected-results-actions .ui-secondary')).tap();await (await modal.$('.selected-results-actions .ui-primary')).tap();await waitFor(()=>app.evaluate(p=>getApp().__queueSave===p,state.collage.path),'album callback')
  assert.deepEqual(await app.evaluate(()=>[getApp().__queueShare,getApp().__queueSave]),[state.collage.path,state.collage.path])
  await (await modal.$('.selected-results-collage')).tap();await pause(200);assert.equal((await modalState()).collage,null)
  await (await modal.$('.selected-results-collage')).tap();await pause(200);assert.equal((await modalState()).collage.path,state.collage.path)
  await (await modal.$('.ui-close')).tap();await waitFor(()=>app.evaluate(p=>{try{wx.getFileSystemManager().accessSync(p);return false}catch(_){return true}},state.collage.path),'temporary collage cleanup')
  // All-still selection takes the same high-resolution JPEG path as one-click.
  await (await page.$('.selection-all')).tap();await cards[2].tap()
  await app.evaluate(paths=>{const service=require('services/studioService.js');service.guestResults=()=>paths.map((p,i)=>({id:'static-'+i,local:true,kind:'manual',localPath:p,status:'completed',created_at:Date.now()/1000-i}))},[paths[2],paths[2]])
  await app.reLaunch('/pages/queue/index');await waitFor(async()=>!!await (await app.currentPage()).$('.selection-toggle'),'static queue')
  const stillPage=await app.currentPage();await (await stillPage.$('.selection-toggle')).tap();await waitFor(async()=>!!await stillPage.$('.selection-all'),'static selection bar');await (await stillPage.$('.selection-all')).tap();await waitFor(async()=>/已选 2/.test(await (await stillPage.$('.selection-bar')).text()),'static selected count');await (await stillPage.$('.make-collage')).tap()
  await waitFor(async()=>{const s=await modalState();return s?.show&&!s.busy&&(s.collage||s.error)},'static collage')
  const still=await modalState();assert.equal(still.error,'');assert.equal(still.collage.animated,false);assert.equal(still.collage.width,688)
  await app.screenshot({path:path.join(output,'queue-static-preview.png')})
  const report={status:'passed',sdkVersion:await app.evaluate(()=>wx.getSystemInfoSync().SDKVersion),selected:3,mixedStaticAndGif:true,selectionOrder:true,incompleteJobRefused:true,frames:reader.numFrames(),durationMs:state.collage.duration,bytes:bytes.length,realCanvasAndFilesystem:true,actualQueueTaps:true,shareAndAlbum:'mocked',staticJpegWidth:still.collage.width,cachedReuse:true,cleanup:true,runtimeErrors:errors}
  fs.writeFileSync(path.join(output,'report.json'),JSON.stringify(report,null,2)+'\n');console.log('PASS native queue collage',JSON.stringify(report));console.log('Evidence:',output)
 }catch(error){await app.screenshot({path:path.join(output,'failure.png')}).catch(()=>{});console.error('Queue data:',JSON.stringify(await (await app.currentPage()).data()).slice(0,2500));throw error
 }finally{
  await app.reLaunch('/pages/index/index').catch(()=>{})
  for(const method of mocked)await app.restoreWxMethod(method).catch(()=>{})
  await app.evaluate(paths=>{for(const p of paths)try{wx.getFileSystemManager().unlinkSync(p)}catch(_){};const original=getApp().__queueOriginals;if(original)Object.assign(require('services/studioService.js'),original);delete getApp().__queueOriginals;delete getApp().__queueShare;delete getApp().__queueSave},created).catch(()=>{})
  await app.disconnect();require('node:child_process').spawnSync('/Applications/wechatwebdevtools.app/Contents/MacOS/cli',['close','--project',project],{timeout:10000})
 }
}
const watchdog=setTimeout(()=>{console.error('Queue collage verification timed out');process.exit(1)},180000);watchdog.unref()
verify().catch(e=>{console.error(e);process.exitCode=1}).finally(()=>clearTimeout(watchdog))
