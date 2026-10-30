const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path')
const {GifReader,GifWriter}=require('omggif'),gifenc=require('gifenc')
const read=name=>fs.readFileSync(path.join(__dirname,'../src/services',name),'utf8').replace(/^import .*$/gm,'').replace(/export /g,'')
const colors=[0,0xff0000,0x0000ff,0x00ff00,0xffff00,0xff00ff,0xffffff,0]
function gif(frames,width=2,height=1){
 const buffer=new Uint8Array(100000),writer=new GifWriter(buffer,width,height,{palette:colors,loop:0})
 for(const frame of frames)writer.addFrame(frame.x||0,frame.y||0,frame.width||width,frame.height||height,Uint8Array.from(frame.pixels),{delay:10,...frame})
 return buffer.slice(0,writer.end())
}
const a=gif([{pixels:[1,1],delay:10},{pixels:[2,2],delay:30}])
const b=gif([{pixels:[3,3],delay:20},{pixels:[4,4],delay:40}])
class Canvas {
 constructor(){this.width=this.height=1;this.bytes=new Uint8ClampedArray(4)}
 storage(){if(this.bytes.length!==this.width*this.height*4)this.bytes=new Uint8ClampedArray(this.width*this.height*4);return this.bytes}
 getContext(){const canvas=this;return {
  fillStyle:'#fffaf4',
  fillRect(){const data=canvas.storage();for(let i=0;i<data.length;i+=4)data.set([255,250,244,255],i)},
  createImageData(w,h){return {width:w,height:h,data:new Uint8ClampedArray(w*h*4)}},
  putImageData(image){canvas.storage().set(image.data)},
  getImageData(){return {data:canvas.storage().slice()}},
  drawImage(image,x,y,w,h){
   const out=canvas.storage(),source=image.storage?image.storage():null
   for(let dy=Math.ceil(y);dy<y+h;dy++)for(let dx=Math.ceil(x);dx<x+w;dx++){
    const p=(dy*canvas.width+dx)*4,s=(Math.min(image.height-1,Math.floor((dy-y)*image.height/h))*image.width+Math.min(image.width-1,Math.floor((dx-x)*image.width/w)))*4
    const alpha=source?source[s+3]/255:1
    for(let c=0;c<3;c++)out[p+c]=Math.round((source?source[s+c]:[255,0,255][c])*alpha+out[p+c]*(1-alpha))
    out[p+3]=255
   }
  },
 }}
 createImage(){return {width:400,height:200,set src(value){this.value=value;queueMicrotask(()=>this.onload())},get src(){return this.value}}}
}
function context(files={'/opaque-temp':a,'/b.gif':b,'/still.png':Uint8Array.of(137,80,78,71)}){
 const canvases=[],written=[],released=[],progress=[]
 const c={...gifenc,GifReader,setTimeout,clearTimeout,Uint8Array,Uint8ClampedArray,Math,Error,Date,console,
  withStorageRecovery:task=>task(),registerTemporary:p=>p,releaseTemporary:p=>released.push(p),
  writeOwnedFile:async(p,data)=>written.push({path:p,bytes:new Uint8Array(data)}),
  uni:{env:{USER_DATA_PATH:'/user'},getFileSystemManager:()=>({
   stat:o=>o.success({stats:{size:files[o.path]?.length||0}}),
   readFile:o=>files[o.filePath]?o.success({data:files[o.filePath].buffer.slice(files[o.filePath].byteOffset,files[o.filePath].byteOffset+files[o.filePath].byteLength)}):o.fail(Error('missing input')),
  })},
  wx:{createOffscreenCanvas:()=>{const canvas=new Canvas();canvases.push(canvas);return canvas},canvasToTempFilePath:o=>o.success({tempFilePath:'/collage.jpg'})},
 }
 vm.createContext(c);vm.runInContext(read('collageGif.js')+read('resultCollage.js'),c)
 return {c,canvases,written,released,progress}
}
const rgb=(data,width,x,y)=>Array.from(data.slice((y*width+x)*4,(y*width+x)*4+3))
const near=(actual,expected)=>actual.forEach((value,i)=>assert.ok(Math.abs(value-expected[i])<9,`${actual} should match ${expected}`))
async function verify(){
 const {c,canvases,written,progress}=context()
 const result=await c.createResultCollage(['/opaque-temp','/b.gif','/still.png'],{onProgress:s=>progress.push(s)})
 assert.equal(result.animated,true);assert.equal(result.duration,600);assert.match(result.path,/collage_.*\.gif$/)
 assert.ok(result.bytes<2*1024*1024)
 const reader=new GifReader(written[0].bytes)
 assert.equal(reader.loopCount(),0);assert.ok(reader.numFrames()>1)
 const expectedA=[[255,0,0],[0,0,255],[0,0,255],[255,0,0],[0,0,255]]
 const expectedB=[[0,255,0],[0,255,0],[255,255,0],[255,255,0],[255,255,0]]
 assert.equal(reader.numFrames(),expectedA.length)
 let duration=0;const pixels=new Uint8ClampedArray(reader.width*reader.height*4)
 for(let i=0;i<reader.numFrames();i++){
  reader.decodeAndBlitFrameRGBA(i,pixels)
  if(i)assert.equal(reader.frameInfo(i).transparent_index,0,'unchanged pixels reuse the previous displayed frame')
  near(rgb(pixels,reader.width,132,132),expectedA[i]);near(rgb(pixels,reader.width,384,132),expectedB[i]);near(rgb(pixels,reader.width,132,384),[255,0,255])
  // A 2:1 GIF remains 2:1 and the untouched band stays the paper color.
  near(rgb(pixels,reader.width,132,20),[255,250,244]);duration+=reader.frameInfo(i).delay*10
 }
 assert.equal(duration,600,'entire longest animation survives composition')
 assert.ok(progress.at(-1).includes('已完成'));assert.ok(canvases.every(canvas=>canvas.width===1&&canvas.height===1),'all source and output canvases are released')
 const still=await c.createResultCollage(['/still.png','/still.png','/still.png'])
 assert.equal(still.path,'/collage.jpg');assert.equal(still.animated,false);assert.equal(still.width,688);assert.equal(still.height,688)
 const single=gif([{pixels:[1,1]}]);const singleContext=context({'/one.gif':single})
 assert.equal((await singleContext.c.createResultCollage(['/one.gif'])).animated,false,'one-frame GIF is static')

 // Restore-to-background and restore-to-previous are required for patch GIFs.
 const patch=gif([{pixels:[1,1],disposal:1},{pixels:[2],width:1,disposal:2,transparent:0},{pixels:[3],x:1,width:1,disposal:3,transparent:0},{pixels:[4],width:1,transparent:0}])
 const source=c.openCollageGif(patch)
 assert.deepEqual(Array.from(source.at(0)),[255,0,0,255,255,0,0,255])
 assert.deepEqual(Array.from(source.at(100)),[0,0,255,255,255,0,0,255])
 assert.deepEqual(Array.from(source.at(200)),[0,0,0,0,0,255,0,255])
 assert.deepEqual(Array.from(source.at(300)),[255,255,0,255,255,0,0,255],'disposal 3 restores the prior composited frame')
 assert.deepEqual(Array.from(source.at(400)),[255,0,0,255,255,0,0,255],'loop starts with a fresh logical canvas');source.close()
 const defaults=c.openCollageGif(gif([{pixels:[1,1],delay:0},{pixels:[2,2],delay:1}]))
 assert.equal(defaults.duration,200);defaults.close()
 const timeline=Array.from(c.collageTimeline([{animated:true,duration:15000,delays:Array(750).fill(20)}]))
 assert.ok(timeline.length<=301);assert.equal(timeline[0],0);assert.equal(timeline.at(-1),15000)
 assert.ok(timeline.every((t,i)=>!i||t>timeline[i-1]))
 assert.throws(()=>c.openCollageGif(a.slice(0,-1)),/无法读取/)
 assert.throws(()=>c.openCollageGif(gif([{pixels:[1,1],delay:1000},{pixels:[2,2],delay:1000}])),/15 秒/)
 const huge=a.slice();huge[6]=255;huge[7]=255;huge[8]=255;huge[9]=255
 assert.throws(()=>c.openCollageGif(huge),/尺寸或帧数/)
 await assert.rejects(c.createResultCollage([]),/请选择/)
 await assert.rejects(c.createResultCollage(Array(10).fill('/still.png')),/请选择/)
 const bad=context({'/bad.gif':a.slice(0,-1)})
 await assert.rejects(bad.c.createResultCollage(['/bad.gif']),/无法读取/);assert.equal(bad.written.length,0,'bad GIF never becomes a silent still collage')
 let cancelled=false;const cancel=context()
 await assert.rejects(cancel.c.createResultCollage(['/opaque-temp'],{cancelled:()=>cancelled,onProgress:s=>{if(s.includes('%'))cancelled=true}}),/取消/)
 assert.equal(cancel.written.length,0);assert.ok(cancel.canvases.every(canvas=>canvas.width===1&&canvas.height===1))
 const late=context();late.c.writeOwnedFile=async()=>{cancelled=true};cancelled=false
 await assert.rejects(late.c.createResultCollage(['/opaque-temp'],{cancelled:()=>cancelled}),/取消/)
 assert.equal(late.released.length,1,'cancel after writing deletes the new GIF')
 const oversized=context();oversized.c.uni.getFileSystemManager=()=>({stat:o=>o.success({stats:{size:8*1024*1024+1}}),readFile:()=>{throw Error('oversized input must not be read')}})
 await assert.rejects(oversized.c.createResultCollage(['/oversized']),/8 MB/);assert.equal(oversized.written.length,0)
 const noCanvas=context();noCanvas.c.wx.createOffscreenCanvas=undefined
 await assert.rejects(noCanvas.c.createResultCollage(['/opaque-temp']),/暂不支持拼图/)
 const failed=context();failed.c.writeOwnedFile=async()=>{throw Error('quota exceeded')}
 await assert.rejects(failed.c.createResultCollage(['/opaque-temp']),/quota/);assert.equal(failed.released.length,1)
 // An oversized first attempt must retry with the same complete duration.
 const retry=context();let attempts=0
 retry.c.GIFEncoder=()=>{const real=gifenc.GIFEncoder(),oversized=++attempts===1;return {...real,bytesView:()=>oversized?new Uint8Array(2*1024*1024+1):real.bytesView()}}
 const retried=await retry.c.createResultCollage(['/opaque-temp','/b.gif'])
 assert.equal(attempts,2);assert.equal(retried.duration,600)
 const again=new GifReader(retry.written[0].bytes)
 assert.equal(Array.from({length:again.numFrames()},(_,i)=>again.frameInfo(i).delay*10).reduce((a,b)=>a+b),600)
 // Browser previews use a typed GIF Blob rather than a JPEG canvas snapshot.
 const browser=context(),blobs=[]
 browser.c.Blob=Blob;browser.c.URL={createObjectURL:blob=>{blobs.push(blob);return 'blob:collage-'+blobs.length}}
 browser.c.document={createElement:()=>{const canvas=new Canvas();browser.canvases.push(canvas);canvas.toBlob=(done,type)=>done(new Blob([Uint8Array.of(255,216,255)],{type}));return canvas}}
 browser.c.Image=function(){return new Canvas().createImage()}
 browser.c.fetch=async file=>({ok:true,blob:async()=>new Blob([file==='/opaque-temp'?a:Uint8Array.of(137,80,78,71)])})
 const web=await browser.c.createResultCollage(['/opaque-temp','/still.png'])
 assert.equal(web.animated,true);assert.equal(web.path,'blob:collage-1');assert.equal(blobs[0].type,'image/gif');assert.ok(new GifReader(new Uint8Array(await blobs[0].arrayBuffer())).numFrames()>1)
 const webStill=await browser.c.createResultCollage(['/still.png'])
 assert.equal(webStill.animated,false);assert.equal(blobs[1].type,'image/jpeg');assert.ok(browser.canvases.every(canvas=>canvas.width===1&&canvas.height===1))
 console.log('PASS real GIF composition: independent timing, looping, mixed stills, aspect ratio, disposal 2/3, bounded timeline, full-duration compression, cancellation, cleanup and corrupt-input refusal')
}
verify().catch(error=>{console.error(error);process.exitCode=1})
