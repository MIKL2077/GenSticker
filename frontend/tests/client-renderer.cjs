const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path')
const draws=[],events=[],savedCanvases=[]
const recipe={supported:true,key:'auto_test',version:1,expires:Date.now()/1000+300,receipt:'signed',assets:{},attribution:{},spec:{width:128,height:128,background:'#ffffff',defaults:['你好'],layers:[{type:'subject',box:[0,0,128,96],slot:0,fit:'contain',color:'#222222'},{type:'text',box:[0,100,128,28],slot:0,value:'你好',fit:'contain',color:'#222222',font_size:20}]}}
let canvas,big=false
const ctx={fillRect:()=>{},save:()=>{},restore:()=>{},translate:()=>{},measureText:s=>({width:s.length*10}),fillText:(...a)=>draws.push(a),strokeText:(...a)=>draws.push(['stroke',...a]),drawImage:(...a)=>draws.push(a)}
const context={API_BASE_URL:'https://example.test/api',apiRequest:async url=>url.includes('/always/')?{supported:true,key:'always',version:1,layout:'always-normal-v1',assets:{},attribution:{},expires:Date.now()/1000+300,receipt:'signed'}:url.includes('/look_flat/')?{supported:true,key:'look_flat',version:1,layout:'look-flat-v1',assets:{},attribution:{},expires:Date.now()/1000+300,receipt:'signed'}:recipe,visitorHeaders:()=>({}),trackTemplate:(...a)=>events.push(a),console,Date,Map,Promise,Object,Number,String,Math,setTimeout,clearTimeout,
wx:{createOffscreenCanvas:o=>{canvas={...o,getContext:()=>ctx,createImage:()=>{const img={width:big?10000:80,height:big?10000:100};Object.defineProperty(img,'src',{set:()=>queueMicrotask(()=>img.onload())});return img}};return canvas},canvasToTempFilePath:o=>{savedCanvases.push([o.canvas.width,o.canvas.height]);o.success({tempFilePath:'/local.jpg'})}},uni:{getImageInfo:o=>o.success({width:big?10000:80,height:big?10000:100,type:'jpeg'})}}
vm.createContext(context)
vm.runInContext(fs.readFileSync(path.join(__dirname,'../src/services/clientRenderer.js'),'utf8').replace(/^import .*$/gm,'').replace(/export /g,''),context)
;(async()=>{
 assert.equal(await context.tryClientRender('auto_test',['/photo.jpg'],['标题']),'/local.jpg')
 assert.equal(events[0][1],'client_generate');assert.ok(draws.length>=2);assert.equal(canvas.width,1);assert.equal(canvas.height,1)
 recipe.attribution={origin:'chinesebqb',author:'Source author',license:'unverified',source_url:'https://example.test/'+'source/'.repeat(100)}
 draws.length=0
 assert.equal(await context.tryClientRender('auto_test',['/photo.jpg'],['标题']),'/local.jpg')
 assert.deepEqual(savedCanvases.at(-1),[128,128]);assert.ok(!draws.some(d=>String(d[0]).includes('Source author') || String(d[0]).includes('https://')))
 assert.equal(await context.tryClientRender('petpet',['/photo.jpg'],[]),null)
 const invalid=JSON.parse(JSON.stringify(recipe));invalid.spec.layers[0].box=[0,0,9999,96];assert.throws(()=>context.validateRecipe(invalid))
 recipe.spec.layers[1].weight='bold';recipe.spec.layers[1].align='center';recipe.spec.layers[1].stroke_width=2;recipe.spec.layers[1].stroke_color='#000000';recipe.spec.layers[1].color='#ffffff';
 assert.equal(await context.tryClientRender('auto_test',['/photo.jpg'],['新文字']),'/local.jpg');assert.ok(draws.some(d=>d[0]==='stroke'));assert.equal(ctx.textAlign,'left');
 const badStyle=JSON.parse(JSON.stringify(recipe));badStyle.spec.layers[1].stroke_width=9;assert.throws(()=>context.validateRecipe(badStyle));
 const executable=JSON.parse(JSON.stringify(recipe));executable.spec.layers[0].type='script';assert.throws(()=>context.validateRecipe(executable))
 const animated=JSON.parse(JSON.stringify(recipe));animated.spec.animation_asset='a'.repeat(64);assert.throws(()=>context.validateRecipe(animated),'native JPEG rendering must never flatten a reaction GIF')
 // A wrapped caption must draw every explicit line; independent captions keep
 // separate slots so editing one never silently replaces only half a meme.
 recipe.spec.layers[1].box=[0,0,128,58];recipe.spec.layers[1].max_lines=2;draws.length=0
 assert.equal(await context.tryClientRender('auto_test',['/photo.jpg'],['第一行\n第二行']),'/local.jpg')
 assert.ok(draws.some(d=>d[0]==='第一行'));assert.ok(draws.some(d=>d[0]==='第二行'))
 recipe.spec.layers.push({...recipe.spec.layers[1],box:[0,64,128,58],slot:1});draws.length=0
 assert.equal(await context.tryClientRender('auto_test',['/photo.jpg'],['上方新文案','下方新文案']),'/local.jpg')
 assert.ok(draws.some(d=>d[0]==='上方新文案'));assert.ok(draws.some(d=>d[0]==='下方新文案'))
 assert.equal(await context.tryClientRender('always',['/photo.jpg'],[]),'/local.jpg')
 assert.equal(await context.tryClientRender('look_flat',['/photo.jpg'],['可恶']),'/local.jpg')
 context.uni.getImageInfo=o=>o.success({width:80,height:100,type:'gif'});assert.equal(await context.tryClientRender('always',['/animated.gif'],[]),null)
 context.uni.getImageInfo=o=>o.success({width:10000,height:10000,type:'jpeg'});big=true;recipe.receipt='new-signed';assert.equal(await context.tryClientRender('auto_test',['/huge.png'],[]),null);assert.equal(canvas.width,1)
 console.log('PASS bounded DSL, local composition, success receipt, canvas release and oversized image fallback')
})().catch(e=>{console.error(e);process.exitCode=1})
