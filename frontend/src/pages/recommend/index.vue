<template>
  <view class="recommend-page">
    <view class="page-header"><button class="back" @click="back">‹ 返回</button><text class="title">照片一键配表情</text></view>
    <text class="intro">上传一张照片，自动匹配表情模板。选一张，也可以全都要。</text>
    <view v-if="!session" class="login-card"><text>登录后即可使用，每天 {{ quota.limit }} 次</text><button class="primary" @click="login">微信登录</button></view>
    <template v-else>
      <view class="quota-row"><text>今日剩余 {{ quota.remaining }} / {{ quota.limit }} 次</text><text class="privacy">照片仅用于本次制作</text></view>
      <button class="upload-card" :disabled="busy" @click="choose"><image v-if="photo" :src="photo" mode="aspectFit" class="photo" /><text v-else class="upload-icon">＋</text><text>{{ photo ? '更换照片' : '选择照片' }}</text></button>
      <button class="primary" :disabled="busy || !photo || quota.remaining <= 0" :loading="uploading" @click="generate">{{ uploading ? '正在上传' : busy ? '正在生成' : '生成九宫格' }}</button>
      <view v-if="error" class="error"><text>{{ error }}</text><button v-if="activeId" class="link" @click="resume">重试获取进度</button></view>
      <view v-if="job" class="result-header"><text>{{ job.message || '等待生成' }}</text><text>{{ job.results.length }} / 9</text></view>
      <view v-if="job?.analysis?.warnings?.length" class="hint">{{ job.analysis.warnings.filter(t => !t.includes('真实情绪')).join('；') }}</view>
      <view v-if="job" class="results">
        <view v-for="slot in 9" :key="slot" class="result" :class="{selected:selected.includes(slot-1)}" @click="toggle(slot-1)">
          <image v-if="previews[slot-1]" :src="previews[slot-1]" :data-slot="slot-1" mode="aspectFit" class="result-image" />
          <text v-else class="placeholder">{{ finished ? '暂无结果' : '准备中' }}</text>
          <text v-if="selected.includes(slot-1)" class="check">✓</text>
        </view>
      </view>
      <view v-if="job?.results?.length" class="actions"><button class="secondary" @click="selectAll">{{ selected.length === job.results.length ? '取消全选' : '全都要' }}</button><button class="primary" :disabled="!selected.length || saving" :loading="saving" @click="save">保存 {{ selected.length }} 张</button></view>
      <view v-if="attributions.length" class="attribution"><text v-for="item in attributions" :key="item.source_url">素材：{{ item.author }} · {{ item.license }}（来源见图片底部）</text></view>
      <view class="preference"><text>根据我的选择优化推荐</text><switch :checked="quota.personalization" color="#ff805c" @change="preference" /></view>
      <text class="section">最近生成</text>
      <view v-for="item in history" :key="item.job_id" class="history-row"><view @click="open(item.job_id)"><text>{{ formatTime(item.created_at) }}</text><text class="history-meta">{{ labels[item.status] || item.status }} · {{ item.count }} 张</text></view><button class="link" @click="deleteHistory(item)">删除</button></view>
      <text class="hint footer">原图24小时后清理，结果保留7天。额度用完后仍可在首页手动制作。</text>
    </template>
  </view>
</template>
<script>
import { ref,computed,watch,nextTick,getCurrentInstance } from 'vue'
import { onShow,onHide,onUnload } from '@dcloudio/uni-app'
import { useLibrary } from '@/composables/useLibrary'
import { getQuota,listJobs,getJob,createJob,uploadPhoto,downloadResult,selectResults,removeJob,setPersonalization } from '@/services/recommendService'
export default {
  setup() {
    const {session}=useLibrary(), quota=ref({limit:3,remaining:0,personalization:true}),photo=ref(''),job=ref(null),previews=ref({}),selected=ref([]),error=ref(''),uploading=ref(false),saving=ref(false),history=ref([]),activeId=ref('')
    let timer=null, visible=true, polling=false, failures=0, requestKey='', generation=0
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
    const activeKey=()=>`gensticker.recommend.active.${session.value?.profile.id || 'guest'}`
    const finished=computed(()=>['completed','failed'].includes(job.value?.status))
    const busy=computed(()=>uploading.value || !!job.value && !finished.value)
    const attributions=computed(()=>{const seen=new Set();return (job.value?.results||[]).map(r=>r.attribution).filter(a=>a?.source_url && !seen.has(a.source_url) && seen.add(a.source_url))})
    const refresh=async()=>{if(!session.value)return;const data=await Promise.all([getQuota(),listJobs()]);quota.value=data[0];history.value=data[1]}
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
    const open=async (id,initial=null)=>{stop();generation++;activeId.value=id;job.value=initial;previews.value={};selected.value=[];inflight.clear();exposed.clear();failures=0;uni.setStorageSync(activeKey(),id);if(initial){poll();return}await poll();selected.value=job.value?.selected_slots||[]}
    onShow(()=>{visible=true;observeVisible();refresh().catch(e=>{error.value=e.message||'暂时无法获取额度'});if(activeId.value)poll();else{const id=uni.getStorageSync(activeKey());if(id && session.value)open(id).catch(()=>{})}})
    onHide(()=>{visible=false;stop();disconnectObserver()});onUnload(()=>{visible=false;stop();disconnectObserver();generation++})
    const choose=()=>uni.chooseImage({count:1,sizeType:['compressed'],sourceType:['album','camera'],success:r=>{photo.value=r.tempFilePaths[0];requestKey='';error.value=''}})
    let uploadedAsset=null
    const generate=async()=>{
      if(busy.value||!photo.value)return
      uploading.value=true;error.value=''
      try {
        if(!requestKey){requestKey=`${Date.now()}-${Math.random().toString(36).slice(2)}`;uploadedAsset=null}
        if(!uploadedAsset)uploadedAsset=await uploadPhoto(photo.value)
        const data=await createJob(uploadedAsset.asset_id,requestKey)
        await open(data.job_id,{status:data.status,results:[],selected_slots:[],message:'照片上传完成，正在匹配模板'})
        refresh().catch(()=>{})
      }catch(e){error.value=e.message||e.errMsg||'提交失败，请重试';if(e.statusCode===401)login()}
      finally{uploading.value=false}
    }
    let feedbackQueue=Promise.resolve()
    const feedback=()=>{const id=activeId.value,slots=[...selected.value];if(id)feedbackQueue=feedbackQueue.then(()=>selectResults(id,slots)).catch(()=>{error.value='选择未能同步，请联网后重新选择'})}
    const toggle=slot=>{if(!previews.value[slot] || !job.value?.results.some(r=>r.slot===slot))return;selected.value=selected.value.includes(slot)?selected.value.filter(s=>s!==slot):[...selected.value,slot];feedback()}
    const selectAll=()=>{selected.value=selected.value.length===job.value.results.length?[]:job.value.results.map(r=>r.slot);feedback()}
    const save=async()=>{
      saving.value=true;let count=0
      try {
        await feedbackQueue
        await selectResults(activeId.value,selected.value)
        for(const slot of selected.value){const path=await downloadResult(`/recommend/jobs/${activeId.value}/results/${slot}`);await uni.saveImageToPhotosAlbum({filePath:path});count++}
        await selectResults(activeId.value,selected.value,'download');uni.showToast({title:`已保存${count}张`,icon:'success'})
      }catch(e){error.value=count?`已保存${count}张，其余未完成，请检查相册权限后重试`:'保存失败，请允许保存到相册后重试'}
      finally{saving.value=false}
    }
    const login=()=>{uni.setStorageSync('gensticker.open-recommend',true);uni.switchTab({url:'/pages/my/index'})}
    const deleteHistory=item=>uni.showModal({title:'删除生成记录',content:'删除这次照片和结果，今天的已用次数不会重置。',success:async r=>{if(!r.confirm)return;try{await removeJob(item.job_id);if(activeId.value===item.job_id){stop();activeId.value='';job.value=null;previews.value={};uni.removeStorageSync(activeKey())}await refresh()}catch(e){error.value=e.message||'删除失败'}}})
    const preference=async e=>{try{await setPersonalization(e.detail.value);quota.value.personalization=e.detail.value}catch(e){error.value=e.message||'设置失败'}}
    return {session,quota,photo,job,previews,selected,error,uploading,saving,history,activeId,finished,busy,attributions,choose,generate,toggle,selectAll,save,login,open,deleteHistory,preference,resume:()=>{stop();poll()},back:()=>uni.navigateBack(),formatTime:t=>new Date(t*1000).toLocaleString(),labels:{queued:'等待中',running:'生成中',completed:'已完成',failed:'已退回次数'}}
  }
}
</script>
<style scoped>
.recommend-page{min-height:100vh;background:#fffaf7;padding:calc(100rpx + env(safe-area-inset-top)) 28rpx 48rpx;box-sizing:border-box}.page-header{display:flex;align-items:center;gap:20rpx}.back,.link{font-size:24rpx;color:#dd6547;margin:0;padding:8rpx;line-height:1.5;background:transparent}.title{font-size:34rpx;font-weight:700;color:#332e2b}.intro{display:block;margin:24rpx 0;color:#887b73;font-size:25rpx;line-height:1.7}.quota-row,.result-header{display:flex;justify-content:space-between;gap:12rpx;color:#6e5d53;font-size:24rpx;margin:28rpx 0}.privacy{font-size:20rpx;color:#9a8a80}.upload-card{height:260rpx;border:2rpx dashed #edcbb9;background:#fff3eb;border-radius:28rpx;display:flex;align-items:center;justify-content:center;flex-direction:column;font-size:26rpx;color:#a76845;gap:12rpx}.upload-icon{font-size:58rpx}.photo{width:180rpx;height:180rpx}.primary{background:#ff805c;color:white;border-radius:22rpx;font-size:27rpx;margin:22rpx 0 0;line-height:2.5}.primary[disabled]{background:#eaded7;color:#a39389}.secondary{background:white;color:#dd6547;border:2rpx solid #f2d1c2;border-radius:22rpx;font-size:25rpx;line-height:2.5;margin:22rpx 0 0}.results{display:grid;grid-template-columns:repeat(3,1fr);gap:14rpx}.result{height:210rpx;background:white;border-radius:22rpx;position:relative;display:flex;align-items:center;justify-content:center;border:3rpx solid transparent}.result.selected{border-color:#ff805c}.result-image{width:190rpx;height:190rpx}.placeholder{font-size:22rpx;color:#b4a59b}.check{position:absolute;right:8rpx;top:8rpx;background:#ff805c;color:white;border-radius:50%;width:34rpx;height:34rpx;text-align:center;line-height:34rpx;font-size:23rpx}.actions{display:flex;gap:18rpx}.actions button{flex:1}.error{color:#b14533;font-size:24rpx;margin-top:22rpx}.hint{display:block;color:#a28b7c;font-size:22rpx;line-height:1.6;margin:16rpx 0}.preference{display:flex;justify-content:space-between;align-items:center;color:#6d5d53;font-size:25rpx;margin:40rpx 0}.section{display:block;font-size:28rpx;font-weight:600;margin:24rpx 0}.history-row{display:flex;justify-content:space-between;align-items:center;background:white;padding:22rpx;border-radius:20rpx;margin-bottom:12rpx;font-size:23rpx;color:#66564c}.history-meta{display:block;color:#ad998b;font-size:21rpx;margin-top:8rpx}.attribution text{display:block;font-size:20rpx;color:#9b897a;margin-top:10rpx}.login-card{padding:30rpx;background:white;border-radius:24rpx;font-size:26rpx;color:#77655b}.footer{margin-top:32rpx}
</style>
