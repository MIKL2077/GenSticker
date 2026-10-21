const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os'),automator=require('miniprogram-automator')
const output=path.resolve(process.argv[2]||fs.mkdtempSync(path.join(os.tmpdir(),'gensticker-search-evidence-'))),pause=ms=>new Promise(r=>setTimeout(r,ms))
async function main(){
 const build=path.resolve(__dirname,'../dist/build/mp-weixin'),project=fs.mkdtempSync(path.join(os.tmpdir(),'gensticker-search-check-'))
 fs.cpSync(build,project,{recursive:true,filter:p=>path.basename(p)!=='project.private.config.json'})
 const config=JSON.parse(fs.readFileSync(path.join(project,'project.config.json')));assert.equal(config.setting.urlCheck,true);config.projectname='GenSticker-search-'+path.basename(project).split('-').at(-1);fs.writeFileSync(path.join(project,'project.config.json'),JSON.stringify(config,null,2));fs.mkdirSync(output,{recursive:true})
 const app=await automator.launch({port:10000+Math.floor(Math.random()*30000),projectPath:project,cliPath:'/Applications/wechatwebdevtools.app/Contents/MacOS/cli',timeout:60000}),errors=[],report={status:'running',project,checks:[]};app.on('exception',e=>errors.push(String(e.message||e)))
 async function wait(fn,label){const end=Date.now()+60000;do{assert.deepEqual(errors,[]);if(await fn())return;await pause(200)}while(Date.now()<end);throw Error('Timed out: '+label)}
 try{
  await wait(async()=>{try{return !!await app.currentPage()}catch(_){return false}},'initial page');await app.reLaunch('/pages/index/index')
  await wait(()=>app.evaluate(()=>getCurrentPages().at(-1)?.$vm?.searchResultCount>0),'catalog')
  const home=await app.currentPage(),input=await home.$('.template-search-input');assert.ok(input)
  const total=await app.evaluate(()=>getCurrentPages().at(-1).$vm.searchResultCount);await input.input('猫')
  await wait(()=>app.evaluate(()=>getCurrentPages().at(-1).$vm.searchQuery==='猫'),'search input')
  const cats=await app.evaluate(()=>({count:getCurrentPages().at(-1).$vm.searchResultCount,page:getCurrentPages().at(-1).$vm.currentPage}));assert.ok(cats.count>0 && cats.count<total);assert.equal(cats.page,1);report.checks.push({name:'native keyword input and pagination reset',total,...cats})
  await app.evaluate(()=>wx.pageScrollTo({selector:'.template-search',duration:0}));await pause(400);await app.screenshot({path:path.join(output,'search.png')})
  await input.input('不存在的模板测试XYZ987');await wait(()=>app.evaluate(()=>getCurrentPages().at(-1).$vm.searchResultCount===0),'empty state');assert.match(await(await home.$('.search-summary')).text(),/没找到/)
  await(await home.$('.search-clear')).tap();await wait(()=>app.evaluate(()=>!getCurrentPages().at(-1).$vm.searchQuery),'clear');assert.equal(await app.evaluate(()=>getCurrentPages().at(-1).$vm.searchResultCount),total);report.checks.push({name:'empty result and native clear button',passed:true})
  if(total>=1000){
   await input.input('猫 动图');await wait(()=>app.evaluate(()=>getCurrentPages().at(-1).$vm.searchQuery==='猫 动图'),'GIF query')
   const gifs=await app.evaluate(()=>{const vm=getCurrentPages().at(-1).$vm;return{count:vm.searchResultCount,allAnimated:vm.currentPageTemplates.every(t=>t.animated)}});assert.ok(gifs.count>0);assert.equal(gifs.allAnimated,true);report.checks.push({name:'live GIF keyword intersection',...gifs})
   await wait(()=>app.evaluate(()=>getCurrentPages().at(-1).$vm.currentPageTemplates.some(t=>!!t.previewImage)),'GIF cover');await pause(500);await app.screenshot({path:path.join(output,'gif-search.png')})
  }
  await app.evaluate(()=>{const vm=getCurrentPages().at(-1).$vm;vm.selectedTemplateDetail={name:'双行及上下独立文字检查',imageCount:'0-0',textCount:'2-2',defaultTexts:['第一行\n第二行','下方独立文字']};vm.textInputs=['第一行\n第二行','下方独立文字'];vm.showTemplateDetail=true})
  let fields;await wait(async()=>{fields=[await home.getElementByXpath('(//textarea)[1]'),await home.getElementByXpath('(//textarea)[2]')];return fields.every(Boolean)},'two textarea slots')
  await fields[0].input('上方第一行\n上方第二行');await fields[1].input('下方第一行\n下方第二行')
  await wait(()=>app.evaluate(()=>getCurrentPages().at(-1).$vm.textInputs[1]==='下方第一行\n下方第二行'),'multiline binding');const texts=await app.evaluate(()=>getCurrentPages().at(-1).$vm.textInputs);assert.deepEqual(texts,['上方第一行\n上方第二行','下方第一行\n下方第二行']);report.checks.push({name:'native multiline entry in both independent slots',values:texts});await app.screenshot({path:path.join(output,'multiline.png')})
  report.status='passed';report.runtimeErrors=errors
 }catch(e){report.status='failed';report.error=e.stack;await app.screenshot({path:path.join(output,'failure.png')}).catch(()=>{});process.exitCode=1;console.error(e)}finally{fs.writeFileSync(path.join(output,'native-search.json'),JSON.stringify(report,null,2)+'\n');await app.disconnect()}
}
main().catch(e=>{console.error(e);process.exitCode=1})
