const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path'),{reactive,ref,computed,watch,nextTick}=require('vue')
const code=fs.readFileSync(path.join(__dirname,'../src/components/SubjectPicker.vue'),'utf8').split('<script setup>')[1].split('</script>')[0].replace(/^import .*$/gm,'')
const flush=async()=>{await nextTick();await new Promise(resolve=>setImmediate(resolve))}
async function create(initial={}){
 const props=reactive({show:true,src:'/photo',initialRect:null,busy:false,externalError:'',fileType:'jpg',detectEnabled:true,...initial}),events=[],edits=[],disposed=[],detections=[]
 const c={displayImageSize:info=>/^(left|right)(-mirrored)?$/.test(info.orientation||'')?{...info,width:info.height,height:info.width}:info,imageEditError:e=>Error(e.errMsg||e.message),ref,computed,watch,Math,warmLocalBackground:async()=>{},removeImageBackground:async()=>'/cutout.png',defineProps:()=>props,defineEmits:()=>((...args)=>events.push(args)),onBeforeUnmount:fn=>{c.unmount=fn},uni:{getWindowInfo:()=>({windowWidth:375,windowHeight:812}),getImageInfo:o=>o.success({width:200,height:100})},detectSubjects:async path=>{detections.push(path);return {candidates:[{id:'one',kind:'person',box:[.2,.1,.4,.7]}]}},editImage:async(path,operation)=>{edits.push(operation);return '/selected.png'},disposeEditedImage:path=>disposed.push(path),clampCrop:rect=>rect}
 vm.createContext(c);vm.runInContext(code+'\nthis.state={rect,selected,chosen,detecting,processing,candidates,workingSrc,history,stage,error,message};this.actions={retryDetection,select,manual,confirm,apply,undo,restore}',c);await flush()
 return {c,props,events,edits,disposed,detections}
}
;(async()=>{
 const ai=await create();assert.equal(ai.c.state.candidates.value.length,1);assert.equal(ai.c.state.selected.value,false,'explicit subject selection is still required')
 ai.c.actions.select(ai.c.state.candidates.value[0]);await ai.c.actions.confirm();assert.equal(ai.edits[0].fileType,'jpg');assert.deepEqual(Array.from(ai.events[0][1].rect),[.2,.1,.4,.7])
 const oriented=await create({show:false,editable:true});oriented.c.uni.getImageInfo=o=>o.success({width:800,height:480,orientation:'right'});oriented.props.show=true;await flush();assert.ok(Math.abs(oriented.c.state.stage.value.w/oriented.c.state.stage.value.h-.6)<1e-10,'EXIF portrait stage matches upright pixels')
 oriented.c.detectSubjects=async()=>{throw {errMsg:'uploadFile:fail timeout'}};await oriented.c.actions.retryDetection();assert.match(oriented.c.state.message.value,/timeout/,'retry failures are visible without blocking manual selection')
 oriented.c.editImage=async()=>{throw {errMsg:'canvasToTempFilePath:fail'}};await oriented.c.actions.apply('flip');assert.match(oriented.c.state.error.value,/canvasToTempFilePath/);assert.equal(oriented.c.state.workingSrc.value,'/photo')
 const editor=await create({initialRect:[0,0,1,1],detectEnabled:false,fileType:'png'});assert.equal(editor.detections.length,0,'already transformed subject does not trigger another face scan');await editor.c.actions.confirm();assert.equal(editor.edits[0].fileType,'png','transparent cutouts survive confirmation')
 editor.props.busy=true;const count=editor.events.length;await editor.c.actions.confirm();editor.c.actions.manual();assert.equal(editor.events.length,count,'processing blocks conflicting edits')
 editor.props.busy=false;let finish;editor.c.editImage=()=>new Promise(resolve=>finish=resolve);const pending=editor.c.actions.confirm();editor.props.show=false;await flush();finish('/late.png');await pending;assert.ok(editor.disposed.includes('/late.png'));assert.equal(editor.events.length,count,'closing the picker discards late crop output')
 const unified=await create({editable:true,fileType:'jpg'})
 unified.c.actions.select(unified.c.state.candidates.value[0]);await unified.c.actions.apply('background')
 assert.equal(unified.c.state.workingSrc.value,'/cutout.png');assert.equal(unified.c.state.candidates.value.length,1,'editing retains original candidate choices')
 assert.equal(unified.events.length,0,'editing and preview do not prematurely submit or open another screen')
 unified.c.actions.select(unified.c.state.candidates.value[0]);assert.equal(unified.c.state.workingSrc.value,'/photo','switching people returns to original coordinates')
 unified.c.actions.undo();assert.equal(unified.c.state.workingSrc.value,'/cutout.png','undo restores the edited preview in the same sheet')
 await unified.c.actions.confirm();assert.equal(unified.events[0][0],'confirm');assert.equal(unified.edits.at(-1).fileType,'png')
 unified.c.unmount();assert.ok(unified.disposed.includes('/cutout.png'),'temporary edits are released after the final copy is transferred')
 const canceled=await create({editable:true});let oldFinish,newFinish
 canceled.c.removeImageBackground=()=>new Promise(resolve=>oldFinish=resolve)
 const oldEdit=canceled.c.actions.apply('background');canceled.props.show=false;await flush()
 assert.equal(canceled.c.state.processing.value,false,'closing unlocks the sheet immediately')
 canceled.props.show=true;await flush();canceled.c.editImage=()=>new Promise(resolve=>newFinish=resolve)
 const newEdit=canceled.c.actions.apply('flip');assert.equal(canceled.c.state.processing.value,true)
 oldFinish('/old-background.png');await oldEdit
 assert.equal(canceled.c.state.processing.value,true,'a canceled result cannot unlock a newer edit')
 assert.ok(canceled.disposed.includes('/old-background.png'))
 newFinish('/new-flip.png');await newEdit;assert.equal(canceled.c.state.workingSrc.value,'/new-flip.png')
 assert.ok(unified.c.state.stage.value.h<=392,'portrait space leaves room for fixed editing controls')
 console.log('PASS shared AI/template subject selection, explicit confirmation, PNG alpha preservation, transformed-subject reuse and cancellation')
})().catch(error=>{console.error(error);process.exitCode=1})
