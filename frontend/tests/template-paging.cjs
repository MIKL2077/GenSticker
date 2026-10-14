const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm')
const keys=Array.from({length:36},(_,i)=>`key${String(i).padStart(2,'0')}`).reverse()
const pending=new Map();let infoCalls=0,previews=0
const context={ref:value=>({value}),computed:getter=>({get value(){return getter()}}),onUnmounted:()=>{},Map,Set,Array,Promise,Math,console,
PAGINATION:{templatesPerPage:9},CATEGORY_UI_TO_API:{all:'all',text:'text_only',image:'image_only',mixed:'mixed'},
seedClientRecipes:()=>{},onThumbnailEvict:()=>()=>{},setThumbnailWindow:()=>{},getCategories:async()=>({all:keys,text_only:[],image_only:keys,mixed:[],cards:keys.map(key=>({key,name:'模板'+key,tags:[]}))}),
getTemplateInfo:async key=>{infoCalls++;return {key,keywords:['详情']}},getTemplatePreviewPath:key=>{previews++;return new Promise(resolve=>pending.set(key,resolve))}}
vm.createContext(context)
vm.runInContext(fs.readFileSync(path.join(__dirname,'../src/composables/useTemplateData.js'),'utf8').replace(/^import .*$/gm,'').replace(/export /g,''),context)
;(async()=>{
const app=context.useTemplateData();await app.fetchMemeCategories()
assert.equal(app.currentPageTemplates.value.length,9);assert.ok(app.currentPageTemplates.value.every(x=>x.name.startsWith('模板')))
const background=app.ensurePageLoaded('all',2,true);assert.equal(app.isLoadingTemplates.value,false)
for(const resolve of pending.values())resolve('/local.png');pending.clear();await background
app.currentPage.value=2;const before=previews;await app.ensurePageLoaded('all',2)
assert.equal(previews,before);assert.equal(app.isLoadingTemplates.value,false);assert.ok(app.currentPageTemplates.value.every(x=>x.previewImage))
const foreground=app.ensurePageLoaded('all',3);assert.equal(app.isLoadingTemplates.value,true)
const speculative=app.ensurePageLoaded('all',4,true);assert.equal(app.isLoadingTemplates.value,true)
for(const [key,resolve] of pending){if(keys.slice(27).includes(key)){resolve('/bg.png');pending.delete(key)}}await speculative
assert.equal(app.isLoadingTemplates.value,true)
for(const resolve of pending.values())resolve('/visible.png');pending.clear();await foreground
assert.equal(app.isLoadingTemplates.value,false);assert.equal(infoCalls,0)
console.log('PASS instant card names, cached page switches and background loads independent of foreground spinner')
})().catch(e=>{console.error(e);process.exitCode=1})
