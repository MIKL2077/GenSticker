const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm')
const ctx={API_BASE_URL:'https://www.shangkun.uk/gensticker/api'}
vm.createContext(ctx)
vm.runInContext(fs.readFileSync('src/services/shareCard.js','utf8').replace(/^import .*$/gm,'').replace(/export /g,''),ctx)
const card=ctx.shareCard()
assert.equal(card.imageUrl,'https://www.shangkun.uk/gensticker/api/share/cover-v2.jpg')
assert.equal(card.path,'/pages/index/index')
let hook
ctx.onShareAppMessage=callback=>{hook=callback}
vm.runInContext(fs.readFileSync('src/composables/useShareCard.js','utf8').replace(/^import .*$/gm,'').replace(/export /g,''),ctx)
ctx.useShareCard();assert.equal(hook().imageUrl,card.imageUrl)
const made=ctx.shareCard({template:'开心 & 你好',image:'wxfile://generated.png'})
assert.equal(made.imageUrl,'wxfile://generated.png')
assert.equal(made.path,'/pages/index/index?template='+encodeURIComponent('开心 & 你好'))
// Every shareable page has an explicit cover. Personal queues and account
// screens share the public landing page, never private screenshots or job IDs.
for(const page of ['my','recommend','library','queue','create','live']){
 const source=fs.readFileSync(`src/pages/${page}/index.vue`,'utf8')
 assert.ok(source.includes('useShareCard()'),page)
}
assert.ok(fs.readFileSync('src/pages/index/index.vue','utf8').includes('onShareAppMessage(()=>shareCard('))
console.log('PASS branded public share cover, original generated image, encoded template link and seven page integrations')
