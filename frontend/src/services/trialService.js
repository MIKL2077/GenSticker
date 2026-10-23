import {visitorHeaders} from '@/services/popularityService'
import {apiRequest} from '@/services/apiService'

const owner=()=>uni.getStorageSync('gensticker.session.v1')?.profile?.id || 'guest'
const storageKey=()=>`gensticker.trial.used.v1.${owner()}`
export function hasUsedTrial(key){return (uni.getStorageSync(storageKey())||[]).includes(key)}
export function markTrialUsed(key){
 if(!key)return
 const previous=uni.getStorageSync(storageKey())||[]
 uni.setStorageSync(storageKey(),[key,...previous.filter(value=>value!==key)].slice(0,128))
 uni.$emit('gensticker:trial-used',key)
 apiRequest('/templates/trial/use',{method:'POST',data:{key},header:visitorHeaders()},1).catch(()=>{})
}
export async function getCurrentTrial(){return apiRequest('/templates/trial',{timeout:10000,header:visitorHeaders()},1)}
