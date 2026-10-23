<template><button class="report" aria-label="举报模板内容" @click="report"><text>举报模板内容</text><text class="report-arrow" aria-hidden="true">›</text></button></template>
<script setup>
import {apiRequest} from '@/services/apiService'
const props=defineProps({templateKey:{type:String,required:true}})
const report=()=>{if(!uni.getStorageSync('gensticker.session.v1')?.access_token){uni.showToast({title:'请先到“我的”登录后提交',icon:'none'});return}uni.showModal({title:'举报模板',editable:true,placeholderText:'请描述问题（至少 2 个字）',confirmText:'提交',success:async r=>{if(!r.confirm)return;const reason=(r.content||'').trim();if(reason.length<2){uni.showToast({title:'请填写具体问题',icon:'none'});return}try{await apiRequest('/templates/reports',{method:'POST',data:{key:props.templateKey,reason:reason.slice(0,500)}},1);uni.showToast({title:'已记录，等待核查',icon:'none'})}catch(e){uni.showToast({title:e.message||'请先登录后提交',icon:'none'})}}})}
</script>
<style scoped>.report{display:flex;align-items:center;justify-content:space-between;width:100%;min-height:80rpx;padding:18rpx 0;font-size:23rpx;line-height:1.6;color:var(--muted);text-align:left;border-radius:12rpx}.report:active{background:var(--peach)}.report-arrow{font-size:30rpx;line-height:1;margin-left:20rpx}</style>
