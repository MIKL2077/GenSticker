const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm')
const source=fs.readFileSync(path.join(__dirname,'../src/services/generationUpload.js'),'utf8').replace(/^import .*$/gm,'').replace(/export /g,'')
;(async()=>{
 const original=new Uint8ClampedArray([200,90,40,0,120,60,30,64,80,50,20,200,100,70,30,255]),exports=[],released=[],files=new Map()
 let animated=false,opaque=false,failMask=false,lastCanvas
 const context={console,setTimeout,clearTimeout,Uint8Array,Error,registerTemporary:p=>p,releaseTemporary:p=>released.push(p),withStorageRecovery:fn=>fn(),uni:{
  getImageInfo:o=>o.success({width:2,height:2,type:animated?'gif':'png'}),
  getFileSystemManager:()=>({stat:o=>o.success({stats:{size:10}}),readFile:o=>o.success({data:files.get(o.filePath)||'original-animation'})})
 },wx:{createOffscreenCanvas:()=>{
  const canvas={width:1,height:1,createImage(){return {width:2,height:2,set src(value){queueMicrotask(()=>this.onload())}}},getContext(){return {drawImage(){canvas.pixels=new Uint8ClampedArray(original);if(opaque)for(let i=3;i<16;i+=4)canvas.pixels[i]=255},getImageData(){return {data:canvas.pixels}},putImageData(p){canvas.pixels=p.data}}}}
  lastCanvas=canvas;return canvas
 },canvasToTempFilePath:o=>{if(failMask&&o.fileType==='png')return o.fail(Error('export failed'));exports.push({type:o.fileType,pixels:[...o.canvas.pixels],quality:o.quality});const p='/owned-'+exports.length;files.set(p,o.fileType==='jpg'?'encoded-colour':'encoded-alpha');o.success({tempFilePath:p})}}}
 vm.createContext(context);vm.runInContext(source,context)
 const result=await context.encodeGenerationImages(['/original-cutout'])
 assert.deepEqual(JSON.parse(JSON.stringify(result)),{images:['encoded-colour'],image_masks:['encoded-alpha']})
 assert.deepEqual(exports[0].pixels.filter((_,i)=>i%4===3),[255,255,255,255])
 assert.deepEqual(exports[1].pixels,[0,0,0,255,64,64,64,255,200,200,200,255,255,255,255,255])
 assert.deepEqual([...original],[200,90,40,0,120,60,30,64,80,50,20,200,100,70,30,255],'editing source is unchanged')
 assert.deepEqual(released,['/owned-1','/owned-2']);assert.equal(lastCanvas.width,1);assert.equal(lastCanvas.height,1)
 opaque=true;assert.deepEqual(JSON.parse(JSON.stringify(await context.encodeGenerationImages(['/opaque']))),{images:['encoded-colour']})
 animated=true;const count=exports.length;assert.equal((await context.encodeGenerationImage('/animated.gif')).image,'original-animation');assert.equal(exports.length,count)
 animated=false;opaque=false;failMask=true
 await assert.rejects(context.encodeGenerationImage('/export-failure'),/export failed/)
 assert.equal(lastCanvas.width,1);assert.ok(released.includes('/owned-'+exports.length));assert.ok(!released.includes('/original-cutout'))
 assert.deepEqual(JSON.parse(JSON.stringify(await context.encodeGenerationImages([]))),{images:[]})
 console.log('PASS compressed colour, lossless alpha separation, opaque/GIF compatibility, original retention and cleanup on export failure')
})().catch(error=>{console.error(error);process.exitCode=1})
