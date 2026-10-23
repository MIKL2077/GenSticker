<template>
  <view v-if="visible" class="guide-mask" @touchmove.stop.prevent>
    <view class="guide-dialog" role="dialog" aria-modal="true" :aria-label="'使用引导：'+current.title">
      <view class="guide-header">
        <text class="guide-welcome">欢迎来到 GenSticker</text>
        <button class="guide-skip" @click="finish">跳过引导</button>
      </view>
      <view class="guide-progress" aria-label="引导进度">
        <view v-for="(item,index) in steps" :key="item.title" class="guide-step" :class="{active:index===step,done:index<step}"/>
      </view>
      <scroll-view scroll-y class="guide-body">
        <view class="guide-illustration">
          <text class="guide-location">{{current.location}}</text>
          <view v-if="step===0" class="guide-real-example">
            <view class="guide-sample"><image src="/static/guide/photo.jpg" mode="aspectFit"/><text>选这张猫咪照片</text></view>
            <text class="guide-arrow">→</text>
            <view class="guide-sample"><image src="/static/guide/always.jpg" mode="aspectFit"/><text>套用「一直」模板</text></view>
          </view>
          <view v-else-if="step===1" class="guide-queue-example"><image src="/static/guide/always.jpg" mode="aspectFit"/><view><text class="guide-job-title">「一直」表情包</text><text>已完成 · 点开预览和保存</text><text>也可以重新编辑原来的内容</text></view></view>
          <view v-else class="guide-real-example guide-batch-example"><image class="guide-batch-photo" src="/static/guide/photo.jpg" mode="aspectFit"/><text class="guide-arrow">→</text><image class="guide-batch-image" src="/static/guide/batch.jpg" mode="aspectFit"/></view>
          <text class="guide-example-label">{{step===2?'同一张照片 · 九个真实模板的生成效果':'真实照片与模板生成示例'}}</text>
        </view>
        <text class="guide-count">{{step+1}} / {{steps.length}}</text>
        <text class="guide-title">{{current.title}}</text>
        <text class="guide-description">{{current.description}}</text>
        <text class="guide-tip">{{current.tip}}</text><button class="guide-credit" @click="credits">示例照片：Alvesgaspar · CC BY-SA 3.0</button>
      </scroll-view>
      <view class="guide-actions">
        <button v-if="step>0" class="ui-secondary guide-back" @click="step--">上一步</button>
        <button class="ui-primary guide-next" @click="next">{{step===steps.length-1?'开始制作':'下一步'}}</button>
      </view>
    </view>
  </view>
</template>

<script>
import {computed,ref,watch} from 'vue'
import {onShow,onHide,onUnload} from '@dcloudio/uni-app'
import {useLibrary} from '@/composables/useLibrary'


export default {
  setup() {
    const {session}=useLibrary()
    const pageActive=ref(false),step=ref(0),dismissedOwner=ref('')
    const owner=computed(()=>session.value?.profile?.id || '')
    const storageKey=id=>`gensticker.guide.${id}.v1`
    const steps=[
      {title:'模板生成',icon:'image',location:'首页 → 模板仓库',example:'选模板 → 换图片、改文字 → 生成',description:'挑一个喜欢的模板，按提示添加图片或文字，点击生成，就能做出自己的表情包。',tip:'图片可以调整选区、旋转和翻转；喜欢的模板也可以收藏。'},
      {title:'生成队列',icon:'queue',location:'我的 → 生成队列',example:'查看进度 → 打开成品 → 预览、保存',description:'模板制作和视频转 GIF 的任务，可以到生成队列查看进度与结果。完成后，点开就能预览和保存。',tip:'收起制作等待页后，可从这里找回任务；结果请及时保存。'},
      {title:'一键生成',icon:'spark',location:'底部导航 → 一键生成',example:'选照片 → 确认主体 → 一次制作九张',description:'选择一张照片，确认要用的主体，一次搭配九张表情。还可以换一批，挑选喜欢的结果一起保存。',tip:'整组生成记录保存在“一键生成”页面，回来还能继续查看。'},
    ]
    const visible=computed(()=>{
      if(!pageActive.value || !owner.value || dismissedOwner.value===owner.value)return false
      try{return uni.getStorageSync(storageKey(owner.value))!==true}catch(_){return true}
    })
    const finish=()=>{
      if(!owner.value)return
      dismissedOwner.value=owner.value
      try{uni.setStorageSync(storageKey(owner.value),true)}catch(_){}
    }
    const next=()=>{if(step.value<steps.length-1)step.value++;else finish()}
    watch(owner,()=>{step.value=0;dismissedOwner.value=''})
    onShow(()=>{pageActive.value=true})
    const hide=()=>{pageActive.value=false}
    onHide(hide)
    onUnload(hide)
    const credits=()=>uni.showModal({title:'示例素材来源',content:'照片：Alvesgaspar，Cat August 2010-4.jpg（Wikimedia Commons）。已裁剪、缩放并用于真实模板合成；示例图片按 CC BY-SA 3.0 许可提供。来源：https://commons.wikimedia.org/wiki/File:Cat_August_2010-4.jpg\n许可：https://creativecommons.org/licenses/by-sa/3.0/',showCancel:false})
    return {visible,step,steps,current:computed(()=>steps[step.value]),finish,next,credits}
  },
}
</script>

<style scoped>
.guide-mask{position:fixed;inset:0;z-index:6000;display:flex;align-items:center;justify-content:center;padding:calc(28rpx + env(safe-area-inset-top)) 28rpx calc(28rpx + env(safe-area-inset-bottom));background:rgba(29,43,47,.48)}
.guide-dialog{display:flex;flex-direction:column;width:100%;max-width:680rpx;max-height:100%;min-height:0;padding:26rpx;background:var(--paper);border:3rpx solid white;border-radius:36rpx;overflow:hidden}
.guide-header{display:flex;align-items:center;justify-content:space-between;gap:12rpx;flex-shrink:0}.guide-welcome{font-size:23rpx;color:var(--muted)}.guide-skip{padding:14rpx 0 14rpx 16rpx;font-size:23rpx;line-height:1.5;color:var(--muted)}
.guide-progress{display:flex;gap:12rpx;margin:12rpx 0 24rpx;flex-shrink:0}.guide-step{height:7rpx;flex:1;background:var(--line);border-radius:8rpx}.guide-step.active{background:var(--accent)}.guide-step.done{background:var(--accent-dark)}
.guide-body{height:640rpx;min-height:0;flex-shrink:1}.guide-illustration{display:flex;align-items:center;flex-direction:column;gap:20rpx;padding:26rpx 18rpx;background:var(--mint);border-radius:26rpx}.guide-icon{display:flex;align-items:center;justify-content:center;width:108rpx;height:108rpx;background:white;border-radius:30rpx}.guide-location{font-size:24rpx;font-weight:600;color:var(--ink)}.guide-example{width:100%;padding:18rpx 10rpx;background:white;border-radius:18rpx;text-align:center;color:var(--ink);font-size:23rpx;line-height:1.7}.guide-example-label{display:block;color:var(--muted);font-size:19rpx;margin-top:5rpx}
.guide-count{display:block;margin-top:24rpx;color:var(--accent-dark);font-size:22rpx}.guide-title{display:block;font-size:36rpx;font-weight:750;margin-top:6rpx}.guide-description{display:block;color:var(--ink);font-size:26rpx;line-height:1.8;margin-top:14rpx}.guide-tip{display:block;color:var(--muted);font-size:23rpx;line-height:1.7;margin:12rpx 0 20rpx}
.guide-actions{display:flex;gap:16rpx;margin-top:24rpx;padding-bottom:7rpx;flex-shrink:0}.guide-back{width:190rpx}.guide-next{flex:1}
@media(max-width:350px){.guide-dialog{padding:22rpx}.guide-title{font-size:32rpx}.guide-description{font-size:24rpx}.guide-back{width:160rpx}}
</style>

<style scoped>
.guide-illustration{gap:14rpx;padding:18rpx}.guide-real-example{width:100%;display:flex;align-items:center;justify-content:center;gap:12rpx}.guide-sample{flex:1;min-width:0;text-align:center}.guide-sample image{width:100%;height:180rpx;background:white;border-radius:16rpx}.guide-sample text{display:block;font-size:20rpx;color:var(--ink);margin-top:8rpx}.guide-arrow{font-size:30rpx;color:var(--muted);flex-shrink:0}.guide-queue-example{display:flex;align-items:center;gap:18rpx;width:100%;padding:18rpx;background:white;border-radius:18rpx}.guide-queue-example image{width:120rpx;height:144rpx;flex-shrink:0}.guide-queue-example text{display:block;font-size:21rpx;line-height:1.9;color:var(--muted)}.guide-queue-example .guide-job-title{font-size:25rpx;color:var(--ink);font-weight:650}.guide-batch-photo{width:110rpx;height:110rpx;border-radius:14rpx}.guide-batch-image{width:250rpx;height:250rpx;border-radius:12rpx}.guide-credit{font-size:18rpx;line-height:1.6;padding:8rpx 0;color:var(--muted);text-align:left}.guide-body{height:690rpx}
</style>
