import { apiRequest } from '@/services/apiService'
import { API_BASE_URL } from '@/constants'
import { visitorHeaders, trackTemplate } from '@/services/popularityService'

const recipes = new Map(), assets = new Map(), inflight = new Map()
let assetBytes = 0, rendering = false

function assetPath(hash, path) {
  if (!/^[a-f0-9]{64}$/.test(hash) || path !== `/template-assets/${hash}.png`) throw new Error('素材地址无效')
  const hit = assets.get(hash)
  if (hit) { assets.delete(hash); assets.set(hash,hit); return Promise.resolve(hit.path) }
  if(inflight.has(hash)) return inflight.get(hash)
  const task = new Promise((resolve,reject) => uni.downloadFile({ url:`${API_BASE_URL}${path}`, timeout:10000, success:r=>{
    if(r.statusCode!==200) return reject(new Error('本地素材暂不可用'))
    const fs=uni.getFileSystemManager()
    fs.stat({path:r.tempFilePath,success:s=>{
      if(s.stats.size>1024*1024) { fs.unlink({filePath:r.tempFilePath,fail:()=>{}}); return reject(new Error('素材过大')) }
      assets.set(hash,{path:r.tempFilePath,bytes:s.stats.size}); assetBytes+=s.stats.size
      while(assetBytes>8*1024*1024 || assets.size>24) { const oldest=assets.keys().next().value, old=assets.get(oldest);assets.delete(oldest);assetBytes-=old.bytes;fs.unlink({filePath:old.path,fail:()=>{}}) }
      resolve(r.tempFilePath)
    },fail:reject})
  },fail:reject})).finally(()=>inflight.delete(hash))
  inflight.set(hash,task); return task
}

export async function prefetchClientTemplate(key) {
  if(!key.startsWith('auto_') || typeof wx==='undefined' || !wx.createOffscreenCanvas) return null
  const cached=recipes.get(key)
  if(cached && cached.expires>Date.now()/1000+30 && cached.receipt) return cached
  const recipe=await apiRequest(`/memes/${encodeURIComponent(key)}/client-template`,{header:visitorHeaders()},1)
  if(!recipe.supported) return null
  validateRecipe(recipe)
  // Serial downloads bound decoded material preparation and API concurrency.
  for(const [hash,path] of Object.entries(recipe.assets)) await assetPath(hash,path)
  recipes.set(key,recipe)
  while(recipes.size>16) recipes.delete(recipes.keys().next().value)
  return recipe
}

export function validateRecipe(recipe) {
  const s=recipe.spec
  if(!s || !Number.isInteger(s.width) || !Number.isInteger(s.height) || s.width<64 || s.height<64 || s.width>768 || s.height>768 || !/^#[a-f0-9]{6}$/i.test(s.background) || !Array.isArray(s.layers) || s.layers.length>12 || s.layers.length<1) throw new Error('模板超出本地能力')
  for(const l of s.layers) {
    if(!['asset','subject','text'].includes(l.type) || !Array.isArray(l.box) || l.box.length!==4 || l.box.some(v=>!Number.isInteger(v))) throw new Error('模板图层无效')
    const [x,y,w,h]=l.box
    if(x<0 || y<0 || w<=0 || h<=0 || x+w>s.width || y+h>s.height || !['contain','cover'].includes(l.fit) || !Number.isInteger(l.slot) || l.slot<0 || l.slot>1 || !/^#[a-f0-9]{6}$/i.test(l.color)) throw new Error('模板图层越界')
    if(l.type==='asset' && (!/^[a-f0-9]{64}$/.test(l.value) || !recipe.assets[l.value])) throw new Error('模板素材无效')
    if(l.type==='text' && (!Number.isInteger(l.font_size) || l.font_size<10 || l.font_size>100)) throw new Error('文字图层无效')
  }
}

function wrap(ctx,value,width) {
  const lines=[];let line=''
  for(const c of String(value)) { if(c==='\n' || ctx.measureText(line+c).width>width){lines.push(line);line=c==='\n'?'':c}else line+=c }
  lines.push(line);return lines
}
async function loadImage(canvas,path) {
  if(uni.getImageInfo) {
    const info=await new Promise((resolve,reject)=>uni.getImageInfo({src:path,success:resolve,fail:reject}))
    if(info.width*info.height>2400000)throw new Error('图片过大，改用服务器')
  }
  return new Promise((resolve,reject)=>{const img=canvas.createImage();let timer=setTimeout(()=>reject(new Error('本地图片解码超时')),5000);img.onload=()=>{clearTimeout(timer);if(img.width*img.height>2400000)return reject(new Error('图片过大，改用服务器'));resolve(img)};img.onerror=()=>{clearTimeout(timer);reject(new Error('图片无法本地解码'))};img.src=path})
}
function drawImage(ctx,img,layer) {
  const [x,y,w,h]=layer.box
  if(layer.fit==='cover') { const scale=Math.max(w/img.width,h/img.height),sw=w/scale,sh=h/scale;ctx.drawImage(img,(img.width-sw)/2,(img.height-sh)/2,sw,sh,x,y,w,h) }
  else { const scale=Math.min(w/img.width,h/img.height);const dw=img.width*scale,dh=img.height*scale;ctx.drawImage(img,x+(w-dw)/2,y+(h-dh)/2,dw,dh) }
}

export async function tryClientRender(key,paths,texts,args={}) {
  if(rendering || Object.keys(args).length || !key.startsWith('auto_')) return null
  let canvas=null,images=[];rendering=true
  try {
    const recipe=await prefetchClientTemplate(key)
    if(!recipe) return null
    const s=recipe.spec,width=Math.max(s.width,512),credit=recipe.attribution || {}
    canvas=wx.createOffscreenCanvas({type:'2d',width,height:s.height+256})
    let ctx=canvas.getContext('2d');ctx.font='12px sans-serif'
    const credits=credit.source_url ? [String(credit.author||'')+' · '+String(credit.license||''),credit.source_url,credit.license_url].flatMap(t=>wrap(ctx,String(t||'').slice(0,500),width-12)) : []
    canvas.height=s.height+(credits.length ? credits.length*16+12 : 0)
    ctx=canvas.getContext('2d');ctx.fillStyle='#ffffff';ctx.fillRect(0,0,canvas.width,canvas.height)
    ctx.save();ctx.translate((width-s.width)/2,0);ctx.fillStyle=s.background;ctx.fillRect(0,0,s.width,s.height)
    for(const layer of s.layers) {
      if(layer.type!=='text') {
        const path=layer.type==='subject'?paths[layer.slot]:await assetPath(layer.value,recipe.assets[layer.value])
        if(!path)throw new Error('缺少图片')
        const img=await loadImage(canvas,path);images.push(img);drawImage(ctx,img,layer)
      } else {
        const [x,y,w,h]=layer.box;const values=texts.length ? texts : s.defaults
        const value=String(values[layer.slot] ?? layer.value).slice(0,200);let lines,size
        for(size=layer.font_size;size>=10;size--){ctx.font=`${size}px sans-serif`;lines=wrap(ctx,value,w);if(lines.length*(size+4)<=h)break}
        if(size<10)throw new Error('文字超出本地排版范围')
        ctx.textBaseline='top';ctx.fillStyle=layer.color;lines.forEach((line,i)=>ctx.fillText(line,x,y+i*(size+4)))
      }
    }
    ctx.restore();ctx.font='12px sans-serif';ctx.textBaseline='top';ctx.fillStyle='#666666';credits.forEach((line,i)=>ctx.fillText(line,6,s.height+5+i*16))
    const result=await new Promise((resolve,reject)=>wx.canvasToTempFilePath({canvas,fileType:'jpg',quality:.9,success:r=>resolve(r.tempFilePath),fail:reject}))
    const token=recipe.receipt;recipe.receipt=''
    trackTemplate(key,'client_generate',token)
    return result
  } catch(e) { console.info('本地模板回退服务器:',e.message || e.errMsg);return null }
  finally { if(canvas){canvas.width=1;canvas.height=1}images.length=0;rendering=false }
}
