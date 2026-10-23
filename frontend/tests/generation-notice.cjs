const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path'),{ref}=require('vue')
let time=100000,owner='alice',next=0,pages=[],navigations=[],events=[];const timers=new Map()
const c={ref,Date:{now:()=>time},setTimeout:(fn,ms)=>{const id=++next;timers.set(id,{fn,at:time+ms});return id},clearTimeout:id=>timers.delete(id),getCurrentPages:()=>pages,uni:{getStorageSync:()=>({profile:{id:owner},access_token:owner}),navigateTo:o=>navigations.push(o),navigateBack:o=>navigations.push(o),$emit:event=>events.push(event)}}
vm.createContext(c);vm.runInContext(fs.readFileSync(path.join(__dirname,'../src/services/generationNotice.js'),'utf8').replace(/^import .*$/gm,'').replace(/export /g,'')+'\nthis.notice=generationNotice;this.visible=generationNoticeVisible;this.currentOwner=noticeIdentity',c)
function advance(ms){time+=ms;for(const [id,timer] of [...timers])if(timer.at<=time){timers.delete(id);timer.fn()}}
c.notifyGeneration({item:{id:'cloud-job',kind:'manual',status:'completed'},image:'/private-result'});assert.equal(c.visible.value,true)
advance(4199);assert.equal(c.visible.value,true);advance(1);assert.equal(c.visible.value,false);assert.ok(c.notice.value,'fade keeps the notice mounted');advance(800);assert.equal(c.notice.value,null,'total lifetime is five seconds')
c.notifyGeneration({item:{id:'second',kind:'manual',status:'completed'}});advance(1000);c.notifyGeneration({recommendId:'batch'});advance(3200);assert.equal(c.visible.value,true,'an older timer cannot hide a newer notice')
pages=[{route:'pages/index/index'},{route:'pages/recommend/index'},{route:'pages/my/index'}];c.openGenerationNotice();assert.equal(navigations.at(-1).delta,1);assert.equal(c.takeCompletedResult('studio'),null);assert.equal(c.takeCompletedResult('recommend').recommendId,'batch');assert.equal(c.takeCompletedResult('recommend'),null)
c.notifyGeneration({item:{id:'third',status:'completed'}});const previous=c.currentOwner();owner='bob';c.openGenerationNotice();assert.equal(c.notice.value,null);assert.equal(c.takeCompletedResult('studio'),null)
c.notifyGeneration({item:{id:'stale'},owner:previous});assert.equal(c.notice.value,null,'late completion cannot cross accounts')
pages=[{route:'pages/queue/index'}];c.notifyGeneration({item:{id:'fresh',status:'completed'}});c.openGenerationNotice();assert.equal(events.at(-1),'gensticker:open-result');assert.equal(c.takeCompletedResult('studio').item.id,'fresh')
console.log('PASS five-second notice/fade, timer replacement, direct result handoff, existing-page navigation and account isolation')
