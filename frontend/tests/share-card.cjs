const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm')
let randomValue=0,randomCalls=0
const ctx={API_BASE_URL:'https://www.shangkun.uk/gensticker/api',Math:{floor:Math.floor,random:()=>{randomCalls++;return randomValue}}}
vm.createContext(ctx)
vm.runInContext(fs.readFileSync('src/services/shareCard.js','utf8').replace(/^import .*$/gm,'').replace(/export /g,''),ctx)
const card=ctx.shareCard()
assert.equal(card.imageUrl,'https://www.shangkun.uk/gensticker/api/share/cover-v2.jpg')
assert.equal(card.path,'/pages/index/index')
const hook=()=>ctx.shareCard()
assert.equal(hook().imageUrl,'https://www.shangkun.uk/gensticker/api/share/cover-v3.jpg')
const used=new Set([card.imageUrl]);let previous=hook().imageUrl
used.add(previous)
for(const value of [0,.25,.5,.75,.999999,0,.999999,.5,.999999]) {
 randomValue=value
 const next=hook().imageUrl
 assert.notEqual(next,previous,'consecutive share callbacks should choose different covers')
 assert.match(next,/\/share\/cover-v[2-5]\.jpg$/)
 used.add(next);previous=next
}
assert.equal(used.size,4,'all four covers must be reachable')
const callsBefore=randomCalls
const made=ctx.shareCard({template:'开心 & 你好',image:'wxfile://generated.png'})
assert.equal(made.imageUrl,'wxfile://generated.png')
assert.equal(made.path,'/pages/index/index?template='+encodeURIComponent('开心 & 你好'))
assert.equal(randomCalls,callsBefore,'explicit generated image must bypass random cover selection')
// Every shareable page has an explicit cover. Personal queues and account
// screens share the public landing page, never private screenshots or job IDs.
for(const page of ['my','recommend','library','queue','create','live']){
 const source=fs.readFileSync(`src/pages/${page}/index.vue`,'utf8')
 assert.ok(source.includes('onShareAppMessage(()=>shareCard())'),page+' must register the native share hook directly for the uni-app compiler')
}
assert.ok(fs.readFileSync('src/pages/index/index.vue','utf8').includes('onShareAppMessage(()=>shareCard('))
console.log('PASS four random covers, no consecutive repeats, per-share selection, original generated image, encoded template link and seven page integrations')
