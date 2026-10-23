<template><view v-if="show" class="preview-modal" @click="queueTap"><view class="preview-content" @click.stop="queueTap"><view class="preview-header"><view><text class="ui-kicker">{{isGenerating?'A LITTLE MAGIC':'MADE BY YOU'}}</text><text class="preview-title">{{isGenerating?'表情正在酝酿中':'你的表情，出炉啦'}}</text></view><button class="ui-close" :aria-label="isGenerating?'双击放入生成队列':'关闭预览'" @click.stop="closeAction">×</button></view><view v-if="isGenerating" class="generating-container"><view class="making-mascot"><ui-icon name="spark" :size="90" tone="accent"/><view class="orbit-star">✦</view></view><text class="loading-text">给小情绪加一点魔法…</text><button class="queue-double-tap" :class="{armed:queueTapHint}" :aria-label="queueTapHint?'再点一次，放入生成队列':'双击放入生成队列'" hover-class="queue-button-pressed" @click.stop="queueTap"><view class="queue-button-icon" aria-hidden="true"><view class="queue-sheet queue-sheet-back"/><view class="queue-sheet queue-sheet-front"><view/><view/></view></view><text class="queue-button-label">放入生成队列</text><text class="queue-button-hint">{{queueTapHint?'再点一次':'双击收起'}}</text></button><text class="queue-caption">后台继续制作 · 完成后提醒你</text></view><view v-else-if="image" class="meme-result"><image :src="image" class="meme-image" mode="aspectFit" @click="previewImage"/><text class="result-note">点击图片放大 · 适配版长边 ≤240 px、≤500 KB，可能降低清晰度或流畅度；能否添加仍以微信为准</text><view class="meme-actions"><button class="ui-secondary" @click="$emit('share')"><ui-icon name="share" tone="accent" :size="30"/> 发原图给好友</button><button class="ui-primary" @click="$emit('save')"><ui-icon name="download" tone="white" :size="30"/> 保存相册</button></view><button v-if="allowEdit" class="edit-again ui-secondary" @click="$emit('edit')">重新编辑</button></view></view></view></template>
<script>
import UiIcon from '@/components/UiIcon.vue';
export default {
 components:{UiIcon},name:'PreviewModal',
 props:{show:{type:Boolean,required:true},isGenerating:{type:Boolean,required:true},image:{type:String,default:''},allowEdit:{type:Boolean,default:true}},
 emits:['close','save','share','edit'],
 data:()=>({queueTapAt:null,queueTapHint:false,queueTapTimer:null}),
 watch:{show(){this.resetQueueTap()},isGenerating(){this.resetQueueTap()}},
 beforeUnmount(){this.resetQueueTap()},
 methods:{
  resetQueueTap(){clearTimeout(this.queueTapTimer);this.queueTapAt=null;this.queueTapHint=false},
  queueTap(){
   if(!this.show||!this.isGenerating)return
   const now=Date.now()
   if(this.queueTapAt!==null&&now-this.queueTapAt<=600){this.resetQueueTap();this.$emit('close');return}
   this.resetQueueTap();this.queueTapAt=now;this.queueTapHint=true;this.queueTapTimer=setTimeout(()=>this.resetQueueTap(),600)
  },
  closeAction(){if(this.isGenerating)this.queueTap();else this.$emit('close')},
  previewImage(){if(this.image)uni.previewImage({urls:[this.image],current:this.image})},
 },
}
</script>
<style scoped>
.preview-modal{position:fixed;inset:0;z-index:2400;background:rgba(29,43,47,.48);display:flex;align-items:center;justify-content:center;padding:28rpx}.preview-content{background:var(--paper);border-radius:38rpx;width:100%;max-width:700rpx;max-height:calc(100% - env(safe-area-inset-top) - env(safe-area-inset-bottom));overflow-y:auto;animation:ui-sheet .24s ease-out}.preview-header{display:flex;justify-content:space-between;align-items:center;gap:16rpx;padding:30rpx 28rpx 18rpx}.preview-title{display:block;font-size:32rpx;font-weight:750;margin-top:8rpx}.generating-container{padding:38rpx 28rpx 54rpx;text-align:center}.making-mascot{width:150rpx;height:150rpx;margin:0 auto 35rpx;background:#ffe8ae;color:#755f39;border-radius:48rpx;position:relative;display:flex;align-items:center;justify-content:center;animation:ui-float 2.8s ease-in-out infinite}.making-mascot>text{font-size:96rpx;line-height:1}.orbit-star{position:absolute;right:-20rpx;top:-18rpx;color:var(--accent);font-size:52rpx}.loading-text{display:block;color:var(--ink);font-size:28rpx;font-weight:600}.meme-result{padding:12rpx 28rpx 30rpx}.meme-image{width:100%;height:390rpx;max-height:40vh;background:#f0ede4;border-radius:24rpx}.result-note{display:block;text-align:center;font-size:21rpx;color:#8d958b;margin-top:12rpx}.edit-again{min-height:80rpx;font-size:25rpx;color:var(--accent-dark);line-height:1.5;padding:20rpx}.meme-actions{display:flex;gap:14rpx}.meme-actions .ui-primary{flex:2}.meme-actions .ui-secondary{flex:1;display:flex;align-items:center;justify-content:center}
.preview-content{border:3rpx solid #fff;background:var(--paper);box-shadow:0 12rpx 0 rgba(79,57,112,.2)}
.meme-image{animation:ui-enter .4s ease-out both}.result-note{animation:ui-reveal .4s ease-out .15s both}.meme-actions{animation:ui-enter .35s ease-out .1s both}.making-mascot{box-shadow:0 8rpx 0 #e7c67e,inset 0 3rpx 0 #fff7d9}
.meme-actions{flex-wrap:wrap}.meme-actions button{gap:10rpx;font-size:24rpx;flex:1!important}/* Keep the action compact; the gesture hint has its own stable space. */
.queue-double-tap{display:flex;align-items:center;justify-content:center;gap:16rpx;width:100%;max-width:510rpx;min-height:92rpx;margin:28rpx auto 0;padding:20rpx 22rpx;border:2rpx solid #ffb899;border-radius:26rpx;background:linear-gradient(135deg,#ff9c7c,#f37557);box-shadow:0 6rpx 0 #cd6549,inset 0 2rpx 0 #ffd2bc;color:#fff;line-height:1.5;transition:background .18s ease,box-shadow .18s ease,transform .18s ease}
.queue-button-icon{position:relative;width:34rpx;height:34rpx;flex-shrink:0}
.queue-sheet{position:absolute;width:25rpx;height:28rpx;border:2rpx solid currentColor;border-radius:5rpx}
.queue-sheet-back{left:0;bottom:0;opacity:.65}
.queue-sheet-front{right:0;top:0;background:#fa8b6a;padding:7rpx 4rpx}
.queue-sheet-front>view{height:2rpx;background:currentColor;border-radius:2rpx;margin-bottom:4rpx}
.queue-button-label{font-size:27rpx;font-weight:750;white-space:nowrap}
.queue-button-hint{min-width:102rpx;padding:5rpx 10rpx;border:1rpx solid #ffffff66;border-radius:12rpx;background:#ffffff24;font-size:20rpx;white-space:nowrap;line-height:1.5}
.queue-double-tap.armed{background:linear-gradient(135deg,#f68a67,#df6446);box-shadow:0 3rpx 0 #b45139,inset 0 2rpx 0 #ffc5a7;transform:translateY(3rpx)}
.queue-double-tap.armed .queue-button-hint{background:#fff5e9;color:#b54b32;border-color:#fff5e9}
.queue-button-pressed{transform:translateY(3rpx)}
.queue-caption{display:block;font-size:22rpx;line-height:1.7;color:#9b8d77;margin-top:22rpx}
@media(max-width:350px){.queue-double-tap{gap:12rpx;padding:18rpx 16rpx}.queue-button-label{font-size:25rpx}.queue-button-hint{font-size:19rpx;min-width:96rpx}}
@media(prefers-reduced-motion:reduce){.making-mascot{animation:none}.queue-double-tap{transition:none}}
</style>

<style scoped>.edit-again{display:flex;align-items:center;justify-content:center;width:100%;margin-top:18rpx;min-height:88rpx;font-size:26rpx;line-height:1.6}</style>
