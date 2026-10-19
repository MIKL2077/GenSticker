const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm')
const keys=Array.from({length:36},(_,i)=>`key${String(i).padStart(2,'0')}`).reverse()
const ordered=[...keys].sort((a,b)=>a.localeCompare(b))
const pending=new Map();let infoCalls=0,previews=0
const context={ref:value=>({value}),computed:getter=>({get value(){return getter()}}),onUnmounted:()=>{},Map,Set,Array,Promise,Math,console,
PAGINATION:{templatesPerPage:9},CATEGORY_UI_TO_API:{all:'all',text:'text_only',image:'image_only',mixed:'mixed'},
seedClientRecipes:()=>{},onThumbnailEvict:()=>()=>{},setThumbnailWindow:()=>{},getCategories:async()=>({all:keys,text_only:[],image_only:keys,mixed:[],cards:keys.map(key=>({key,name:'模板'+key,heat:key==='key00'?100:key==='key01'?90:key==='key02'?80:0,tags:[],params_type:{min_images:1,max_images:1,min_texts:0,max_texts:0,default_texts:[]},attribution:{source_url:'https://example.test/source'}}))}),
getTemplateInfo:async key=>{infoCalls++;return {key,keywords:['详情']}},getTemplatePreviewPath:key=>{previews++;return new Promise(resolve=>pending.set(key,resolve))}}
vm.createContext(context)
vm.runInContext(fs.readFileSync(path.join(__dirname,'../src/composables/useTemplateData.js'),'utf8').replace(/^import .*$/gm,'').replace(/export /g,''),context)
const timeout=setTimeout(()=>{console.error("FAIL paging promise did not settle");process.exitCode=1},3000)
;(async()=>{
const app=context.useTemplateData();await app.fetchMemeCategories()
assert.equal(app.currentPageTemplates.value.length,9);assert.ok(app.currentPageTemplates.value.every(x=>x.name.startsWith('模板')))
assert.equal(app.spotlight.value.map(t=>t.key).join(','),'key00,key01,key02')
app.selectedCategory.value='text';app.sortMode.value='explore'
assert.equal(app.spotlight.value.map(t=>t.key).join(','),'key00,key01,key02','ranking must be global and independent of category/sort')
app.selectedCategory.value='all';app.sortMode.value='hot'
const detail=await app.fetchMemeInfo(keys[0]);assert.equal(detail.imageCount,'1-1');assert.equal(detail.attribution.source_url,'https://example.test/source');assert.equal(infoCalls,0)
const background=app.ensurePageLoaded('all',2,true);assert.equal(app.isLoadingTemplates.value,false)
for(const resolve of pending.values())resolve('/local.png');pending.clear();await background
app.currentPage.value=2;const before=previews;await app.ensurePageLoaded('all',2)
assert.equal(previews,before);assert.equal(app.isLoadingTemplates.value,false);assert.ok(app.currentPageTemplates.value.every(x=>x.previewImage))
const foreground=app.ensurePageLoaded('all',3);assert.equal(app.isLoadingTemplates.value,true)
const speculative=app.ensurePageLoaded('all',4,true);assert.equal(app.isLoadingTemplates.value,true)
for(const [key,resolve] of pending){if(ordered.slice(27).includes(key)){resolve('/bg.png');pending.delete(key)}}await speculative
assert.equal(app.isLoadingTemplates.value,true)
for(const resolve of pending.values())resolve('/visible.png');pending.clear();await foreground
assert.equal(app.isLoadingTemplates.value,false);assert.equal(infoCalls,0)
console.log('PASS instant card names, cached page switches and background loads independent of foreground spinner')
})().catch(e=>{console.error(e);process.exitCode=1}).finally(()=>clearTimeout(timeout))
