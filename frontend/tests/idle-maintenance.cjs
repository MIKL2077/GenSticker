const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path')
let time=100000,next=0,warms=0,cleanups=0;const timers=new Map()
const c={Date:{now:()=>time},setTimeout:(fn,ms)=>{const id=++next;timers.set(id,{fn,at:time+ms});return id},clearTimeout:id=>timers.delete(id),warmLocalBackground:async({canStart})=>{assert.equal(canStart(),true);warms++},trimOwnedFiles:async()=>cleanups++}
vm.createContext(c)
for(const file of ['backgroundActivity','modelWarmup'])vm.runInContext(fs.readFileSync(path.join(__dirname,'../src/services/'+file+'.js'),'utf8').replace(/^import .*$/gm,'').replace(/export /g,''),c)
async function advance(ms){time+=ms;for(const [id,timer] of [...timers])if(timer.at<=time){timers.delete(id);await timer.fn()}}
;(async()=>{
 c.startIdleMaintenance();await advance(1000);assert.equal(warms,0,'first render has no model work')
 const resume=c.holdBackgroundWork();await advance(5000);assert.equal(warms,0,'album/editor interaction cancels pending prewarm')
 resume();await advance(1499);assert.equal(warms,0);await advance(1);assert.equal(warms,1);assert.equal(cleanups,1)
 c.stopIdleMaintenance();time+=100000;await advance(2000);assert.equal(warms,1,'hidden application does no prewarm')
 c.startIdleMaintenance();await advance(1500);assert.equal(warms,2)
 console.log('PASS idle startup warmup, interaction deferral, quiet-period delay, foreground resumption and hidden-app suspension')
})().catch(error=>{console.error(error);process.exitCode=1})
