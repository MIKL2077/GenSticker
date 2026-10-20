<template>
 <view class="data-controls">
  <account-action-card class="manage" icon="layers" title="管理素材与账号" description="整理作品与账号数据" @click="open"/>
  <view v-if="visible" class="mask" @touchmove.stop>
   <view class="panel">
    <view class="heading"><text>我的素材与数据</text><button @click="visible=false">关闭</button></view>
    <text v-if="usage" class="note">已用 {{mb(usage.used_bytes)}} / {{mb(usage.limit_bytes)}} MB · 自制模板 {{usage.templates}} / {{usage.template_limit}}</text>
    <text class="note">删除视频后，旧任务可能无法重新制作；已保存到相册或他人设备的副本无法撤回。</text>
    <text v-if="error" class="error">{{error}}</text>
    <scroll-view scroll-y class="items">
     <text class="section">我的模板</text>
     <view v-for="item in templates" :key="item.id" class="item"><view><text>{{item.name}}</text><text class="note">{{item.requires_review?'识别草稿，待你校对':item.status==='published'?'已公开':item.status==='pending'?'待检查':'仅自己可见'}}</text></view><button v-if="item.status==='published'||item.status==='pending'" :disabled="busy" @click="changeTemplate(item,false)">撤回</button><button :disabled="busy" @click="changeTemplate(item,true)">删除</button><view v-if="item.requires_review" class="review"><text class="note">请校对识别文字并检查预览；确认后仍需微信内容检查。</text><input v-for="(text,i) in item.review_texts" :key="i" v-model="item.review_texts[i]" maxlength="200" @input="previews[item.id]=''"/><button :disabled="busy" @click="review(item,false)">保存校对并预览</button><image v-if="previews[item.id]" :src="previews[item.id]" mode="aspectFit" @click="enlarge(previews[item.id])"/><button v-if="previews[item.id] && item.review_digest" :disabled="busy" @click="review(item,true)">已检查预览，申请发布</button></view></view>
     <text v-if="!templates.length" class="note">还没有自制模板</text>
     <text class="section">上传的视频与 GIF 素材</text>
     <view v-for="item in videos" :key="item.id" class="item"><view><text>{{Math.round(item.duration)}} 秒 · {{mb(item.bytes)}} MB</text><text class="note">{{date(item.created_at)}}</text></view><button :disabled="busy" @click="removeVideo(item)">删除</button></view>
     <text v-if="!videos.length" class="note">没有保留的视频素材</text>
    </scroll-view>
    <button class="danger" :disabled="busy" @click="removeAccount">注销账号并删除数据</button>
    <text class="note">注销会撤回公开模板、删除资料、收藏、历史、偏好、私有素材和作品。已有制作任务须先完成；防滥用摘要保留约 31 天，加密备份按保留期清除。</text>
   </view>
  </view>
 </view>
</template>
<script setup>
import {ref} from 'vue'
import AccountActionCard from '@/components/AccountActionCard.vue'
import {apiRequest} from '@/services/apiService'
import {useLibrary} from '@/composables/useLibrary'
import {privateImage,trackStudioJob} from '@/services/studioService'
const account=useLibrary(),visible=ref(false),busy=ref(false),error=ref(''),usage=ref(null),templates=ref([]),videos=ref([]),previews=ref({})
const mb=n=>(n/1048576).toFixed(1)
const date=t=>new Date(t*1000).toLocaleDateString()
const load=async()=>{const owner=account.session.value?.profile?.id;const [used,items,media]=await Promise.all([apiRequest('/account/storage',{},1),apiRequest('/studio/templates',{},1),apiRequest('/studio/live/assets',{},1)]);if(account.session.value?.profile?.id!==owner){visible.value=false;return}usage.value=used;videos.value=media;templates.value=items.map(item=>({id:item.id,name:item.name,status:item.status,requires_review:item.requires_review,review_digest:item.review_digest,review_texts:[...item.params_type.default_texts]}))}
const open=async()=>{visible.value=true;error.value='';try{await load()}catch(e){error.value=e.message||'暂时无法读取，请重试'}}
const confirm=(title,content)=>new Promise(resolve=>uni.showModal({title,content,confirmText:'确认',confirmColor:'#b65e4b',success:r=>resolve(r.confirm),fail:()=>resolve(false)}))
const run=async action=>{if(busy.value)return;busy.value=true;error.value='';try{await action();await load()}catch(e){error.value=e.message||'操作失败，请稍后重试'}finally{busy.value=false}}
const changeTemplate=async(item,remove)=>{if(!await confirm(remove?'删除这个模板？':'撤回公开模板？',remove?'模板将从你的列表和公开目录移除，无法恢复。':'之后仅自己可见，可以再次申请发布。'))return;await run(()=>apiRequest(`/studio/templates/${item.id}${remove?'':'/withdraw'}`,{method:remove?'DELETE':'POST'},1))}
const enlarge=path=>uni.previewImage({urls:[path],current:path})
const review=async(item,confirmed)=>{if(confirmed&&!await confirm('确认校对并申请发布？','请确认已检查文字和布局，并拥有素材使用与公开的权利。之后还需要微信内容检查。'))return;await run(async()=>{const result=await apiRequest(`/studio/templates/${item.id}/captions`,{method:'PATCH',data:{texts:item.review_texts,confirmed,rights_attested:confirmed,preview_digest:item.review_digest||''}},1);if(result.publication_job)trackStudioJob(result.publication_job);if(!confirmed)previews.value[item.id]=await privateImage(result.preview_url)})}
const removeVideo=async item=>{if(await confirm('删除视频素材？','删除后无法用这份视频重做；已完成的 GIF 仍可领取。'))await run(()=>apiRequest(`/studio/live/assets/${item.id}`,{method:'DELETE'},1))}
const removeAccount=async()=>{
 const current=account.session.value,owner=current?.profile?.id
 if(busy.value||!owner||!await confirm('注销账号并删除数据？','此操作无法撤销。将退出所有设备，删除资料及私有作品，并撤回公开模板。'))return
 if(account.session.value?.profile?.id!==owner){visible.value=false;return}
 busy.value=true;error.value=''
 try{
  await apiRequest('/account',{method:'DELETE',header:{Authorization:'Bearer '+current.access_token},data:{confirmation:'注销账号'}},1)
  if(account.session.value?.profile?.id===owner)account.logout()
  const keys=uni.getStorageInfoSync?.().keys||[]
  for(const key of keys)if(key.startsWith('gensticker.')&&key.includes(owner)){
   const records=uni.getStorageSync(key)
   if(Array.isArray(records))for(const item of records){const path=item?.localPath;if(path&&uni.env?.USER_DATA_PATH&&path.startsWith(uni.env.USER_DATA_PATH+'/generated_meme_'))uni.getFileSystemManager?.().unlink({filePath:path,fail:()=>{}})}
   uni.removeStorageSync(key)
  }
  const avatar=`${uni.env?.USER_DATA_PATH}/avatar_${owner}.jpg`
  if(uni.env?.USER_DATA_PATH)uni.getFileSystemManager?.().unlink({filePath:avatar,fail:()=>{}})
  visible.value=false;uni.showToast({title:'账号数据已删除',icon:'none'})
 }catch(e){error.value=e.message||'注销未完成，请重试'}finally{busy.value=false}
}
</script>
<style scoped>
.data-controls{height:100%}.manage{display:block;height:100%}.mask{position:fixed;inset:0;background:rgba(29,43,47,.5);z-index:3100;display:flex;align-items:center;padding:28rpx}.panel{background:var(--paper);border-radius:30rpx;padding:28rpx;width:100%;max-height:85vh;overflow-y:auto}.heading{display:flex;justify-content:space-between;align-items:center;font-size:31rpx;font-weight:650}.heading button{font-size:24rpx;padding:15rpx}.note{display:block;color:#858b7d;font-size:22rpx;line-height:1.7;margin:10rpx 0}.items{max-height:42vh}.section{display:block;font-size:27rpx;font-weight:650;margin:20rpx 0}.item{display:flex;flex-wrap:wrap;align-items:center;gap:12rpx;padding:16rpx 0;border-bottom:1rpx solid var(--line);font-size:25rpx}.item>view{flex:1}.item button{font-size:23rpx;padding:14rpx;color:var(--accent-dark)}.danger{color:#b65e4b;font-size:26rpx;padding:24rpx;margin-top:18rpx;border:1rpx solid var(--line);border-radius:20rpx}.error{display:block;color:#b65e4b;font-size:24rpx;line-height:1.7}
</style>

<style scoped>.review{flex:0 0 100%!important}.review input{background:white;border:1rpx solid var(--line);border-radius:12rpx;padding:14rpx;margin:12rpx 0;font-size:26rpx}.review image{display:block;width:100%;height:280rpx}.review button{margin-top:10rpx;border:1rpx solid var(--line);border-radius:14rpx}</style>
