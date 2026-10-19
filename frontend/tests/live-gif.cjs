const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm')
const gifenc=require('gifenc')
const source=fs.readFileSync(path.join(__dirname,'../src/services/liveGifService.js'),'utf8').replace(/^import .*$/gm,'').replace(/export /g,'')
async function verify(){
 const c={...gifenc,console,Promise,Date,Math,Uint8Array,Uint8ClampedArray,DataView,ArrayBuffer,Error,setTimeout,clearTimeout,Blob,URL,registerTemporary:p=>p,releaseTemporary:()=>{},writeOwnedFile:async()=>{}}
 vm.createContext(c);vm.runInContext(source+'\nthis.clip=clipWindow;this.supported=supportsLocalGif',c)
 assert.deepEqual(JSON.parse(JSON.stringify(c.clip(60,56,9))),{start:51,duration:9})
 assert.deepEqual(JSON.parse(JSON.stringify(c.clip(2,0,9))),{start:0,duration:2})
 assert.deepEqual(JSON.parse(JSON.stringify(c.clampCrop([.95,-1,.4,.6]))),[.6,0,.4,.6])
 const geo=c.cropPixels(1080,1920,[.2,.1,.5,.25]);assert.equal(geo.width,240);assert.equal(geo.height,213)
 const frames=[]
 for(let i=0;i<90;i++){const rgba=new Uint8Array(80*60*4);for(let y=0;y<60;y++)for(let x=0;x<80;x++){const at=(y*80+x)*4;rgba[at]=(x+i)%80<20?255:40;rgba[at+1]=80;rgba[at+2]=y*3;rgba[at+3]=255}frames.push(rgba)}
 const encoded=await c.encodeGifFrames(frames,80,60)
 assert.ok(encoded.bytes.length<=500*1024);assert.equal(Buffer.from(encoded.bytes.slice(0,6)).toString(),'GIF89a')
 fs.writeFileSync('/tmp/gensticker-local-test.gif',encoded.bytes)
 await assert.rejects(c.encodeGifFrames(frames,80,60,()=>{},()=>true),/取消/)
 const seeks=[],writes=[];let removed=false
 const nativeCanvas={width:1,height:1,getContext(){return {createImageData:(w,h)=>({data:new Uint8ClampedArray(w*h*4)}),putImageData:()=>{}}}}
 c.wx={createOffscreenCanvas:()=>nativeCanvas,createVideoDecoder:()=>({start:async options=>{assert.equal(options.mode,1);assert.equal(options.abortAudio,true)},seek:async ms=>seeks.push(ms),getFrameData:()=>({width:2,height:2,data:new Uint8Array(16).buffer}),stop:async()=>{},remove:async()=>{removed=true}})}
 const reader=await c.frameReader('/local.mp4');await reader.at(12.4);await reader.close();assert.deepEqual(seeks,[12400]);assert.ok(removed)
 c.document={};const still=new Uint8Array(20);c.fetch=async()=>({arrayBuffer:async()=>still.buffer});await assert.rejects(c.albumMotion('/still.jpg'),/静态照片/)
 const motion=new Uint8Array(40);motion[7]=24;motion.set(Buffer.from('ftypisom'),8);c.fetch=async()=>({arrayBuffer:async()=>motion.buffer});c.document={};c.URL={createObjectURL:()=>'/embedded.mp4'}
 assert.equal(await c.albumMotion('/motion.jpg'),'/embedded.mp4')
 console.log('PASS local GIF encoding, 9-second window, arbitrary crop, decoder millisecond seek, cancellation, embedded motion and album-only picker')
}
verify().catch(e=>{console.error(e);process.exitCode=1})
