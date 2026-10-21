const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path')
const source=fs.readFileSync(path.join(__dirname,'../src/services/localBackground.js'),'utf8').replace(/^import .*$/gm,'').replace(/export /g,'')
const area=320*320
function runtime({transparent=false,broken=false,capable=true}={}){
 const exports=[],requests=[],runs=[],destroyed=[]
 function canvas(width,height){
  let w=width,h=height,pixels=new Uint8ClampedArray(w*h*4),mode='source-over'
  const c={get width(){return w},set width(value){w=value;pixels=new Uint8ClampedArray(w*h*4)},get height(){return h},set height(value){h=value;pixels=new Uint8ClampedArray(w*h*4)},createImage:()=>({width:40,height:40,set src(value){this.path=value;queueMicrotask(()=>this.onload())}})}
  const ctx={createImageData:(w,h)=>({data:new Uint8ClampedArray(w*h*4)}),putImageData:image=>pixels.set(image.data),getImageData:()=>({data:pixels.slice()}),set globalCompositeOperation(value){mode=value},drawImage:(image,...args)=>{
   const [sx,sy,sw,sh,dx,dy,dw,dh]=args.length===8?args:[0,0,image.width,image.height,...(args.length===2?[...args,image.width,image.height]:args)]
   for(let y=0;y<dh;y++)for(let x=0;x<dw;x++){
    const tx=Math.min(w-1,Math.floor(dx+x)),ty=Math.min(h-1,Math.floor(dy+y)),index=(ty*w+tx)*4
    const ix=Math.min(image.width-1,Math.floor(sx+x/dw*sw)),iy=Math.min(image.height-1,Math.floor(sy+y/dh*sh))
    const rgba=image._pixels?image._pixels().slice((iy*image.width+ix)*4,(iy*image.width+ix)*4+4):[200,100,50,transparent&&(ix<10||ix>=30||iy<10||iy>=30)?0:255]
    if(mode==='destination-in')pixels[index+3]=Math.round(pixels[index+3]*rgba[3]/255)
    else pixels.set(rgba,index)
   }
  }}
  c.getContext=()=>ctx;c._pixels=()=>pixels;return c
 }
 const c={API_BASE_URL:'https://example.test',ArrayBuffer,Float32Array,Uint8ClampedArray,Promise,Math,Number,String,Date,Error,console,setTimeout:(fn,ms)=>{const timer=setTimeout(fn,ms);if(ms===90000)timer.unref();return timer},clearTimeout,
 uni:{env:{USER_DATA_PATH:'/user'},getDeviceInfo:()=>({platform:'ios'}),getImageInfo:o=>o.success({width:40,height:40}),getFileSystemManager:()=>({getFileInfo:o=>o.success({size:4574861,digest:'0a99236f0d5c1916a99a8c401b23e5ef32038606'})}),downloadFile:o=>{requests.push(o);throw Error('cached model must not download')}},
 wx:{createOffscreenCanvas:o=>canvas(o.width,o.height)}}
 if(capable)c.wx.createInferenceSession=options=>{
  assert.equal(typeof options.allowNPU,'boolean')
  return {onLoad:fn=>queueMicrotask(fn),onError:()=>{},destroy:()=>destroyed.push(true),run:async input=>{
   runs.push(input);if(broken)throw Error('unsupported operator')
   const data=new Float32Array(area);for(let y=80;y<240;y++)for(let x=80;x<240;x++)data[y*320+x]=1
   return {'1959':{type:'float32',shape:[1,1,320,320],data:data.buffer}}
  }}
 }

 vm.createContext(c);vm.runInContext(source,c)
 c.exportCanvas=async(canvas,type)=>{exports.push({width:canvas.width,height:canvas.height,pixels:canvas._pixels().slice(),type});return '/export-'+exports.length+'.'+type}
 return {c,exports,requests,runs,destroyed}
}
;(async()=>{
 const local=runtime();await local.c.warmLocalBackground()
 const output=await local.c.prepareForeground('/photo',local.c.exportCanvas)
 assert.equal(output.method,'device');assert.equal(local.runs.length,1);assert.equal(local.requests.length,0)
 const input=new Float32Array(local.runs[0]['input.1'].data);assert.equal(input.length,3*area);assert.ok(Math.abs(input[0]-(1-.485)/.229)<1e-5);assert.ok(Math.abs(input[area]-(.5-.456)/.224)<1e-5)
 const saved=local.exports.at(-1);assert.equal(saved.width,20);assert.equal(saved.height,20);assert.equal(saved.type,'png');assert.deepEqual(Array.from(saved.pixels.slice(0,4)),[200,100,50,255])
 const first=runtime();let stored=false
 first.c.uni.getFileSystemManager=()=>({getFileInfo:o=>o.filePath==='/downloaded-model'||stored?o.success({size:4574861,digest:'0a99236f0d5c1916a99a8c401b23e5ef32038606'}):o.fail({errMsg:'missing'}),unlink:o=>o.success(),saveFile:o=>{stored=true;o.success()}})
 first.c.uni.downloadFile=o=>{assert.equal(o.timeout,30000,'model downloads may finish in background on slow networks');o.success({statusCode:200,tempFilePath:'/downloaded-model'})}
 const warm=first.c.warmLocalBackground();assert.equal(first.c.warmLocalBackground(),warm,'first download/compile is shared');await warm;assert.equal(stored,true)
 const npu=runtime(),factory=npu.c.wx.createInferenceSession,attempts=[];let failedSessionDestroyed=false
 npu.c.wx.createInferenceSession=options=>{attempts.push(options.allowNPU);if(options.allowNPU)return{onLoad:()=>{},onError:fn=>queueMicrotask(()=>fn(Error('unsupported NPU operator'))),destroy:()=>{failedSessionDestroyed=true}};return factory(options)}
 await npu.c.warmLocalBackground();assert.deepEqual(attempts,[true,false]);assert.equal(failedSessionDestroyed,true)
 assert.equal((await npu.c.prepareForeground('/photo',npu.c.exportCanvas)).method,'device','NPU load failure can still complete on the device')
 const alpha=runtime({transparent:true});const reused=await alpha.c.prepareForeground('/transparent',alpha.c.exportCanvas);assert.equal(reused.method,'alpha');assert.equal(alpha.runs.length,0);assert.equal(alpha.exports[0].width,20)
 const unsupported=runtime({capable:false});const fallback=await unsupported.c.prepareForeground('/photo',unsupported.c.exportCanvas);assert.equal(fallback.method,'server');assert.equal(unsupported.exports[0].type,'jpg');assert.equal(unsupported.runs.length,0)
 const broken=runtime({broken:true});await broken.c.warmLocalBackground();assert.equal((await broken.c.prepareForeground('/photo',broken.c.exportCanvas)).method,'server');assert.equal(broken.destroyed.length,1)
 assert.throws(()=>local.c.predictionMask({type:'float32',shape:[1,1,320,320],data:new Float32Array(area).buffer}),/不明确/)
 assert.throws(()=>local.c.predictionMask({type:'float32',shape:[1,1,320,320],data:new Float32Array([NaN]).buffer}),/尺寸/)
 console.log('PASS device tensor normalization, alpha mask/crop, transparent local reuse, cached model, unsupported/failing inference fallback and canvas cleanup')
})().catch(error=>{console.error(error);process.exitCode=1})
