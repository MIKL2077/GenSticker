const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path'),{reactive,ref,computed,watch,nextTick}=require('vue')
const code=fs.readFileSync(path.join(__dirname,'../src/components/SubjectPicker.vue'),'utf8').split('<script setup>')[1].split('</script>')[0].replace(/^import .*$/gm,'')
const flush=async()=>{await nextTick();await new Promise(resolve=>setImmediate(resolve))}
async function create(initial={}){
 const props=reactive({show:true,src:'/photo',initialRect:null,busy:false,externalError:'',fileType:'jpg',detectEnabled:true,...initial}),events=[],edits=[],disposed=[],detections=[]
 const c={ref,computed,watch,Math,warmLocalBackground:async()=>{},removeImageBackground:async()=>'/cutout.png',defineProps:()=>props,defineEmits:()=>((...args)=>events.push(args)),onBeforeUnmount:fn=>{c.unmount=fn},uni:{getWindowInfo:()=>({windowWidth:375,windowHeight:812}),getImageInfo:o=>o.success({width:200,height:100})},detectSubjects:async path=>{detections.push(path);return {candidates:[{id:'one',kind:'person',box:[.2,.1,.4,.7]}]}},editImage:async(path,operation)=>{edits.push(operation);return '/selected.png'},disposeEditedImage:path=>disposed.push(path),clampCrop:rect=>rect}
 vm.createContext(c);vm.runInContext(code+'\nthis.state={rect,selected,chosen,detecting,processing,candidates,workingSrc,history,stage};this.actions={select,manual,confirm,apply,undo,restore}',c);await flush()
 return {c,props,events,edits,disposed,detections}
}
;(async()=>{
 const ai=await create();assert.equal(ai.c.state.candidates.value.length,1);assert.equal(ai.c.state.selected.value,false,'explicit subject selection is still required')
 ai.c.actions.select(ai.c.state.candidates.value[0]);await ai.c.actions.confirm();assert.equal(ai.edits[0].fileType,'jpg');assert.deepEqual(Array.from(ai.events[0][1].rect),[.2,.1,.4,.7])
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
 assert.ok(unified.c.state.stage.value.h<=392,'portrait space leaves room for fixed editing controls')
 console.log('PASS shared AI/template subject selection, explicit confirmation, PNG alpha preservation, transformed-subject reuse and cancellation')
})().catch(error=>{console.error(error);process.exitCode=1})
