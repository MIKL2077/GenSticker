const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os'),automator=require('miniprogram-automator')
const output=path.resolve(process.argv[2]||fs.mkdtempSync(path.join(os.tmpdir(),'gensticker-editor-check-'))),build=path.resolve(__dirname,'../dist/build/mp-weixin')
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms))
async function main(){
 const project=fs.mkdtempSync(path.join(os.tmpdir(),'gensticker-editor-project-'));fs.cpSync(build,project,{recursive:true,filter:file=>path.basename(file)!=='project.private.config.json'})
 const config=JSON.parse(fs.readFileSync(path.join(project,'project.config.json'),'utf8'));assert.equal(config.setting.urlCheck,true);config.projectname='GenSticker-editor-'+path.basename(project).split('-').at(-1);fs.writeFileSync(path.join(project,'project.config.json'),JSON.stringify(config,null,2)+'\n');fs.mkdirSync(output,{recursive:true})
 const app=await automator.launch({projectPath:project,cliPath:process.env.WECHAT_DEVTOOLS_CLI_PATH || '/Applications/wechatwebdevtools.app/Contents/MacOS/cli',timeout:60000}),errors=[]
 app.on('exception',error=>errors.push(String(error.message||error)))
 // Edits stay in SubjectPicker's preview until the user confirms; the page's
 // submitted image must not be used as the progress signal for flip/rotate.
 const state=()=>app.evaluate(()=>{const vm=getCurrentPages().slice(-1)[0]?.$vm;return vm?{ready:!!vm.currentPageTemplates?.length,detail:vm.showTemplateDetail,editor:vm.showImageEditor,busy:vm.editorBusy,error:vm.editorError,images:vm.templateImages,undo:vm.editorCanUndo}:null})
 async function wait(check,label,timeout=25000){const until=Date.now()+timeout;do{assert.deepEqual(errors,[]);if(await check())return;await pause(150)}while(Date.now()<until);throw Error('Timed out: '+label)}
 try{
  await wait(async()=>{try{return !!await app.currentPage()}catch(_){return false}},'native page')
  await app.reLaunch('/pages/index/index');await wait(async()=>!!(await state())?.ready,'real templates',60000)
  await app.evaluate(async()=>{await getCurrentPages().slice(-1)[0].$vm.onSelectTemplate('always')});await wait(async()=>(await state())?.detail,'template details')
  await app.mockWxMethod('chooseMedia',{tempFiles:[{tempFilePath:'/static/logo-subject.png',fileType:'image',size:10000}]})
  await app.mockWxMethod('chooseImage',{tempFilePaths:['/static/logo-subject.png'],tempFiles:[{path:'/static/logo-subject.png',size:10000}]})
  await app.evaluate(()=>getCurrentPages().slice(-1)[0].$vm.chooseImagesForTemplate());await wait(async()=>(await state())?.editor,'subject editor')
  const home=await app.currentPage()
  const find=className=>home.getElementByXpath('//*[contains(@class,"'+className+'")]')
  const button=(className,index)=>home.getElementByXpath('//*[contains(@class,"'+className+'")]/button['+index+']')
  const preview=async()=>{const image=await home.getElementByXpath('//*[contains(@class,"subject-stage")]/image');return image?.id?await image.attribute('src'):''}
  const unlocked=async()=>{const confirm=await find('subject-confirm');return confirm?.id && (await confirm.property('disabled'))==='false'}
  const manual=async()=>{for(let index=1;index<=15;index++){const item=await button('subject-choices',index);if(!item?.id)break;if((await item.text()).trim()==='手动框选'){await item.tap();return}}throw Error('Manual crop button missing')}
  await wait(async()=>!!(await find('subject-stage'))?.id && await unlocked(),'shared native subject stage')
  await manual()
  await wait(async()=>!!(await find('subject-box'))?.id,'selected subject box')
  const tools=await Promise.all([1,2,3].map(index=>button('editor-tools',index)));assert.ok(tools.every(tool=>tool?.id),'flip, rotate and background tools remain')
  const paths=[]
  async function edit(index){
   const previous=await preview(),tool=await button('editor-tools',index+1)
   await tool.tap()
   await wait(async()=>{
    const problem=await find('subject-error');if(problem?.id && await problem.text())throw Error(await problem.text())
    const src=await preview(),note=await(await find('subject-note')).text()
    return await unlocked() && (index===2?note.includes('预览已更新'):src!==previous)
   },'edit '+index)
   const s=await state();assert.equal(s.images[0],'/static/logo-subject.png','preview edits must wait for explicit confirmation');paths.push(await preview())
  }
  await edit(0);console.log('Native flip preview passed');await edit(1);console.log('Native rotate preview passed');await edit(2);console.log('Native alpha cutout preview passed')
  await app.screenshot({path:path.join(output,'edited-preview.png')})
  const histories=await Promise.all([1,2].map(index=>button('editor-history',index)));await histories[0].tap();await wait(async()=>await preview()===paths[1],'undo restored previous preview')
  await histories[1].tap();await wait(async()=>await preview()==='/static/logo-subject.png','restore upload preview')
  await manual();await (await find('subject-confirm')).tap();await wait(async()=>!(await state()).editor,'subject confirmation')
  const result=await state();assert.ok(result.images[0] && result.images[0]!=='/static/logo-subject.png');assert.equal(result.error,'')
  const report={status:'passed',domainValidation:true,source:'packaged public logo; picker fixture only',sharedSubjectStage:true,tools:['flip','rotate','background'],undo:true,restore:true,pngSubjectConfirmation:true,physicalDeviceInference:false,runtimeErrors:errors}
  fs.writeFileSync(path.join(output,'report.json'),JSON.stringify(report,null,2)+'\n');console.log('PASS native template subject selection, flip, rotate, local alpha cutout, undo, restore and PNG confirmation');console.log('Evidence:',output)
 }finally{await app.restoreWxMethod('chooseImage').catch(()=>{});await app.restoreWxMethod('chooseMedia').catch(()=>{});await app.disconnect()}
}
main().catch(error=>{console.error(error.stack||error);process.exitCode=1})
