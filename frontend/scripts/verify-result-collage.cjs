// Exercise the production page and real WeChat canvas/filesystem. Only the
// input download and outbound share/album APIs are mocked; no photos are sent.
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path')
const crypto=require('node:crypto')
const net=require('node:net')
const automator=require('miniprogram-automator'),{GifReader,GifWriter}=require('omggif')
const args=process.argv.slice(2),options={}
for(let i=0;i<args.length;i+=2){
  if(!['--project','--output-dir','--fixtures-json'].includes(args[i])||!args[i+1])throw Error('Usage: node scripts/verify-result-collage.cjs [--project path] [--output-dir path] [--fixtures-json path]')
  options[args[i].slice(2)]=path.resolve(args[i+1])
}
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms))
function fixture(color,delay){
  const bytes=new Uint8Array(20000),writer=new GifWriter(bytes,64,64,{palette:[0xfffaf4,color,0x283c44,0xffffff],loop:0})
  for(let frame=0;frame<6;frame++){
    const pixels=new Uint8Array(64*64)
    for(let y=12;y<52;y++)for(let x=8+frame*3;x<28+frame*3;x++)pixels[y*64+x]=1
    writer.addFrame(0,0,64,64,pixels,{delay})
  }
  return Buffer.from(bytes.subarray(0,writer.end()))
}
async function verify(){
  const output=options['output-dir']||fs.mkdtempSync(path.join(os.tmpdir(),'gensticker-collage-proof-'))
  fs.mkdirSync(output,{recursive:true})
  let project=options.project||path.resolve(__dirname,'../dist/build/mp-weixin')
  let buildMarker=''
  const buildFingerprint=crypto.createHash('sha256').update(fs.readFileSync(path.join(project,'services/resultCollage.js'))).digest('hex')
  if(!options.project){
    const copy=fs.mkdtempSync(path.join(os.tmpdir(),'gensticker-collage-project-'))
    fs.cpSync(project,copy,{recursive:true,filter:file=>path.basename(file)!=='project.private.config.json'})
    project=copy
    const configPath=path.join(project,'project.config.json'),config=JSON.parse(fs.readFileSync(configPath,'utf8'))
    config.projectname='GenSticker-GIF-'+path.basename(project).split('-').pop()
    fs.writeFileSync(configPath,JSON.stringify(config,null,2)+'\n')
    buildMarker=crypto.randomUUID()
    // A copied project can still be compiling when its automation socket opens.
    // Gate all fixtures on this copy's App startup, not a previous webview.
    fs.appendFileSync(path.join(project,'app.js'),'\nsetTimeout(function(){getApp().__genstickerCollageBuild='+JSON.stringify(buildMarker)+'},0);\n')
  }
  const files=options['fixtures-json']?JSON.parse(fs.readFileSync(options['fixtures-json'],'utf8')).map(file=>fs.readFileSync(file)):
    [fixture(0xf37557,10),fixture(0x82b79b,20)]
  assert.ok(files.length>1&&files.length<=9)
  const fixtures=files.map((bytes,index)=>({index,base64:bytes.toString('base64'),animated:bytes.subarray(0,3).toString()==='GIF'&&new GifReader(bytes).numFrames()>1}))
  const expectedDuration=Math.max(...files.map(bytes=>{
    if(bytes.subarray(0,3).toString()!=='GIF')return 0
    const reader=new GifReader(bytes)
    return reader.numFrames()===1?0:Array.from({length:reader.numFrames()},(_,i)=>{const delay=reader.frameInfo(i).delay;return delay<2?100:delay*10}).reduce((a,b)=>a+b,0)
  }))
  // On macOS an IPv6 port check can miss an existing IPv4 automation server.
  // Allocate explicitly on IPv4 so a run cannot attach to an older project.
  const port=await new Promise((resolve,reject)=>{const server=net.createServer();server.once('error',reject);server.listen(0,'127.0.0.1',()=>{const port=server.address().port;server.close(()=>resolve(port))})})
  console.log('Testing build:',buildFingerprint.slice(0,12),'automation port:',port)
  const app=await automator.launch({projectPath:project,port,cliPath:process.env.WECHAT_DEVTOOLS_CLI_PATH||'/Applications/wechatwebdevtools.app/Contents/MacOS/cli',timeout:60000})
  const errors=[],mocked=[],created=[]
  app.on('exception',error=>errors.push(String(error.message||error)))
  async function waitFor(check,description,timeout=30000){
    const end=Date.now()+timeout
    do{assert.deepEqual(errors,[],'WeChat runtime exception');if(await check())return;await pause(200)}while(Date.now()<end)
    throw Error('Timed out: '+description)
  }
  try{
    await waitFor(()=>app.evaluate(marker=>!!getCurrentPages().slice(-1)[0]?.$vm&&(!marker||getApp().__genstickerCollageBuild===marker),buildMarker),'current build startup',60000)
    await app.reLaunch('/pages/recommend/index')
    await waitFor(()=>app.evaluate(()=>getCurrentPages().slice(-1)[0]?.route==='pages/recommend/index'&&!!getCurrentPages().slice(-1)[0]?.$vm),'recommend page')
    await app.evaluate(()=>{
      const service=require('services/resultCollage.js'),run=service.createResultCollage
      getApp().__collageSmokeRun=run
      service.createResultCollage=async function(...args){
        try{return await run(...args)}catch(error){getApp().__collageSmokeError={message:error?.message,errMsg:error?.errMsg,description:String(error)};throw error}
      }
    })
    const paths=await app.evaluate(items=>{const copies=new Map();return items.map(item=>{
      // Repeated fixtures share an original file, just as real downloaded
      // originals stay outside the persistent output directory's quota.
      if(copies.has(item.base64))return copies.get(item.base64)
      const file=wx.env.USER_DATA_PATH+'/gensticker_edit_collage_fixture_'+Date.now()+'_'+item.index+(item.animated?'.gif':'.png')
      wx.getFileSystemManager().writeFileSync(file,item.base64,'base64');copies.set(item.base64,file);return file
    })},fixtures)
    created.push(...new Set(paths))
    await app.mockWxMethod('downloadFile',function(options,paths){
      const match=options.url.match(/\/recommend\/jobs\/collage-local-fixture\/results\/(\d+)$/)
      // Background model/catalog downloads must never receive a photo fixture:
      // their checksum-failure cleanup would delete that supposed download.
      return match?{statusCode:200,tempFilePath:paths[Number(match[1])]}:{statusCode:503,tempFilePath:''}
    },paths);mocked.push('downloadFile')
    await app.mockWxMethod('showShareImageMenu',function(options){getApp().__collageSmokeShare=options.path;return {errMsg:'showShareImageMenu:ok'}});mocked.push('showShareImageMenu')
    await app.mockWxMethod('saveImageToPhotosAlbum',function(options){getApp().__collageSmokeSave=options.filePath;return {errMsg:'saveImageToPhotosAlbum:ok'}});mocked.push('saveImageToPhotosAlbum')
    await app.evaluate(async items=>{
      const vm=getCurrentPages().slice(-1)[0].$vm
      vm.activeId='collage-local-fixture';vm.job={status:'completed',results:items.map(item=>({slot:item.index,animated:item.animated})),reroll_available:true}
      vm.previews=Object.fromEntries(items.map(item=>[item.index,item.path]));vm.selected=items.map(item=>item.index)
      await vm.shareSelected()
    },fixtures.map((fixture,index)=>({...fixture,base64:undefined,path:paths[index]})))
    const originals=await app.evaluate(()=>getCurrentPages().slice(-1)[0].$vm.shareItems.map(item=>item.path))
    assert.deepEqual(originals,paths,'native downloads use every selected original in order')
    await pause(400)
    await app.screenshot({path:path.join(output,'selected-originals.png')})
    // uni-app exposes the component path as a tag to the automation SDK.
    const page=await app.currentPage(),modal=await page.$('components\\/SelectedResultsModal')
    assert.ok(modal,'selected results component is mounted')
    const button=await modal.$('.selected-results-collage')
    assert.match(await button.text(),/动态 GIF/)
    const started=Date.now();await button.tap()
    await waitFor(()=>app.evaluate(()=>{const vm=getCurrentPages().slice(-1)[0].$vm;return !vm.preparingCollage&&(vm.showCollage||!!vm.shareError)}),'animated collage export',90000)
    const result=await app.evaluate(()=>{const vm=getCurrentPages().slice(-1)[0].$vm;return {collage:vm.collage,error:vm.shareError,show:vm.showCollage,diagnostic:getApp().__collageSmokeError}})
    assert.equal(result.error,'',JSON.stringify(result.diagnostic));assert.equal(result.show,true);assert.equal(result.collage.animated,true)
    assert.equal(result.collage.duration,expectedDuration);assert.match(result.collage.path,/\.gif$/)
    const base64=await app.evaluate(file=>wx.getFileSystemManager().readFileSync(file,'base64'),result.collage.path)
    const bytes=Buffer.from(base64,'base64'),reader=new GifReader(bytes)
    assert.ok(reader.numFrames()>1);assert.ok(bytes.length<=2*1024*1024);assert.equal(reader.loopCount(),0)
    const duration=Array.from({length:reader.numFrames()},(_,index)=>reader.frameInfo(index).delay*10).reduce((a,b)=>a+b,0)
    assert.equal(duration,expectedDuration)
    fs.writeFileSync(path.join(output,'collage.gif'),bytes)
    await app.screenshot({path:path.join(output,'animated-preview.png')})
    await pause(350);await app.screenshot({path:path.join(output,'animated-preview-later.png')})
    const share=await modal.$('.selected-results-actions .ui-secondary'),save=await modal.$('.selected-results-actions .ui-primary')
    await share.tap();await save.tap()
    await waitFor(()=>app.evaluate(file=>getApp().__collageSmokeSave===file&&!getCurrentPages().slice(-1)[0].$vm.saving,result.collage.path),'save callback')
    assert.deepEqual(await app.evaluate(()=>[getApp().__collageSmokeShare,getApp().__collageSmokeSave]),[result.collage.path,result.collage.path],'share and album receive the real GIF file')
    await (await modal.$('.selected-results-collage')).tap()
    await waitFor(()=>app.evaluate(()=>!getCurrentPages().slice(-1)[0].$vm.showCollage),'return to selected originals')
    await (await modal.$('.selected-results-collage')).tap()
    await waitFor(()=>app.evaluate(()=>getCurrentPages().slice(-1)[0].$vm.showCollage),'cached collage preview')
    assert.equal(await app.evaluate(()=>getCurrentPages().slice(-1)[0].$vm.collage.path),result.collage.path,'return to cached GIF without rendering again')
    await app.evaluate(()=>getCurrentPages().slice(-1)[0].$vm.closeShare())
    await waitFor(()=>app.evaluate(file=>{try{wx.getFileSystemManager().accessSync(file);return false}catch(_){return true}},result.collage.path),'temporary GIF cleanup')
    const report={status:'passed',buildFingerprint,loadedBuildVerified:!!buildMarker,sdkVersion:await app.evaluate(()=>wx.getSystemInfoSync().SDKVersion),selected:files.length,frames:reader.numFrames(),durationMs:duration,width:reader.width,height:reader.height,bytes:bytes.length,elapsedMs:Date.now()-started,realCanvasAndFilesystem:true,shareAndAlbum:'mocked to avoid sending or saving test content',originalOrder:true,preview:true,cachedReuse:true,cleanup:true,runtimeErrors:errors}
    fs.writeFileSync(path.join(output,'report.json'),JSON.stringify(report,null,2)+'\n')
    console.log('PASS native animated collage:',JSON.stringify(report));console.log('Evidence:',output)
  }finally{
    await app.evaluate(()=>{const vm=getCurrentPages().slice(-1)[0]?.$vm;vm?.closeShare?.()}).catch(()=>{})
    for(const method of mocked)await app.restoreWxMethod(method).catch(()=>{})
    await app.evaluate(paths=>{for(const file of paths)try{wx.getFileSystemManager().unlinkSync(file)}catch(_){};if(getApp().__collageSmokeRun)require('services/resultCollage.js').createResultCollage=getApp().__collageSmokeRun;delete getApp().__collageSmokeRun;delete getApp().__collageSmokeError;delete getApp().__collageSmokeShare;delete getApp().__collageSmokeSave},created).catch(()=>{})
    await app.disconnect()
    if(!options.project){
      const closed=require('node:child_process').spawnSync(process.env.WECHAT_DEVTOOLS_CLI_PATH||'/Applications/wechatwebdevtools.app/Contents/MacOS/cli',['close','--project',project],{encoding:'utf8',timeout:10000})
      if(closed.status!==0)console.warn('Close the completed test project when convenient:',project)
    }
  }
}
const watchdog=setTimeout(()=>{console.error('Animated collage verification timed out');process.exit(1)},180000);watchdog.unref()
verify().catch(error=>{console.error(error);process.exitCode=1}).finally(()=>clearTimeout(watchdog))
