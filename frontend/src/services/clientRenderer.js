import { apiRequest } from '@/services/apiService'
import { API_BASE_URL } from '@/constants'
import { visitorHeaders, trackTemplate } from '@/services/popularityService'

const recipes = new Map(), assets = new Map(), inflight = new Map()
const recipeRequests = new Map(), seeding = new Map()
let assetBytes = 0, rendering = false
// Only remove files owned by this public material cache, never user pictures.
if(typeof uni!=='undefined' && uni.env?.USER_DATA_PATH && uni.getFileSystemManager) {
  const fs=uni.getFileSystemManager()
  fs.readdir?.({dirPath:uni.env.USER_DATA_PATH,success:r=>{for(const name of r.files || [])if(/^gensticker_material_[a-f0-9]{64}\.png$/.test(name))fs.unlink({filePath:`${uni.env.USER_DATA_PATH}/${name}`,fail:()=>{}})},fail:()=>{}})
}
function trimAssets() {
  while(assetBytes>8*1024*1024 || assets.size>24) { const oldest=assets.keys().next().value, old=assets.get(oldest);assets.delete(oldest);assetBytes-=old.bytes;uni.getFileSystemManager().unlink({filePath:old.path,fail:()=>{}}) }
}

export function seedClientRecipes(manifest) {
  if(typeof wx==='undefined' || !uni.getFileSystemManager || !uni.env?.USER_DATA_PATH) return
  for(const recipe of manifest?.recipes || []) {
    try { validateRecipe(recipe);if(recipes.size<32 || recipes.has(recipe.key))recipes.set(recipe.key,recipe) } catch(_) {}
  }
  let bytes=0
  for(const [hash,value] of Object.entries(manifest?.assets || {})) {
    if(!/^[a-f0-9]{64}$/.test(hash) || typeof value!=='string' || bytes+value.length>180*1024 || assets.has(hash) || seeding.has(hash))continue
    bytes+=value.length
    const path=`${uni.env.USER_DATA_PATH}/gensticker_material_${hash}.png`,size=Math.floor(value.length*3/4)
    const task=new Promise(resolve=>uni.getFileSystemManager().writeFile({filePath:path,data:value,encoding:'base64',success:()=>{assets.set(hash,{path,bytes:size});assetBytes+=size;trimAssets();resolve()},fail:()=>resolve()})).finally(()=>seeding.delete(hash))
    seeding.set(hash,task)
  }
}

function assetPath(hash, path) {
  if (!/^[a-f0-9]{64}$/.test(hash) || path !== `/template-assets/${hash}.png`) throw new Error('素材地址无效')
  const hit = assets.get(hash)
  if (hit) { assets.delete(hash); assets.set(hash,hit); return Promise.resolve(hit.path) }
  if(seeding.has(hash))return seeding.get(hash).then(()=>assetPath(hash,path))
  if(inflight.has(hash)) return inflight.get(hash)
  const task = new Promise((resolve,reject) => uni.downloadFile({ url:`${API_BASE_URL}${path}`, timeout:10000, success:r=>{
    if(r.statusCode!==200) return reject(new Error('本地素材暂不可用'))
    const fs=uni.getFileSystemManager()
    fs.stat({path:r.tempFilePath,success:s=>{
      if(s.stats.size>1024*1024) { fs.unlink({filePath:r.tempFilePath,fail:()=>{}}); return reject(new Error('素材过大')) }
      assets.set(hash,{path:r.tempFilePath,bytes:s.stats.size}); assetBytes+=s.stats.size
      trimAssets()
      resolve(r.tempFilePath)
    },fail:reject})
  },fail:reject})).finally(()=>inflight.delete(hash))
  inflight.set(hash,task); return task
}

export async function prefetchClientTemplate(key) {
  if((!key.startsWith('auto_') && !['always','look_flat'].includes(key)) || typeof wx==='undefined' || !wx.createOffscreenCanvas) return null
  const cached=recipes.get(key)
  if(cached && cached.expires>Date.now()/1000+30) {
    for(const [hash,path] of Object.entries(cached.assets))await assetPath(hash,path)
    return cached
  }
  if(recipeRequests.has(key))return recipeRequests.get(key)
  const task=(async()=>{
  const recipe=await apiRequest(`/memes/${encodeURIComponent(key)}/client-template`,{header:visitorHeaders()},1)
  if(!recipe.supported) return null
  validateRecipe(recipe)
  // Serial downloads bound decoded material preparation and API concurrency.
  for(const [hash,path] of Object.entries(recipe.assets)) await assetPath(hash,path)
  recipes.set(key,recipe)
  while(recipes.size>16) recipes.delete(recipes.keys().next().value)
  return recipe
  })().finally(()=>recipeRequests.delete(key))
  recipeRequests.set(key,task);return task
}

function reportSuccess(key, recipe) {
  const token=recipe.receipt;recipe.receipt=''
  if(token && (recipe.receipt_expires || recipe.expires)>Date.now()/1000){trackTemplate(key,'client_generate',token);return}
  // Analytics and ticket refresh must never block the local result.
  apiRequest(`/memes/${encodeURIComponent(key)}/client-template`,{header:visitorHeaders()},1).then(fresh=>{
    if(fresh.supported && fresh.version===recipe.version)trackTemplate(key,'client_generate',fresh.receipt)
    else if(fresh.supported){validateRecipe(fresh);recipes.set(key,fresh)}
  }).catch(()=>{})
}

export function validateRecipe(recipe) {
  if(recipe.layout) {
    if(!((recipe.key==='always' && recipe.layout==='always-normal-v1') || (recipe.key==='look_flat' && recipe.layout==='look-flat-v1')))throw new Error('本地布局未注册')
    return
  }
  const s=recipe.spec
  if(!s || !Number.isInteger(s.width) || !Number.isInteger(s.height) || s.width<64 || s.height<64 || s.width>768 || s.height>768 || !/^#[a-f0-9]{6}$/i.test(s.background) || !Array.isArray(s.layers) || s.layers.length>12 || s.layers.length<1) throw new Error('模板超出本地能力')
  for(const l of s.layers) {
    if(!['asset','subject','text'].includes(l.type) || !Array.isArray(l.box) || l.box.length!==4 || l.box.some(v=>!Number.isInteger(v))) throw new Error('模板图层无效')
    const [x,y,w,h]=l.box
    if(x<0 || y<0 || w<=0 || h<=0 || x+w>s.width || y+h>s.height || !['contain','cover'].includes(l.fit) || !Number.isInteger(l.slot) || l.slot<0 || l.slot>1 || !/^#[a-f0-9]{6}$/i.test(l.color)) throw new Error('模板图层越界')
    if(l.type==='asset' && (!/^[a-f0-9]{64}$/.test(l.value) || !recipe.assets[l.value])) throw new Error('模板素材无效')
    if(l.type==='text' && (!Number.isInteger(l.font_size) || l.font_size<10 || l.font_size>100)) throw new Error('文字图层无效')
    if(l.type==='text' && ((!['left','center','right'].includes(l.align || 'left')) || !['normal','bold'].includes(l.weight || 'normal') || !Number.isInteger(l.stroke_width ?? 0) || (l.stroke_width ?? 0)<0 || (l.stroke_width ?? 0)>4 || !/^#[a-f0-9]{6}$/i.test(l.stroke_color || '#000000')))throw new Error('文字样式无效')
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
  if(rendering || Object.keys(args).length || (!key.startsWith('auto_') && !['always','look_flat'].includes(key))) return null
  let canvas=null,images=[];rendering=true
  try {
    const recipe=await prefetchClientTemplate(key)
    if(!recipe) return null
    if(recipe.layout) {
      // Preserve original GIF behaviour: native ports accept JPEG only.
      const info=await new Promise((resolve,reject)=>uni.getImageInfo({src:paths[0],success:resolve,fail:reject}))
      if(!/^(jpg|jpeg)$/i.test(info.type || '') || info.width*info.height>2400000)return null
      const h=Math.round(500*info.height/info.width),smallH=Math.round(100*info.height/info.width)
      const outputH=key==='always' ? h+Math.max(smallH,80)+10 : Math.floor(h/2)+80
      if(outputH>1024 || paths.length!==1)return null
      canvas=wx.createOffscreenCanvas({type:'2d',width:500,height:outputH})
      const ctx=canvas.getContext('2d'),img=await loadImage(canvas,paths[0]);images.push(img)
      ctx.fillStyle='#ffffff';ctx.fillRect(0,0,500,outputH);ctx.fillStyle='#000000';ctx.textBaseline='top'
      if(key==='always') {
        ctx.drawImage(img,0,0,500,h);ctx.drawImage(img,290,h+5+(Math.max(smallH,80)-smallH)/2,100,smallH)
        ctx.font='60px sans-serif';ctx.textAlign='right';ctx.fillText('要我一直',280,h+5+(Math.max(smallH,80)-60)/2)
        ctx.textAlign='left';ctx.fillText('吗',400,h+5+(Math.max(smallH,80)-60)/2)
      } else {
        const imageH=Math.floor(h/2),text=String(texts[0] || '可恶...被人看扁了')
        ctx.drawImage(img,0,0,500,imageH);let size=55
        for(;size>=30;size--){ctx.font=`bold ${size}px sans-serif`;if(ctx.measureText(text).width<=480)break}
        if(size<30)throw new Error('本地文字超出排版范围')
        ctx.textAlign='center';ctx.fillText(text,250,imageH+(80-size)/2)
      }
      const output=await new Promise((resolve,reject)=>wx.canvasToTempFilePath({canvas,fileType:'jpg',quality:.9,success:r=>resolve(r.tempFilePath),fail:reject}))
      reportSuccess(key,recipe);return output
    }
    const s=recipe.spec,credit=recipe.attribution || {},width=credit.origin==='user-provided' ? s.width : Math.max(s.width,512)
    canvas=wx.createOffscreenCanvas({type:'2d',width,height:s.height+256})
    let ctx=canvas.getContext('2d');ctx.font='12px sans-serif'
    const credits=credit.source_url && credit.origin!=='user-provided' ? [String(credit.author||'')+' · '+String(credit.license||''),credit.source_url,credit.license_url].flatMap(t=>wrap(ctx,String(t||'').slice(0,500),width-12)) : []
    canvas.height=s.height+(credits.length ? credits.length*16+12 : 0)
    ctx=canvas.getContext('2d');ctx.fillStyle='#ffffff';ctx.fillRect(0,0,canvas.width,canvas.height)
    ctx.save();ctx.translate((width-s.width)/2,0);ctx.fillStyle=s.background;ctx.fillRect(0,0,s.width,s.height)
    let decodedPixels=0
    for(const layer of s.layers) {
      if(layer.type!=='text') {
        const path=layer.type==='subject'?paths[layer.slot]:await assetPath(layer.value,recipe.assets[layer.value])
        if(!path)throw new Error('缺少图片')
        const img=await loadImage(canvas,path);decodedPixels+=img.width*img.height;if(decodedPixels>6000000)throw new Error('素材解码资源超限');images.push(img);drawImage(ctx,img,layer)
      } else {
        const [x,y,w,h]=layer.box;const values=texts.length ? texts : s.defaults
        const value=String(values[layer.slot] ?? layer.value).slice(0,200);let lines,size
        const stroke=layer.stroke_width || 0
        for(size=layer.font_size;size>=10;size--){ctx.font=`${layer.weight==='bold' ? 'bold ' : ''}${size}px sans-serif`;lines=wrap(ctx,value,w-2*stroke);if((!layer.max_lines || lines.length<=layer.max_lines) && lines.length*(size+4)<=h)break}
        if(size<10)throw new Error('文字超出本地排版范围')
        ctx.textBaseline='top';ctx.fillStyle=layer.color;ctx.textAlign=layer.align || 'left';ctx.strokeStyle=layer.stroke_color || '#000000';ctx.lineWidth=stroke*2;ctx.lineJoin='round'
        const left=layer.align==='center' ? x+w/2 : layer.align==='right' ? x+w-stroke : x+stroke
        lines.forEach((line,i)=>{if(stroke)ctx.strokeText(line,left,y+i*(size+4));ctx.fillText(line,left,y+i*(size+4))})
        ctx.textAlign='left'
      }
    }
    ctx.restore();ctx.font='12px sans-serif';ctx.textBaseline='top';ctx.fillStyle='#666666';credits.forEach((line,i)=>ctx.fillText(line,6,s.height+5+i*16))
    const result=await new Promise((resolve,reject)=>wx.canvasToTempFilePath({canvas,fileType:'jpg',quality:.9,success:r=>resolve(r.tempFilePath),fail:reject}))
    reportSuccess(key,recipe)
    return result
  } catch(e) { console.info('本地模板回退服务器:',e.message || e.errMsg);return null }
  finally { if(canvas){canvas.width=1;canvas.height=1}images.length=0;rendering=false }
}
