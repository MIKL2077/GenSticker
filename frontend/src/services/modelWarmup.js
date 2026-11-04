import {trimOwnedFiles} from '@/services/ownedFiles'
import {isBackgroundIdle,onBackgroundActivity,setBackgroundVisible} from '@/services/backgroundActivity'
let timer=null,enabled=false,running=false,lastCleanup=0
function schedule(){
 clearTimeout(timer);timer=null
 if(!enabled||running||!isBackgroundIdle())return
 timer=setTimeout(async()=>{
  timer=null;if(!enabled||!isBackgroundIdle())return;running=true
  try{
   if(Date.now()-lastCleanup>30000){await trimOwnedFiles({canContinue:isBackgroundIdle});lastCleanup=Date.now()}
  }catch(_){}finally{running=false}
 },10000)
}
onBackgroundActivity(schedule)
export function startIdleMaintenance(){enabled=true;setBackgroundVisible(true);schedule()}
export function stopIdleMaintenance(){enabled=false;clearTimeout(timer);timer=null;setBackgroundVisible(false)}
