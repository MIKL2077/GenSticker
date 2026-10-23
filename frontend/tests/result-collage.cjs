const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path')
const source=fs.readFileSync(path.join(__dirname,'../src/services/resultCollage.js'),'utf8').replace(/^import .*$/gm,'').replace(/export /g,'')
async function verify(){
 let canvas,draws=[],dimensions
 const c={withStorageRecovery:task=>task(),setTimeout,clearTimeout,Math,Error,registerTemporary:p=>p,wx:{createOffscreenCanvas:()=>canvas={width:0,height:0,getContext:()=>({fillRect:()=>{},drawImage:(image,...args)=>draws.push({src:image.src,args})}),createImage:()=>({width:400,height:200,set src(value){this.value=value;queueMicrotask(()=>this.onload())},get src(){return this.value}})},canvasToTempFilePath:options=>{dimensions=[canvas.width,canvas.height];options.success({tempFilePath:'/collage.jpg'})}}}
 vm.createContext(c);vm.runInContext(source,c)
 assert.equal(await c.createResultCollage(['/a.gif','/b.png','/c.gif']),'/collage.jpg');assert.deepEqual(dimensions,[688,688]);assert.deepEqual(draws.map(draw=>draw.src),['/a.gif','/b.png','/c.gif'])
 for(const {args} of draws)assert.equal(args[2]/args[3],2,'collage preserves image aspect ratio')
 assert.equal(canvas.width,1);assert.equal(canvas.height,1,'canvas backing memory is released')
 c.wx.canvasToTempFilePath=options=>options.fail(Error('export failed'));await assert.rejects(c.createResultCollage(['/a.gif']),/export failed/);assert.equal(canvas.width,1)
 await assert.rejects(c.createResultCollage([]),/请选择/)
 console.log('PASS collage includes every selected original in order, preserves aspect ratio, bounds memory and releases failed exports')
}
verify().catch(error=>{console.error(error);process.exitCode=1})
