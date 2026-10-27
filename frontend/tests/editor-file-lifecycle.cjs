const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm')
const text=fs.readFileSync(path.join(__dirname,'../src/components/ImageEditor.vue'),'utf8').match(/<script setup>([\s\S]*?)<\/script>/)[1].replace(/^import .*$/gm,'')
const props={templateKey:'one',src:'/original.jpg',activeIndex:0},watchers=[],downloads=[],released=[],registered=[]
const c={Math,Error,defineProps:()=>props,defineEmits:()=>()=>{},ref:value=>({value}),computed:fn=>({get value(){return fn()}}),watch:(source,fn)=>watchers.push(fn),onBeforeUnmount:fn=>c.unmount=fn,
 registerTemporary:p=>{registered.push(p);return p},releaseTemporary:p=>released.push(p),withStorageRecovery:task=>task(),visitorHeaders:()=>({}),apiRequest:async()=>({overlay_url:'/owned-guide.png'}),API_BASE_URL:'https://public.test',
 uni:{getWindowInfo:()=>({windowWidth:375,windowHeight:812}),downloadFile:o=>downloads.push(o)}}
vm.createContext(c);vm.runInContext(text,c)
const flush=()=>new Promise(resolve=>setImmediate(resolve))
;(async()=>{
 const first=watchers[2]('one');await flush();downloads.shift().success({statusCode:200,tempFilePath:'/overlay-one.png'});await first
 assert.equal(vm.runInContext('overlay.value',c),'/overlay-one.png')
 props.templateKey='two';const second=watchers[2]('two');await flush();assert.ok(released.includes('/overlay-one.png'))
 c.unmount();downloads.shift().success({statusCode:200,tempFilePath:'/late-overlay.png'});await second
 assert.ok(registered.includes('/late-overlay.png')&&released.includes('/late-overlay.png'),'late response after unmount is reclaimed')
 props.templateKey='three';const denied=watchers[2]('three');await flush();downloads.shift().success({statusCode:403,tempFilePath:'/error-body.tmp'});await denied
 assert.ok(released.includes('/error-body.tmp'));assert.equal(vm.runInContext('guide.value.generic',c),true)
 assert.ok(!released.includes('/original.jpg'))
 console.log('PASS editor overlay replacement, unmount, late response, HTTP error cleanup and source retention')
})().catch(error=>{console.error(error);process.exitCode=1})
