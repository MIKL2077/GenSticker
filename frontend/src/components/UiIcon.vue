<template><image class="ui-icon" :src="'/static/icons/'+name+'-'+tone+'.png'" :style="{width:size+'rpx',height:size+'rpx'}" mode="aspectFit" aria-hidden="true"/></template>
<script setup>defineProps({name:{type:String,default:'spark'},tone:{type:String,default:'ink'},size:{type:Number,default:40}})</script>
<style scoped>.ui-icon{display:inline-block;vertical-align:middle;flex-shrink:0;pointer-events:none}</style>
