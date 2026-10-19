const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm')
let owner='alice',resolveMine
const owned=(id,time)=>({id,name:id,created_at:time,status:'private',preview_url:'/studio/templates/'+id+'/preview',creator:{name:'Alice'},params_type:{min_images:1,max_images:1,min_texts:0,max_texts:0,default_texts:[]}})
const c={ref:value=>({value}),computed:get=>({get value(){return get()}}),onUnmounted:()=>{},onThumbnailEvict:()=>()=>{},setThumbnailWindow:()=>{},seedClientRecipes:()=>{},console,PAGINATION:{templatesPerPage:9},CATEGORY_UI_TO_API:{all:'all',image:'image_only',text:'text_only',mixed:'mixed'},uni:{getStorageSync:()=>owner?{access_token:owner,profile:{id:owner}}:null},getCategories:async()=>({all:['popular','fresh'],image_only:['popular','fresh'],cards:[{key:'popular',name:'Popular',heat:100,created_at:1},{key:'fresh',name:'Fresh',heat:1,created_at:50}].map(card=>({...card,params_type:{min_images:1,max_images:1,min_texts:0,max_texts:0,default_texts:[]}}))}),getTemplatePreviewPath:async key=>'/public/'+key,privateImage:async key=>'/authenticated'+key,listMyTemplates:async()=>[owned('user_old',10),owned('user_new',30)]}
vm.createContext(c);vm.runInContext(fs.readFileSync(path.join(__dirname,'../src/composables/useTemplateData.js'),'utf8').replace(/^import .*$/gm,'').replace(/export /g,''),c)
async function verify(){
 const app=c.useTemplateData();await app.fetchMemeCategories();assert.equal(app.currentPageTemplates.value[0].key,'popular')
 app.sortMode.value='new';assert.equal(app.currentPageTemplates.value[0].key,'fresh')
 app.sortMode.value='cold';assert.equal(app.currentPageTemplates.value[0].key,'fresh')
 app.sortMode.value='old';assert.equal(app.currentPageTemplates.value[0].key,'popular')
 await app.loadMine(['fresh']);app.libraryMode.value='mine';app.sortMode.value='new'
 assert.deepEqual(Array.from(app.currentPageTemplates.value,t=>t.key),['fresh','user_new','user_old'])
 assert.equal(await app.fetchMemePreview('user_new'),'/authenticated/studio/templates/user_new/preview')
 c.listMyTemplates=()=>new Promise(resolve=>resolveMine=resolve)
 const stale=app.loadMine(['fresh']);await Promise.resolve();owner=null;await app.loadMine([]);resolveMine([owned('private-late',100)]);await stale
 assert.equal(app.currentPageTemplates.value.length,0,'logout immediately clears owned/favourite lists')
 assert.equal(app.templateDetails.value.has('user_new'),false,'previous owner metadata is evicted')
 assert.equal(app.templateDetails.value.has('private-late'),false,'late authenticated responses never repopulate private templates')
 console.log('PASS warehouse popularity/time sorting, owned plus favourite union, authenticated previews and stale-account isolation')
}
verify().catch(e=>{console.error(e);process.exitCode=1})
