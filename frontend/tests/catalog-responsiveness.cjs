const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path')
const cards=Array.from({length:1500},(_,i)=>({key:'template_'+i,name:'奶龙中文模板'+i,keywords:Array.from({length:100},(_,j)=>'关键词'+j),tags:['中文'],version:1,heat:1500-i,params_type:{min_images:0,max_images:0,min_texts:1,max_texts:1,default_texts:['你好']}}))
const data={all:cards.map(c=>c.key),text_only:cards.map(c=>c.key),cards}
let yields=0,heartbeats=0,catalog=data
const c={ref:value=>({value}),computed:get=>({get value(){return get()}}),onUnmounted:()=>{},console,PAGINATION:{templatesPerPage:9},CATEGORY_UI_TO_API:{all:'all',text:'text_only',image:'image_only',mixed:'mixed'},getCategories:async()=>catalog,seedClientRecipes:()=>{},onThumbnailEvict:()=>()=>{},setThumbnailWindow:()=>{},yieldToUI:()=>new Promise(resolve=>setImmediate(()=>{yields++;heartbeats++;resolve()})),uni:{getStorageSync:()=>null}}
vm.createContext(c);vm.runInContext(fs.readFileSync(path.join(__dirname,'../src/composables/useTemplateData.js'),'utf8').replace(/^import .*$/gm,'').replace(/export /g,''),c)
;(async()=>{const app=c.useTemplateData();await app.fetchMemeCategories();assert.equal(app.searchResultCount.value,1500);assert.ok(yields>=46);assert.equal(heartbeats,yields);app.setSearchQuery('奶龙 中文');assert.equal(app.searchResultCount.value,1500)
 const old=app.fetchMemeCategories();await new Promise(resolve=>setImmediate(resolve));catalog={all:['newest'],cards:[{...cards[0],key:'newest',name:'最新模板'}]};await app.fetchMemeCategories();await old;app.setSearchQuery('');assert.equal(app.currentPageTemplates.value[0].key,'newest');assert.equal(app.searchResultCount.value,1,'stale batches never replace a newer catalog')
 console.log('PASS 1500 templates / 150000 keywords yield to input between batches, searchable index and stale-refresh isolation')
})().catch(e=>{console.error(e);process.exitCode=1})
