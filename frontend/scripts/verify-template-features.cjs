// Production build, real downloads/canvas/filesystem; outbound sharing mocked.
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),net=require('node:net')
const automator=require('miniprogram-automator'),{GifReader}=require('omggif')
const output=path.resolve(process.argv[2]||'../../output/template-features-20261103/wechat'),pause=ms=>new Promise(r=>setTimeout(r,ms))
async function main(){
 fs.mkdirSync(output,{recursive:true});const project=fs.mkdtempSync(path.join(os.tmpdir(),'gensticker-template-features-'))
 fs.cpSync(path.resolve(__dirname,'../dist/build/mp-weixin'),project,{recursive:true,filter:f=>path.basename(f)!=='project.private.config.json'})
 const config=JSON.parse(fs.readFileSync(path.join(project,'project.config.json'),'utf8'));config.projectname='GenSticker-features-'+Date.now();fs.writeFileSync(path.join(project,'project.config.json'),JSON.stringify(config))
 const server=net.createServer();await new Promise(r=>server.listen(0,'127.0.0.1',r));const port=server.address().port;await new Promise(r=>server.close(r))
 const app=await automator.launch({projectPath:project,cliPath:'/Applications/wechatwebdevtools.app/Contents/MacOS/cli',port,timeout:60000});console.log('WeChat connected',project)
 const errors=[];app.on('exception',e=>errors.push(e.message||String(e)))
 const until=async(check,label)=>{const end=Date.now()+60000;while(Date.now()<end){assert.deepEqual(errors,[]);try{if(await check())return}catch(e){if(Date.now()>end-500)throw e}await pause(200)}throw Error('Timeout '+label)}
 const state=()=>app.evaluate(()=>{const v=getCurrentPages().slice(-1)[0]?.$vm;return v?{count:v.currentPageTemplates?.length,loading:v.isLoadingTemplates,error:v.loadError,sharing:v.exampleSharing}:null})
 try{
  await until(async()=>!!(await state())?.count,'initial catalog')
  await app.mockWxMethod('showShareImageMenu',function(options){getApp().__exampleShare={path:options.path,bytes:wx.getFileSystemManager().statSync(options.path).size,base64:wx.getFileSystemManager().readFileSync(options.path,'base64')};return {errMsg:'showShareImageMenu:ok'}})
  await app.evaluate(()=>{getApp().__nativeStarts=0;wx.createInferenceSession=()=>{getApp().__nativeStarts++;throw Error('Unexpected UI-thread model compile')};wx.initFaceDetect=()=>{getApp().__nativeStarts++;throw Error('Unexpected UI-thread face engine')};getApp().__gaps=[];let previous=Date.now();getApp().__gapTimer=setInterval(()=>{const now=Date.now();getApp().__gaps.push(now-previous);previous=now},50)})
  await app.reLaunch('/pages/index/index')
  await until(async()=>!!(await state())?.count&&!(await state()).loading,'warm reopen')
  const cases=[]
  for(const key of ['auto_story_17614d3aefdd49fe5dbd7c0a','erised_mirror']){
   await app.evaluate(k=>getCurrentPages().slice(-1)[0].$vm.onSelectTemplate(k),key)
   await until(()=>app.evaluate(()=>getCurrentPages().slice(-1)[0].$vm.showTemplateDetail),'detail')
   const page=await app.currentPage(),modal=await page.$('#template-detail'),button=await modal.$('.example-share');assert.ok(button)
   await app.screenshot({path:path.join(output,key.startsWith('auto_')?'gif-example-button.png':'static-example-button.png')})
   await button.tap()
   await until(()=>app.evaluate(()=>!!getApp().__exampleShare&&!getCurrentPages().slice(-1)[0].$vm.exampleSharing),'example native share callback')
   const result=await app.evaluate(()=>getApp().__exampleShare);const bytes=Buffer.from(result.base64,'base64');delete result.base64
   if(key.startsWith('auto_')){const gif=new GifReader(bytes);assert.ok(gif.numFrames()>1);result.frames=gif.numFrames();result.width=gif.width;result.height=gif.height;fs.writeFileSync(path.join(output,'shared-example.gif'),bytes)}
   else assert.equal(bytes.subarray(0,4).toString('hex'),'89504e47')
   cases.push({key,...result});await app.evaluate(()=>{getApp().__exampleShare=null;getCurrentPages().slice(-1)[0].$vm.closeTemplateDetail()})
  }
  for(const query of ['中文','猫 动图','谢谢','哈喽']){await app.evaluate(q=>getCurrentPages().slice(-1)[0].$vm.setSearchQuery(q),query);await pause(250)}
  await app.evaluate(()=>{const v=getCurrentPages().slice(-1)[0].$vm;v.setSearchQuery('');v.nextPage()});await pause(300);await app.evaluate(()=>getCurrentPages().slice(-1)[0].$vm.prevPage())
  await pause(10500)
  const timing=await app.evaluate(()=>{clearInterval(getApp().__gapTimer);const values=getApp().__gaps.sort((a,b)=>a-b);return {nativeModelInitializations:getApp().__nativeStarts,samples:values.length,maxTimerGapMs:values.at(-1),p95TimerGapMs:values[Math.floor(values.length*.95)]}})
  assert.equal(timing.nativeModelInitializations,0);assert.ok(timing.samples>100);assert.deepEqual(errors,[])
  const report={status:'passed',cases,timing,runtimeErrors:errors,sharing:'native menu mocked; full images downloaded from deployed API',scope:'WeChat simulator; physical-device frame rates still require phone verification'}
  fs.writeFileSync(path.join(output,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report))
 }finally{await app.restoreWxMethod('showShareImageMenu').catch(()=>{});await app.close()}
}
const timer=setTimeout(()=>{console.error('Feature verification timed out');process.exit(1)},180000);timer.unref();main().catch(e=>{console.error(e);process.exitCode=1}).finally(()=>clearTimeout(timer))
