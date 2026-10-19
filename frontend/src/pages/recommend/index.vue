<template>
 <view class="recommend-page" :class="{'has-results':job?.results?.length,'motion-paused':!sceneActive,'scene-enter':sceneActive}">
  <view class="page-header"><button class="back" aria-label="返回" @click="back">‹</button><view><text class="ui-kicker">PHOTO TO STICKERS</text><text class="title">一键为 Ta 造梗</text></view><image class="mini-logo" src="/static/logo.png" mode="aspectFit"/></view>
  <view class="intro-card ui-enter"><view class="intro-copy-block"><text class="ui-kicker">THE STICKER FACTORY</text><text class="intro-title">选一张 Ta，<text class="intro-pop">接住九张损图。</text></text><text class="intro">AI 批量搭配；换一批，继续发现新模板。</text></view><view class="intro-toys"><mood-toy :active="sceneActive" :show-hint="false"/></view></view>
  <view class="steps fx-enter"><text class="step active">01 选照片</text><text class="step-line"/><text class="step" :class="{active:!!job}">02 配表情</text><text class="step-line"/><text class="step" :class="{active:finished && !!job?.results?.length}">03 挑喜欢的</text></view>
  <view v-if="!session" class="login-card fx-enter"><image src="/static/logo.png" mode="aspectFit" class="login-logo"/><text class="login-title">先登录，收好你的小表情</text><text class="login-copy">登录后就能开始，生成记录随时回来查看。</text><button class="ui-primary" :loading="loggingIn" :disabled="loggingIn" @click="login">微信一键登录 →</button><text class="hint">自动填好默认资料，之后随时修改。</text></view>
  <template v-else>
   <view class="quota-row"><text>{{quotaLoading?'正在连接工作室…':quotaReady?(unlimited?'日常使用不限次数，连续操作稍作间隔':'今日剩余 '+quota.remaining+' / '+quota.limit+' 次'):'工作室暂未连接'}}</text><text class="quota-badge">灵感持续供应</text></view>
   <button v-if="quotaError" class="error retry-inline" @click="refresh">{{quotaError}} · 重试 ↗</button>
   <button class="upload-card fx-enter" :disabled="busy" @click="choose"><image v-if="photo" :src="photo" mode="aspectFit" class="photo"/><view v-else class="upload-illustration"><text>☺</text><text>＋</text></view><text class="upload-title">{{photo?'照片准备好了':'选一张喜欢的照片'}}</text><text class="upload-caption">{{photo?'点击更换照片':'从相册选取，或拍一张新的'}}</text></button>
   <button class="ui-primary generate-button" :disabled="busy || retrySeconds>0 || !photo || !quotaReady || !quotaAvailable" :loading="uploading" @click="generate">{{uploading?'正在上传照片':job && !finished?'正在搭配表情…':'为 Ta 生成 9 张损图 ✦'}}</button>
   <text class="hint generation-hint">{{generateHint}}</text><button v-if="quotaReady && !quotaAvailable" class="text-link" @click="goHome">去首页手动制作 ↗</button>
  </template>
  <view v-if="error" class="error"><text>{{error}}</text><button v-if="activeId" class="link" @click="resume">重试获取进度 ↗</button></view>
  <template v-if="session">
   <view v-if="job" class="result-header fx-enter"><view><text class="section-title">{{job.status==='failed'?'这盒暂时没出炉':finished?'你的表情出炉啦':'小情绪，变身中'}}</text><text class="result-status">{{job.message || '正在等待生成'}}{{finished && job.results.length<9 && job.results.length?' · 本次生成'+job.results.length+'张':''}}</text></view><text class="result-count">{{job.results.length}}<text> / 9</text></text></view>
   <view v-if="job && finished" class="batch-bar fx-enter"><view><text class="batch-title">同一张照片，再开一盒</text><text class="batch-caption">{{!rerollSupported?'当前服务器尚未支持换批，请先保存这组结果':job.reroll_available===false?'原图已过期，请重新选一张照片':'优先用新模板 · 上一批在最近生成里'}}</text></view><button class="reroll-button" :disabled="busy || retrySeconds>0 || !quotaReady || !quotaAvailable || !rerollSupported || job.reroll_available===false" :loading="uploading" @click="reroll">{{rerollSupported?'↻ 换一批':'服务待更新'}}</button></view>
   <view v-if="job?.analysis?.warnings?.length" class="hint">{{job.analysis.warnings.filter(t=>!t.includes('真实情绪')).join('；')}}</view>
   <view v-if="job" class="results"><view v-for="slot in resultSlots" :key="slot" class="result" :class="{selected:selected.includes(slot),'fx-enter':!!previews[slot]}" @click="toggle(slot)"><image v-if="previews[slot]" :src="previews[slot]" :data-slot="slot" mode="aspectFit" class="result-image"/><text v-else class="placeholder" :class="{'fx-breathe':!finished}">{{finished?'图片加载中':'✦'}}</text><button v-if="previews[slot]" class="zoom" :aria-label="'放大第'+(slot+1)+'张'" @click.stop="preview(slot)">放大 ↗</button><text class="check" :class="{checked:selected.includes(slot)}">{{selected.includes(slot)?'✓':' '}}</text></view></view>
   <text v-if="finished && !job?.results?.length" class="empty-note">{{job?.status==='failed'?'这次没有完成，可以再换一批，或试试另一张照片。':'这次没有匹配到合适的结果，试试另一张照片吧。'}}</text>
   <view v-if="job?.results?.length" class="actions"><view class="selection-copy"><text>{{saveProgress || '选中了 '+selected.length+' 张小表情'}}</text><button :disabled="saving" @click="selectAll">{{selected.length===job.results.length?'取消全选':'全都要'}}</button></view><button class="ui-primary" :disabled="!selected.length || saving" :loading="saving" @click="save">{{saving?saveProgress:'保存 '+selected.length+' 张到相册 ↓'}}</button><button class="ui-secondary share-selected" :disabled="!selected.length || saving" @click="shareSelected"><ui-icon name="share" tone="accent" :size="30"/> 分享所选原图 / 朋友圈</button></view>
   <view v-if="attributions.length" class="attribution"><text v-for="item in attributions" :key="item.source_url">素材：{{item.author}} · {{item.license}}（来源见图片底部）</text></view>
   <view class="preference fx-enter"><view><text>越选，越懂你</text><text class="preference-copy">根据选择优化推荐，关闭后清除已有偏好。</text></view><switch :checked="quota.personalization" color="#f37557" @change="preference"/></view>
   <view class="history-heading"><text class="section-title">最近生成</text><text class="hint">保存这几天的小情绪</text></view><button v-if="historyError" class="error retry-inline" @click="refresh">{{historyError}}</button><text v-if="!history.length && !historyError" class="empty-history">第一组专属表情，在等你来制作。</text>
   <view v-for="item in visibleHistory" :key="item.job_id" class="history-row fx-enter"><button class="history-open" :disabled="uploading || saving" @click="open(item.job_id)"><view class="history-symbol"><image v-if="historyPreviews[item.job_id]" :src="historyPreviews[item.job_id]" mode="aspectFill"/><ui-icon v-else name="image" :size="40" tone="accent"/></view><view><text>{{formatTime(item.created_at)}}</text><text class="history-meta">{{labels[item.status] || item.status}} · {{item.count}} 张</text></view></button><button class="link delete-link" :disabled="uploading || saving" @click="deleteHistory(item)">删除</button></view>
   <view v-if="historyPages>1" class="history-paging"><button :disabled="historyPage===1" @click="changeHistoryPage(-1)">上一页</button><text>{{historyPage}} / {{historyPages}}</text><button :disabled="historyPage===historyPages" @click="changeHistoryPage(1)">下一页</button></view>
  </template>
  <preview-modal :show="shareSlot!==null" :is-generating="false" :image="shareImage" :allow-edit="false" @close="shareSlot=null" @share="shareCurrent" @save="saveCurrent"/>
  <view class="privacy-note"><text>放心制作，照片只用于本次处理。</text><text>原图24小时后清理，原图缩略图和结果保留7天。</text><text>每次换一批，都会保留上一组结果。</text></view>
  <bottom-tabs active="ai"/>
 </view>
</template>
<script>
import { ref,computed,watch,nextTick,getCurrentInstance } from 'vue'
import { onShow,onHide,onUnload } from '@dcloudio/uni-app'
import { useLibrary } from '@/composables/useLibrary'
import MoodToy from '@/components/MoodToy.vue'
import BottomTabs from '@/components/BottomTabs.vue'
import UiIcon from '@/components/UiIcon.vue'
import PreviewModal from '@/components/PreviewModal.vue'
import {shareOriginalImage} from '@/services/wechatSharing'
import { getQuota,listJobs,getJob,createJob,uploadPhoto,downloadResult,selectResults,removeJob,setPersonalization } from '@/services/recommendService'
export default {
  components: { BottomTabs, MoodToy, UiIcon, PreviewModal },
  setup() {
    const sceneActive=ref(true),historyPage=ref(1),historyPreviews=ref({}),shareSlot=ref(null)
    const historyPages=computed(()=>Math.max(1,Math.ceil(history.value.length/5)))
    const visibleHistory=computed(()=>history.value.slice((historyPage.value-1)*5,historyPage.value*5))
    const historyInflight=new Set()
    const loadHistoryPreviews=async()=>{const owner=session.value?.profile?.id;for(const item of visibleHistory.value){if(!item.source_preview_url || historyPreviews.value[item.job_id] || historyInflight.has(item.job_id))continue;historyInflight.add(item.job_id);downloadResult(item.source_preview_url).then(path=>{if(owner===session.value?.profile?.id)historyPreviews.value[item.job_id]=path}).catch(()=>{}).finally(()=>historyInflight.delete(item.job_id))}}
    const changeHistoryPage=delta=>{historyPage.value=Math.max(1,Math.min(historyPages.value,historyPage.value+delta));loadHistoryPreviews()}
    const shareImage=computed(()=>shareSlot.value===null?'':previews.value[shareSlot.value]||'')
    const account=useLibrary(), {session,loggingIn}=account, quotaLoading=ref(false), quotaReady=ref(false), quotaError=ref(''), historyError=ref(''), savedSlots=ref([]), saveProgress=ref(''), quota=ref({limit:0,remaining:null,unlimited:true,personalization:true}),photo=ref(''),job=ref(null),previews=ref({}),selected=ref([]),error=ref(''),uploading=ref(false),saving=ref(false),history=ref([]),activeId=ref('')
    let timer=null, visible=true, polling=false, failures=0, requestKey='', rerollKey='', generation=0
    const inflight=new Set(), exposed=new Set()
    const instance=getCurrentInstance()
    let observer=null
    const disconnectObserver=()=>{if(observer)observer.disconnect();observer=null}
    const observeVisible=()=>{nextTick(()=>{
      disconnectObserver()
      if(!visible || !activeId.value || !Object.keys(previews.value).length || !uni.createIntersectionObserver)return
      const id=activeId.value
      try {
        observer=uni.createIntersectionObserver(instance.proxy,{observeAll:true,thresholds:[0.5]})
        observer.relativeToViewport().observe('.result-image',event=>{
          const slot=Number(event.dataset?.slot)
          if(quota.value.personalization && id===activeId.value && event.intersectionRatio>=0.5 && Number.isInteger(slot) && !exposed.has(slot)){
            exposed.add(slot);selectResults(id,[slot],'exposure').catch(()=>{})
          }
        })
      }catch(_){disconnectObserver()}
    })}
    watch(previews,observeVisible,{deep:true})
    const activeKey=()=>`gensticker.recommend.active.${session.value?.profile?.id || 'guest'}`
    const unlimited=computed(()=>quota.value.unlimited===true || quota.value.limit===0)
    const rerollSupported=computed(()=>quota.value.features?.reroll===true)
    const quotaAvailable=computed(()=>unlimited.value || quota.value.remaining>0)
    const finished=computed(()=>['completed','failed'].includes(job.value?.status))
    const busy=computed(()=>uploading.value || saving.value || !!job.value && !finished.value)
    const resultSlots=computed(()=>finished.value ? (job.value?.results||[]).map(r=>r.slot) : Array.from({length:9},(_,i)=>i))
    const retryAt=ref(0),retrySeconds=ref(0)
    let cooldownTimer=null
    const applyCooldown=e=>{if(e.statusCode!==429)return;retryAt.value=Date.now()+Math.max(2,e.retryAfter||10)*1000;clearInterval(cooldownTimer);const tick=()=>{retrySeconds.value=Math.max(0,Math.ceil((retryAt.value-Date.now())/1000));if(!retrySeconds.value)clearInterval(cooldownTimer)};tick();cooldownTimer=setInterval(tick,1000)}
    onUnload(()=>clearInterval(cooldownTimer))
    const generateHint=computed(()=>retrySeconds.value?'操作有点快，'+retrySeconds.value+' 秒后可继续':uploading.value?'正在提交，请稍等':job.value && !finished.value?'离开页面也会继续生成，回来就能查看':!quotaReady.value?'正在连接生成服务':!quotaAvailable.value?'今天的次数用完啦，也可以去首页手动制作':!photo.value?'先选一张照片，再让 AI 帮你搭配':'每批优先搭配未用过的模板，九张一组')
    const attributions=computed(()=>{const seen=new Set();return (job.value?.results||[]).map(r=>r.attribution).filter(a=>a?.source_url && !seen.has(a.source_url) && seen.add(a.source_url))})
    const refresh=async()=>{
      if(!session.value)return
      const owner=session.value.profile.id
      quotaLoading.value=true
      await Promise.allSettled([
        getQuota().then(data=>{if(session.value?.profile?.id===owner){quota.value=data;quotaReady.value=true;quotaError.value=''}}).catch(e=>{if(session.value?.profile?.id===owner){quotaReady.value=false;quotaError.value=e.message||'服务暂时没连上，点这里重试'}}),
        listJobs().then(data=>{if(session.value?.profile?.id===owner){history.value=data;historyPage.value=Math.min(historyPage.value,historyPages.value);historyError.value='';loadHistoryPreviews()}}).catch(()=>{if(session.value?.profile?.id===owner)historyError.value='最近生成暂时没加载出来，点这里重试'})
      ])
      if(session.value?.profile?.id===owner)quotaLoading.value=false
    }
    const stop=()=>{if(timer)clearTimeout(timer);timer=null}
    const poll=async()=>{
      if(!visible || !activeId.value || polling)return
      stop()
      polling=true;const id=activeId.value,epoch=generation
      try {
        const data=await getJob(id)
        if(id!==activeId.value || epoch!==generation)return
        job.value=data;error.value='';failures=0
        for(const result of data.results) {
          if(previews.value[result.slot] || inflight.has(result.slot) || inflight.size>=3)continue
          inflight.add(result.slot)
          downloadResult(result.preview_url).then(path=>{if(id===activeId.value && epoch===generation){previews.value[result.slot]=path;}}).catch(()=>{}).finally(()=>inflight.delete(result.slot))
        }
        if(finished.value)await refresh()
      } catch(e){failures++;error.value=e.message||e.errMsg||'网络暂时不可用，任务仍在后台处理';if(e.statusCode===404 || e.statusCode===401){activeId.value='';uni.removeStorageSync(activeKey())}}
      finally {
        polling=false
        if(visible && activeId.value && (!finished.value || job.value?.results?.some(r=>!previews.value[r.slot])))timer=setTimeout(poll,Math.min(8000,1000+failures*1500))
      }
    }
    const open=async (id,initial=null)=>{if(saving.value)return;rerollKey='';savedSlots.value=[];saveProgress.value='';stop();generation++;activeId.value=id;job.value=initial;previews.value={};selected.value=[];inflight.clear();exposed.clear();failures=0;uni.setStorageSync(activeKey(),id);if(initial){poll();return}await poll();selected.value=job.value?.selected_slots||[]}
    onShow(()=>{visible=true;sceneActive.value=true;observeVisible();refresh().catch(e=>{error.value=e.message||'暂时无法获取额度'});if(activeId.value)poll();else{const id=uni.getStorageSync(activeKey());if(id && session.value)open(id).catch(()=>{})}})
    onHide(()=>{visible=false;sceneActive.value=false;stop();disconnectObserver()});onUnload(()=>{visible=false;stop();disconnectObserver();generation++})
    const choose=()=>uni.chooseImage({count:1,sizeType:['compressed'],sourceType:['album','camera'],success:r=>{photo.value=r.tempFilePaths[0];requestKey='';error.value=''}})
    let uploadedAsset=null
    const generate=async()=>{
      if(busy.value||retrySeconds.value||!photo.value||!quotaReady.value||!quotaAvailable.value)return
      uploading.value=true;error.value=''
      const owner=session.value?.profile?.id,epoch=generation
      try {
        if(!requestKey){requestKey=`${Date.now()}-${Math.random().toString(36).slice(2)}`;uploadedAsset=null}
        if(!uploadedAsset)uploadedAsset=await uploadPhoto(photo.value)
        if(owner!==session.value?.profile?.id || epoch!==generation)return
        const data=await createJob(uploadedAsset.asset_id,requestKey)
        if(owner!==session.value?.profile?.id || epoch!==generation)return
        requestKey=''
        await open(data.job_id,{status:data.status,results:[],selected_slots:[],message:'照片上传完成，正在匹配模板'})
        refresh().catch(()=>{})
      }catch(e){if(owner!==session.value?.profile?.id || epoch!==generation)return;applyCooldown(e);error.value=e.message||e.errMsg||'提交失败，请重试';if(e.statusCode===401)login()}
      finally{uploading.value=false}
    }
    const reroll=async()=>{
      if(busy.value || retrySeconds.value || !activeId.value || !finished.value || !quotaReady.value || !quotaAvailable.value || !rerollSupported.value || job.value?.reroll_available===false)return
      const parent=activeId.value,owner=session.value?.profile?.id,epoch=generation
      uploading.value=true;error.value=''
      if(!rerollKey)rerollKey=`reroll-${Date.now()}-${Math.random().toString(36).slice(2)}`
      try{
        const data=await createJob(undefined,rerollKey,parent)
        if(owner!==session.value?.profile?.id || epoch!==generation)return
        await open(data.job_id,{status:data.status,results:[],selected_slots:[],message:'同一张照片，正在换一组新模板'})
        refresh().catch(()=>{})
      }catch(e){if(owner===session.value?.profile?.id && epoch===generation){applyCooldown(e);error.value=e.message||'没换成，原来的结果还在，点换一批重试吧'}}
      finally{uploading.value=false}
    }
    let feedbackQueue=Promise.resolve()
    const feedback=()=>{const id=activeId.value,slots=[...selected.value];if(id)feedbackQueue=feedbackQueue.then(()=>selectResults(id,slots)).catch(()=>{error.value='选择未能同步，请联网后重新选择'})}
    const toggle=slot=>{if(saving.value || !previews.value[slot] || !job.value?.results.some(r=>r.slot===slot))return;selected.value=selected.value.includes(slot)?selected.value.filter(s=>s!==slot):[...selected.value,slot];feedback()}
    const selectAll=()=>{if(saving.value)return;selected.value=selected.value.length===job.value.results.length?[]:job.value.results.map(r=>r.slot);feedback()}
    const save=async()=>{
      if(saving.value || !activeId.value || !selected.value.length)return
      const id=activeId.value, owner=session.value?.profile?.id, slots=[...selected.value]
      const pending=slots.filter(slot=>!savedSlots.value.includes(slot))
      if(!pending.length){uni.showToast({title:'所选图片已经保存啦',icon:'none'});return}
      saving.value=true;error.value=''
      const report=()=>saveProgress.value=`已保存 ${slots.filter(slot=>savedSlots.value.includes(slot)).length} / ${slots.length} 张`
      report()
      try {
        for(const slot of pending){
          const path=await downloadResult(`/recommend/jobs/${id}/results/${slot}`)
          if(id!==activeId.value || owner!==session.value?.profile?.id)throw new Error('账户或记录已切换，请重新选择结果')
          await uni.saveImageToPhotosAlbum({filePath:path})
          savedSlots.value=[...savedSlots.value,slot];report()
        }
        selectResults(id,slots,'download').catch(()=>{})
        uni.showToast({title:`已保存${slots.length}张`,icon:'success'})
      }catch(e){const raw=String(e.errMsg||e.message||'');error.value=/auth|deny|denied|权限/.test(raw)?'相册权限还没开启，请在小程序设置中允许保存后重试':(raw||'保存暂时失败')+'；重试会继续保存剩余图片'}
      finally{saving.value=false}
    }
    const login=async()=>{if(loggingIn.value)return;error.value='';try{await account.loginWeChat();await refresh()}catch(e){error.value=e.message||'登录失败，请重试'}}
    const shareCurrent=()=>shareOriginalImage(shareImage.value,title=>uni.showToast({title,icon:'none'}))
    const shareSelected=async()=>{const slot=selected.value[0],id=activeId.value,owner=session.value?.profile?.id;if(slot===undefined)return;try{const path=previews.value[slot]||await downloadResult(`/recommend/jobs/${id}/results/${slot}`);if(id!==activeId.value || owner!==session.value?.profile?.id)return;previews.value[slot]=path;shareSlot.value=slot}catch(e){error.value=e.message||'图片暂时没能打开，请重试'}}
    const saveCurrent=async()=>{if(!shareImage.value)return;try{await uni.saveImageToPhotosAlbum({filePath:shareImage.value});uni.showToast({title:'已保存',icon:'success'})}catch(e){error.value='保存失败，请检查相册权限后重试'}}
    const preview=slot=>{const paths=(job.value?.results||[]).map(r=>previews.value[r.slot]).filter(Boolean);if(previews.value[slot])uni.previewImage({urls:paths,current:previews.value[slot]})}
    const deleteHistory=item=>{if(uploading.value || saving.value)return;uni.showModal({title:'删除生成记录',content:'删除这组结果后无法恢复。若原照片还被其他批次使用，会继续保留至24小时到期。',success:async r=>{if(!r.confirm)return;try{await removeJob(item.job_id);if(activeId.value===item.job_id){stop();activeId.value='';job.value=null;previews.value={};uni.removeStorageSync(activeKey())}await refresh()}catch(e){error.value=e.message||'删除失败'}}})}
    const preference=async e=>{try{await setPersonalization(e.detail.value);quota.value.personalization=e.detail.value}catch(e){error.value=e.message||'设置失败'}}
    watch(()=>session.value?.profile?.id,(id,old)=>{if(id===old)return;stop();generation++;disconnectObserver();activeId.value='';job.value=null;previews.value={};selected.value=[];photo.value='';history.value=[];historyPage.value=1;historyPreviews.value={};historyInflight.clear();shareSlot.value=null;savedSlots.value=[];saveProgress.value='';quotaReady.value=false;quotaLoading.value=false;quotaError.value='';historyError.value='';inflight.clear();exposed.clear();requestKey='';rerollKey='';uploadedAsset=null;if(id && visible)refresh()})
    return {historyPage,historyPages,visibleHistory,historyPreviews,changeHistoryPage,shareSlot,shareImage,shareCurrent,shareSelected,saveCurrent,sceneActive,rerollSupported,unlimited,quotaAvailable,reroll,session,loggingIn,quotaLoading,quotaReady,quotaError,historyError,resultSlots,generateHint,savedSlots,saveProgress,preview,refresh,goHome:()=>uni.switchTab({url:'/pages/index/index'}),quota,photo,job,previews,selected,error,uploading,saving,history,activeId,finished,busy,attributions,choose,generate,toggle,selectAll,save,login,open,deleteHistory,preference,resume:()=>{stop();poll()},back:()=>uni.navigateBack(),formatTime:t=>new Date(t*1000).toLocaleString(),labels:{queued:'等待中',running:'生成中',completed:'已完成',failed:'未完成'}}
  }
}
</script>

<style scoped>
.recommend-page{min-height:100vh;background:var(--paper);padding:calc(100rpx + env(safe-area-inset-top)) 28rpx calc(180rpx + env(safe-area-inset-bottom))}.recommend-page.has-results{padding-bottom:calc(380rpx + env(safe-area-inset-bottom))}.page-header{display:flex;align-items:center;gap:18rpx}.page-header>view{flex:1;min-width:0}.back{width:76rpx;height:80rpx;line-height:72rpx;border-radius:24rpx;background:#f1ece3;color:#7e8a7c;font-size:46rpx;padding:0;flex-shrink:0}.title{display:block;font-size:34rpx;font-weight:750;margin-top:4rpx}.mini-logo{width:86rpx;height:86rpx;border:2rpx solid var(--line);border-radius:24rpx}.intro-card{display:flex;align-items:center;justify-content:space-between;background:#e9f0e7;padding:28rpx;border-radius:30rpx;margin-top:28rpx;gap:12rpx}.intro-title{display:block;font-size:34rpx;font-weight:750;color:#355d52}.intro{display:block;font-size:23rpx;color:#7d9585;margin-top:8rpx}.intro-spark{font-size:60rpx;color:#a0b99a;animation:ui-float 5s ease-in-out infinite}.steps{display:flex;align-items:center;gap:14rpx;margin:28rpx 0;font-size:22rpx}.step{color:#a1a795;white-space:nowrap}.step.active{color:var(--accent-dark);font-weight:600}.step-line{height:2rpx;flex:1;background:var(--line)}.quota-row{display:flex;align-items:center;justify-content:space-between;margin:26rpx 0 18rpx;font-size:25rpx;color:#6f8277}.quota-badge{font-size:20rpx;color:#a0a58f}.upload-card{width:100%;min-height:300rpx;background:#fff;border:2rpx dashed #decfbc;border-radius:32rpx;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:8rpx;padding:24rpx;line-height:1.6}.photo{width:100%;height:240rpx;border-radius:22rpx;background:#f4f2eb;margin-bottom:10rpx}.upload-illustration{position:relative;width:100rpx;height:100rpx;background:#ffebc0;border-radius:32rpx;transform:rotate(-7deg);color:#a28550;margin-bottom:14rpx;display:flex;align-items:center;justify-content:center}.upload-illustration>text:first-child{font-size:72rpx}.upload-illustration>text:last-child{position:absolute;right:-18rpx;bottom:-4rpx;border:5rpx solid white;border-radius:50%;width:48rpx;height:48rpx;background:var(--accent);color:white;font-size:28rpx;line-height:38rpx}.upload-title{font-size:28rpx;color:var(--ink);font-weight:600}.upload-caption{font-size:22rpx;color:#929a8a}.generate-button{margin-top:20rpx;width:100%}.hint{font-size:22rpx;color:#96a08d;line-height:1.7}.generation-hint{display:block;text-align:center;margin:14rpx 0 24rpx}.result-header{display:flex;justify-content:space-between;align-items:center;gap:20rpx;margin:34rpx 0 18rpx}.result-header>view{flex:1;min-width:0}.section-title{font-size:31rpx;font-weight:750;color:var(--ink)}.result-status{display:block;font-size:22rpx;color:#8b9a88;margin-top:7rpx}.result-count{font-size:38rpx;color:var(--accent-dark);font-weight:750;white-space:nowrap}.result-count>text{font-size:22rpx;color:#a0a78e;font-weight:400}.results{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14rpx}.result{min-width:0;height:234rpx;position:relative;background:#fff;border:3rpx solid var(--line);border-radius:26rpx;overflow:hidden;display:flex;align-items:center;justify-content:center;transition:transform .16s,border-color .16s}.result:active{transform:scale(.97)}.result.selected{border-color:var(--accent)}.result-image{width:100%;height:180rpx;margin-bottom:40rpx;animation:ui-enter .22s ease-out}.placeholder{font-size:34rpx;color:#c9bba2}.zoom{position:absolute;bottom:0;left:0;right:0;width:100%;height:52rpx;background:#f5f2e9;color:#84917c;font-size:20rpx;line-height:52rpx;padding:0}.check{position:absolute;top:8rpx;right:8rpx;width:36rpx;height:36rpx;background:#fffdf8;border:2rpx solid #e4ddcf;border-radius:50%;font-size:24rpx;line-height:32rpx;text-align:center;color:white}.check.checked{background:var(--accent);border-color:var(--accent)}.actions{position:fixed;bottom:calc(130rpx + env(safe-area-inset-bottom));left:16rpx;right:16rpx;background:#fffdfa;border:2rpx solid var(--line);border-radius:28rpx;padding:14rpx 20rpx 18rpx;z-index:110;box-shadow:0 -4rpx 22rpx rgba(56,61,39,.04)}.selection-copy{display:flex;justify-content:space-between;align-items:center;font-size:23rpx;color:#8c987e;margin-bottom:10rpx}.selection-copy button{font-size:23rpx;color:var(--accent-dark);padding:8rpx 12rpx;line-height:1.5}.actions .ui-primary{min-height:80rpx;padding:18rpx 12rpx}.error{display:block;font-size:24rpx;line-height:1.7;color:#af5c45;background:#fff0e4;padding:20rpx;border-radius:24rpx;margin:18rpx 0}.retry-inline{width:100%;text-align:left}.link,.text-link{font-size:24rpx;color:var(--accent-dark);line-height:1.5;padding:16rpx 10rpx}.text-link{margin:0 auto}.attribution{margin-top:16rpx}.attribution text{display:block;font-size:20rpx;color:#a1a48f;line-height:1.7}.preference{display:flex;align-items:center;justify-content:space-between;gap:14rpx;padding:24rpx;background:#f0f1e5;border-radius:28rpx;margin-top:30rpx;font-size:26rpx;color:#687e62}.preference>view{flex:1}.preference-copy{display:block;font-size:20rpx;color:#91a085;line-height:1.6;margin-top:6rpx}.history-heading{display:flex;align-items:center;justify-content:space-between;margin:34rpx 0 16rpx}.history-row{display:flex;align-items:center;background:white;border:2rpx solid var(--line);border-radius:24rpx;margin-bottom:12rpx;padding:10rpx 10rpx 10rpx 18rpx}.history-open{display:flex;align-items:center;gap:18rpx;flex:1;text-align:left;line-height:1.6;font-size:24rpx;color:#657e70;padding:8rpx 0}.history-symbol{width:68rpx;height:68rpx;background:#f7eed9;border-radius:22rpx;color:#b59a64;font-size:43rpx;line-height:68rpx;text-align:center;flex-shrink:0}.history-meta{display:block;font-size:21rpx;color:#9aa58b;margin-top:4rpx}.delete-link{font-size:22rpx;min-height:84rpx;padding:22rpx 14rpx}.privacy-note{margin-top:34rpx;text-align:center}.privacy-note text{display:block;font-size:21rpx;line-height:1.8;color:#a6ad98}.login-card{text-align:center;background:white;border:2rpx solid var(--line);border-radius:32rpx;padding:30rpx 26rpx}.login-logo{width:130rpx;height:130rpx;border-radius:30rpx;margin:0 auto 20rpx}.login-title{display:block;font-size:30rpx;font-weight:700}.login-copy{display:block;font-size:24rpx;color:#8f9c8b;margin-top:10rpx}.login-card .ui-primary{width:100%;margin:26rpx 0 14rpx}.empty-history,.empty-note{display:block;font-size:23rpx;color:#97a58a;background:#f0f1e7;padding:26rpx;border-radius:24rpx;line-height:1.8;margin-top:16rpx}
.recommend-page{padding-top:calc(76rpx + env(safe-area-inset-top));padding-left:30rpx;padding-right:30rpx}.intro-card{position:relative;overflow:hidden;background:linear-gradient(125deg,#fcf5ee,#faf2e9);border:3rpx solid #fff;border-radius:38rpx;box-shadow:0 7rpx 0 #f0e6da;min-height:265rpx;padding:30rpx 24rpx}.intro-card>view:first-child{position:relative;z-index:1;width:73%}.intro-title{color:#3a5a64;font-size:40rpx;line-height:1.35;margin-top:13rpx;letter-spacing:-1rpx;font-weight:850}.intro-title>text{display:block;color:#bd7c65}.intro{color:#aba195;font-size:21rpx;margin-top:12rpx}.intro-toys{position:absolute;width:235rpx;height:235rpx;right:-30rpx;top:10rpx}.back{background:linear-gradient(145deg,#fff,#f7f1eb);border:2rpx solid #fff;color:#aca296;box-shadow:0 5rpx 0 #ede5dc}.steps{background:#f5f1ed;border-radius:24rpx;padding:17rpx 19rpx;margin-top:30rpx;font-size:20rpx}.step{color:#aea499}.step.active{color:#c1846d}.quota-row{color:#a09385;font-size:23rpx}.quota-badge{font-size:17rpx;color:#bcb3a9}.upload-card{border:3rpx dashed #ede0d2;box-shadow:inset 0 3rpx 0 #fff,0 6rpx 0 #f3ece5;background:#fefefd;border-radius:34rpx}.upload-illustration{background:linear-gradient(135deg,#fff4c8,#f8d980);color:#b28638;border:2rpx solid #fff4cc;box-shadow:0 7rpx 0 #e4be64,inset 0 4rpx 0 #fff9df}.upload-illustration>text:last-child{background:linear-gradient(145deg,#e8a58d,#c47e64);box-shadow:0 3rpx 0 #a96248}.upload-caption,.hint{color:#ada397}.result{box-shadow:0 5rpx 0 #efe8e0;border-color:#fff;background:linear-gradient(135deg,#fff,#fefcf9)}.result.selected{border-color:#e3b3a1;box-shadow:0 5rpx 0 #dcbaae}.zoom{background:#f8f3ed;color:#a4998c}.result-status{color:#a89d90}.batch-bar{display:flex;align-items:center;justify-content:space-between;gap:12rpx;border:2rpx solid #f4eadf;background:#f9f3ed;border-radius:27rpx;padding:20rpx;margin:16rpx 0 24rpx}.batch-bar>view{flex:1;min-width:0}.batch-title{display:block;font-size:24rpx;font-weight:750;color:#8a7c6c}.batch-caption{display:block;font-size:18rpx;color:#aea499;margin-top:5rpx;line-height:1.7}.reroll-button{display:flex;align-items:center;justify-content:center;min-height:74rpx;flex-shrink:0;border:2rpx solid #fff;border-radius:22rpx;background:linear-gradient(135deg,#fff,#faf1e7);color:#ba765d;box-shadow:0 5rpx 0 #eadccc;font-size:24rpx;font-weight:750;line-height:1.4;padding:13rpx 19rpx}.reroll-button:active{transform:translateY(4rpx)}.actions{background:#fefefd;border:3rpx solid #fff;border-radius:32rpx;bottom:calc(158rpx + env(safe-area-inset-bottom));padding-bottom:24rpx;box-shadow:0 7rpx 0 #ede5dc,0 10rpx 26rpx rgba(64,40,94,.07)}.selection-copy{color:#a79c90}.preference{background:#f7f1eb;color:#9e9284}.preference-copy{color:#b7aea4}.history-symbol{background:linear-gradient(140deg,#fff3c9,#f3d488);box-shadow:0 5rpx 0 #e0c16f,inset 0 3rpx 0 #fff9df;color:#af8738}.history-row{border-color:#fff;box-shadow:0 5rpx 0 #f1ebe4}.history-open{color:#9e9284}.history-meta{color:#bab2a8}.privacy-note text{color:#bbb3aa}.login-card{border:3rpx solid white;box-shadow:0 7rpx 0 #f1e9e0; padding-bottom:34rpx}.login-copy{color:#aea397}.empty-history,.empty-note{background:#f7f1eb;color:#b0a69a}.result-count>text{color:#bcb3a9}.attribution text{color:#bbb2a8}.selection-copy button{background:transparent}.error{color:#ad7462;background:#fff0ea}
.intro-card{background:linear-gradient(125deg,#ebf2e7,#e4eddf);box-shadow:0 7rpx 0 #d5e1cd}.intro-title{color:#355d52}.intro-title>text{color:#7a986c}.intro{color:#91a183}.batch-bar{background:#f1f4e7;border-color:#e4e9d4}.batch-title{color:#7a8c5f}.batch-caption{color:#a1ac8a}.reroll-button{background:linear-gradient(135deg,#fff,#f0f3e5);color:#8c9c6c;box-shadow:0 5rpx 0 #dce2c8}.quota-row{color:#7d9273}.quota-badge{color:#a3af94}.preference{background:#eef2e5;color:#839675}.preference-copy{color:#a1ae93}.result-status{color:#8a987b}.selection-copy{color:#a38c6c}.login-copy{color:#a2927c}
.intro-copy-block{position:relative;z-index:1;width:65%}.intro-pop{display:block;color:#7a986c}.intro-toys{width:210rpx;height:230rpx;right:6rpx;top:18rpx}
.step.active{animation:ui-pop .35s ease-out both}.result.selected .check{animation:ui-pop .3s ease-out both}.result:nth-child(3n+2) .placeholder{animation-delay:.2s}.result:nth-child(3n) .placeholder{animation-delay:.4s}.reroll-button:not([disabled]):active{transform:translateY(4rpx) rotate(-3deg)}.result.selected{transform:translateY(-3rpx)}.error{animation:ui-nudge .35s ease-out both}.selection-copy{animation:ui-reveal .25s ease-out both}

.actions{position:static;margin:24rpx 0;box-shadow:none;border-radius:26rpx}.recommend-page.has-results{padding-bottom:calc(180rpx + env(safe-area-inset-bottom))}.share-selected{width:100%;margin-top:14rpx;gap:12rpx}.history-symbol{overflow:hidden;display:flex;align-items:center;justify-content:center}.history-symbol image{width:100%;height:100%}.history-paging{display:flex;justify-content:center;align-items:center;gap:26rpx;margin:26rpx 0;color:#8f9a80;font-size:24rpx}.history-paging button{padding:16rpx 24rpx;border-radius:16rpx;background:white;color:#bb7d57;font-size:24rpx}.history-paging button[disabled]{opacity:.35}
</style>
