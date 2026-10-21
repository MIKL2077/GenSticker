const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os'),automator=require('miniprogram-automator')
const fixtures=path.resolve(process.argv[2]||''),output=path.resolve(process.argv[3]||fs.mkdtempSync(path.join(os.tmpdir(),'gensticker-fast-editor-evidence-')))
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms))
async function main(){
 const build=path.resolve(__dirname,'../dist/build/mp-weixin'),project=fs.mkdtempSync(path.join(os.tmpdir(),'gensticker-fast-editor-'))
 fs.cpSync(build,project,{recursive:true,filter:file=>path.basename(file)!=='project.private.config.json'})
 for(const file of ['qa-faces.jpg','qa-rotated.jpg','qa-alpha.png'])fs.copyFileSync(path.join(fixtures,file),path.join(project,'static',file))
 const config=JSON.parse(fs.readFileSync(path.join(project,'project.config.json'),'utf8'));assert.equal(config.setting.urlCheck,true);config.projectname='GenSticker-fast-'+path.basename(project).split('-').at(-1);fs.writeFileSync(path.join(project,'project.config.json'),JSON.stringify(config,null,2))
 fs.mkdirSync(output,{recursive:true})
 const app=await automator.launch({port:10000+Math.floor(Math.random()*30000),projectPath:project,cliPath:process.env.WECHAT_DEVTOOLS_CLI_PATH||'/Applications/wechatwebdevtools.app/Contents/MacOS/cli',timeout:60000}),errors=[]
 app.on('exception',error=>errors.push(String(error.message||error)))
 const report={status:'running',project,scope:'WeChat DevTools native canvas and actual public HTTPS APIs; public OpenCV face fixture, synthetic orientation/alpha fixtures',physicalDeviceInference:false,checks:[]}
 const record=(name,result)=>{report.checks.push({name,...result});console.log(name,JSON.stringify(result))}
 async function wait(check,label,timeout=30000){const end=Date.now()+timeout;do{assert.deepEqual(errors,[]);if(await check())return;await pause(100)}while(Date.now()<end);throw Error('Timed out: '+label)}
 async function job(){await wait(()=>app.evaluate(()=>!!wx.__qaFastResult),'native API result',45000);const result=await app.evaluate(()=>wx.__qaFastResult);assert.ok(!result.error,result.error);return result}
 try{
  await wait(async()=>{try{return !!await app.currentPage()}catch(_){return false}},'initial page')
  await app.reLaunch('/pages/recommend/index');await wait(()=>app.evaluate(()=>!!getCurrentPages().slice(-1)[0]?.$vm?.choose),'AI page')
  await app.evaluate(()=>{wx.__qaSavedSession=wx.getStorageSync('gensticker.session.v1');wx.removeStorageSync('gensticker.session.v1');const vm=getCurrentPages().slice(-1)[0].$vm;vm.photoOriginal='/static/qa-rotated.jpg';vm.subjectRect=null;vm.subjectPicker=true})
  const page=await app.currentPage();let picker;await wait(async()=>{picker=await page.$('.subject-picker-host');return picker && await picker.$('.subject-box')},'immediate crop box');const button=await picker.$('.subject-confirm');assert.ok(button)
  const disabled=await button.attribute('disabled');assert.ok(!disabled || disabled==='false','confirm is usable before network detection completes')
  await app.screenshot({path:path.join(output,'instant-editor.png')});record('AI editor usable without waiting for detection',{confirmEnabled:true})
  await app.evaluate(()=>{getCurrentPages().slice(-1)[0].$vm.subjectPicker=false})
  await app.evaluate(()=>{wx.__qaFastResult=null;(async()=>{
   const service=require('services/subjectSelection.js'),api=require('common/vendor.js').index,original=api.uploadFile;let uploads=0
   api.uploadFile=options=>{uploads++;return original(options)}
   try{const started=Date.now(),first=await service.detectSubjects('/static/qa-faces.jpg',{force:true,withMask:true}),firstMs=Date.now()-started,afterFirst=uploads,t=Date.now(),second=await service.detectSubjects('/static/qa-faces.jpg',{withMask:true});wx.__qaFaces=first;return{method:first.method,candidates:first.candidates.length,firstMs,hasPreview:!!first.preview,cachedMs:Date.now()-t,firstUploads:afterFirst,cachedUploads:uploads-afterFirst,sameCandidates:JSON.stringify(first.candidates)===JSON.stringify(second.candidates)}}finally{api.uploadFile=original}
  })().then(result=>wx.__qaFastResult=result,error=>wx.__qaFastResult={error:error.message||error.errMsg})})
  const faces=await job();assert.ok(faces.candidates>=2);assert.equal(faces.hasPreview,true);assert.equal(faces.cachedUploads,0);assert.equal(faces.sameCandidates,true);record('Real two-person detection and coordinate reuse',faces)
  await app.evaluate(()=>{wx.__qaFastResult=null;(async()=>{
   const api=require('common/vendor.js').index,edit=require('services/imageEditing.js'),upload=api.uploadFile,download=api.downloadFile;let uploads=0,downloads=0,uploadBytes=0,delivery='';let result=''
   api.uploadFile=options=>{uploads++;delivery=options.formData?.delivery;try{uploadBytes=wx.getFileSystemManager().statSync(options.filePath).size}catch(_){}return upload(options)};api.downloadFile=options=>{if(options.url.includes('/images/subject-results/'))downloads++;return download(options)}
   try{const started=Date.now();result=await edit.composeBackgroundMask('/static/qa-faces.jpg',wx.__qaFaces.preview,{rect:wx.__qaFaces.candidates[0].box});const ms=Date.now()-started,info=await api.getImageInfo({src:result}),canvas=wx.createOffscreenCanvas({type:'2d',width:info.width,height:info.height}),img=canvas.createImage();await new Promise((resolve,reject)=>{img.onload=resolve;img.onerror=reject;img.src=result});const ctx=canvas.getContext('2d');ctx.drawImage(img,0,0);const pixels=ctx.getImageData(0,0,canvas.width,canvas.height).data;let minAlpha=255,maxAlpha=0;for(let i=3;i<pixels.length;i+=4){minAlpha=Math.min(minAlpha,pixels[i]);maxAlpha=Math.max(maxAlpha,pixels[i])}canvas.width=canvas.height=1;return{ms,width:info.width,height:info.height,minAlpha,maxAlpha,uploads,downloads,uploadBytes,delivery}}finally{api.uploadFile=upload;api.downloadFile=download;if(result)edit.disposeEditedImage(result)}
  })().then(result=>wx.__qaFastResult=result,error=>wx.__qaFastResult={error:error.message||error.errMsg})})
  const cutout=await job();assert.equal(cutout.uploads,0);assert.equal(cutout.downloads,0);assert.equal(cutout.minAlpha,0);assert.ok(cutout.maxAlpha>=240);record('Detection mask reused on native canvas without another request',cutout)
  await app.evaluate(()=>{wx.__qaFastResult=null;(async()=>{const edit=require('services/imageEditing.js'),api=require('common/vendor.js').index,started=Date.now(),p=await edit.removeImageBackground('/static/qa-alpha.png');try{const info=await api.getImageInfo({src:p});return{ms:Date.now()-started,width:info.width,height:info.height}}finally{edit.disposeEditedImage(p)}})().then(result=>wx.__qaFastResult=result,error=>wx.__qaFastResult={error:error.message||error.errMsg})})
  const alpha=await job();assert.equal(alpha.width,81);assert.equal(alpha.height,121);record('Existing transparency reused locally',alpha)
  await app.reLaunch('/pages/index/index');await wait(()=>app.evaluate(()=>!!getCurrentPages().slice(-1)[0]?.$vm?.currentPageTemplates?.length),'template catalog',60000)
  await app.evaluate(async()=>{await getCurrentPages().slice(-1)[0].$vm.onSelectTemplate('always')})
  await app.mockWxMethod('chooseImage',{tempFilePaths:['/static/qa-alpha.png'],tempFiles:[{path:'/static/qa-alpha.png',size:1000}]})
  await app.evaluate(()=>getCurrentPages().slice(-1)[0].$vm.chooseImagesForTemplate());const home=await app.currentPage();await wait(()=>home.getElementByXpath('//*[contains(@class,"subject-box")]'),'template immediate crop')
  await (await home.getElementByXpath('//*[contains(@class,"subject-confirm")]')).tap();await wait(()=>app.evaluate(()=>!getCurrentPages().slice(-1)[0].$vm.showImageEditor),'template confirmation')
  record('Template editor opens and confirms without detection wait',{passed:true})
  report.status='passed';report.runtimeErrors=errors
 }catch(error){report.status='failed';report.error=error.stack;process.exitCode=1;console.error(error)}finally{
  fs.writeFileSync(path.join(output,'native.json'),JSON.stringify(report,null,2)+'\n')
  await app.evaluate(()=>{if(wx.__qaSavedSession)wx.setStorageSync('gensticker.session.v1',wx.__qaSavedSession);else wx.removeStorageSync('gensticker.session.v1')}).catch(()=>{})
  await app.restoreWxMethod('chooseImage').catch(()=>{});await app.disconnect()
 }
}
main().catch(error=>{console.error(error);process.exitCode=1})
