import {warmLocalBackground} from '@/services/localBackground'
import {trimOwnedFiles} from '@/services/ownedFiles'
import {isBackgroundIdle,onBackgroundActivity,setBackgroundVisible} from '@/services/backgroundActivity'
let timer=null,enabled=false,running=false,lastWarm=0,lastCleanup=0
function schedule(){
 clearTimeout(timer);timer=null
 if(!enabled||running||!isBackgroundIdle())return
 timer=setTimeout(async()=>{
  timer=null;if(!enabled||!isBackgroundIdle())return;running=true
  let deferred=false
  try{
   if(Date.now()-lastCleanup>30000){await trimOwnedFiles({canContinue:isBackgroundIdle});lastCleanup=Date.now()}
   if(!isBackgroundIdle())return
   if(Date.now()-lastWarm>45000){await warmLocalBackground({canStart:isBackgroundIdle});lastWarm=Date.now()}
  }catch(error){deferred=error.code==='WARMUP_DEFERRED'}finally{running=false;if(deferred&&isBackgroundIdle())schedule()}
 },1500)
}
onBackgroundActivity(schedule)
export function startIdleMaintenance(){enabled=true;setBackgroundVisible(true);schedule()}
export function stopIdleMaintenance(){enabled=false;clearTimeout(timer);timer=null;setBackgroundVisible(false)}
