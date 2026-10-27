const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path')
const read=file=>fs.readFileSync(path.join(__dirname,'../src',file),'utf8').replace(/^import .*$/gm,'').replace(/export /g,'')
async function verify(){
  const geometryContext={releaseTemporary:()=>{}};vm.createContext(geometryContext);vm.runInContext(read('services/imageEditing.js'),geometryContext)
  vm.runInContext(read('services/imageGeometry.js'),geometryContext)
  for(const orientation of ['left','right','left-mirrored','right-mirrored'])assert.deepEqual(JSON.parse(JSON.stringify(geometryContext.displayImageSize({width:800,height:480,orientation}))),{width:480,height:800,orientation})
  for(const orientation of ['up','down','up-mirrored','down-mirrored'])assert.equal(geometryContext.displayImageSize({width:800,height:480,orientation}).width,800)
  const geometry=geometryContext.cropGeometry
  let crop=geometry(400,200,200,200,1)
  assert.deepEqual(Array.from(crop.rect),[.25,0,.5,1])
  crop=geometry(400,200,200,200,2,10000,-10000)
  assert.deepEqual(Array.from(crop.rect),[0,.5,.25,.5])
  crop=geometry(400,900,120,270,1)
  assert.deepEqual(Array.from(crop.rect),[0,0,1,1],'original portrait aspect keeps every pixel')
  assert.equal(crop.width/crop.height,400/900,'preview geometry never stretches a portrait')
  crop=geometry(400,900,180,180,1)
  assert.equal(crop.width/crop.height,400/900,'square crop preserves source aspect instead of squashing')
  const released=[],callbacks=[],calls=[];let pending,fail=false
  const c={retainFile:()=>()=>{},choosePhotos:o=>callbacks.push(o),ref:value=>({value}),parseRange:s=>{const [min,max]=s.split('-').map(Number);return {min,max}},prepareImages:async()=>[],disposeEditedImage:p=>released.push(p),editImage:async(p,o)=>{calls.push([p,o]);if(fail)throw Error('failed edit');return '/edited-'+calls.length+'.png'},removeImageBackground:()=>new Promise(resolve=>pending=resolve),uni:{chooseImage:o=>callbacks.push(o)}}
  vm.createContext(c);vm.runInContext(read('composables/useTemplateInput.js'),c)
  const input=c.useTemplateInput();input.initializeTemplateInputs({imageCount:'1-2',textCount:'0-0'})
  input.chooseImagesForTemplate();callbacks.pop().success({tempFilePaths:['/original-a.png','/original-b.png']})
  assert.equal(input.showImageEditor.value,true);assert.equal(input.activeImageIndex.value,0)
  await input.applyImageEdit({type:'flip'});assert.equal(input.templateImages.value[0],'/edited-1.png')
  input.openImageEditor(1);assert.equal(input.editorCanUndo.value,false)
  await input.applyImageEdit({type:'rotate'});input.undoImageEdit();assert.equal(input.templateImages.value[1],'/original-b.png')
  input.openImageEditor(0);input.restoreImage();assert.equal(input.templateImages.value[0],'/original-a.png')
  assert.ok(!released.includes('/original-a.png')&&!released.includes('/original-b.png'))
  const beforePrepared=calls.length
  await input.applyImageEdit({type:'prepared',path:'/selected-subject.png',complete:true})
  assert.equal(calls.length,beforePrepared,'confirmed subject must not be cropped a second time')
  assert.equal(input.templateImages.value[0],'/selected-subject.png');assert.equal(input.showImageEditor.value,false)
  input.openImageEditor(0);input.undoImageEdit();assert.equal(input.templateImages.value[0],'/original-a.png')
  const selectionCutout=input.applyImageEdit({type:'background',rect:[.1,.2,.5,.6]})
  await new Promise(resolve=>setImmediate(resolve));assert.equal(calls.at(-1)[1].type,'crop','background removal only receives the selected region')
  const selectedCrop=calls.length;pending('/selection-cutout.png');await selectionCutout
  assert.ok(released.includes('/edited-'+selectedCrop+'.png'),'intermediate selection crop is released')
  input.restoreImage();assert.equal(input.templateImages.value[0],'/original-a.png')
  fail=true;await input.applyImageEdit({type:'flip'});assert.equal(input.templateImages.value[0],'/original-a.png');assert.equal(input.editorError.value,'failed edit')
  const request=input.applyImageEdit({type:'background'});assert.equal(input.isTemplateInputValid(),false)
  input.closeImageEditor();pending('/late-cutout.png');await request
  assert.equal(input.templateImages.value[0],'/original-a.png');assert.ok(released.includes('/late-cutout.png'))
  input.chooseImagesForTemplate(); // Full input must not open a picker.
  input.removeTemplateImage(1);input.chooseImagesForTemplate();const late=callbacks.pop();input.resetInputs();late.success({tempFilePaths:['/late-upload.png']})
  assert.equal(input.templateImages.value.length,0);assert.equal(input.editorBusy.value,false)
  console.log('PASS: crop bounds, independent image undo/restore, failed edit preserves input, canceled processing and late picker cleanup')
}
verify().catch(e=>{console.error(e);process.exitCode=1})
