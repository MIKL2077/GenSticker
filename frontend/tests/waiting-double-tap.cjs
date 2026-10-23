const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path')
let time=1000;const events=[]
const c={UiIcon:{},Date:{now:()=>time},setTimeout:()=>1,clearTimeout:()=>{}}
const source=fs.readFileSync(path.join(__dirname,'../src/components/PreviewModal.vue'),'utf8').split('<script>')[1].split('</script>')[0].replace(/^import .*$/gm,'').replace('export default','this.component=')
vm.createContext(c);vm.runInContext(source,c)
const state={...c.component.data(),show:true,isGenerating:true,$emit:event=>events.push(event)}
for(const [name,method] of Object.entries(c.component.methods))state[name]=method.bind(state)
state.queueTap();assert.equal(events.length,0);assert.equal(state.queueTapHint,true)
time+=300;state.queueTap();assert.deepEqual(events,['close'],'two taps enqueue once')
events.length=0;state.queueTap();time+=800;state.queueTap();assert.equal(events.length,0,'two slow taps never enqueue')
state.resetQueueTap();state.closeAction();assert.equal(events.length,0,'close icon also requires a deliberate double tap while generating')
state.resetQueueTap();state.isGenerating=false;state.queueTap();assert.equal(events.length,0);state.closeAction();assert.deepEqual(events,['close'],'finished previews retain one-tap close')
console.log('PASS first-tap guidance, deliberate double-tap backgrounding, slow taps, reset and completed-preview close')
