let visible=false
const holds=new Set(),listeners=new Set()
const changed=()=>{for(const listener of listeners)listener()}
export const isBackgroundIdle=()=>visible && !holds.size
export function setBackgroundVisible(value){visible=value;changed()}
export function onBackgroundActivity(listener){listeners.add(listener);return()=>listeners.delete(listener)}
export function holdBackgroundWork(){
 const hold={};holds.add(hold);changed();let released=false
 return()=>{if(released)return;released=true;holds.delete(hold);changed()}
}
