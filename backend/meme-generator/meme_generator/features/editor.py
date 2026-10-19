"""Template replacement guides and private transient foreground delivery."""
import hashlib,json,secrets,time,threading
from collections import OrderedDict
from io import BytesIO
import numpy as np
from PIL import Image,ImageChops,ImageFilter
from fastapi import APIRouter,HTTPException,Request,Response
from fastapi.security import HTTPAuthorizationCredentials
from ..account import current_user
from .store import connect
from .declarative import render
from .popularity import actor
router=APIRouter()
_lock=threading.RLock();_slots=threading.BoundedSemaphore(2);_guides=OrderedDict();_foreground=OrderedDict()

def identity(request):
    auth=request.headers.get('authorization','')
    return current_user(HTTPAuthorizationCredentials(scheme='Bearer',credentials=auth[7:]))['id'] if auth.lower().startswith('bearer ') else ''

def template(key,request):
    user=identity(request);db=connect()
    try:
        row=db.execute("SELECT * FROM templates WHERE key=? AND status='published'",(key,)).fetchone()
        if row:return dict(row)
    finally:db.close()
    if key.startswith('user_'):
        from .studio import own_template
        row=own_template(key,{'id':user});return {**row,'version':row['updated']}
    raise HTTPException(404,'模板暂时不可用')

def guide(key,request):
    row=template(key,request);cachekey=(key,row['version'])
    with _lock:
        if cachekey in _guides:_guides.move_to_end(cachekey);return _guides[cachekey]
    if not _slots.acquire(False):raise HTTPException(503,'模板参照正在准备，请稍后再试')
    try:
        from ..manager import get_meme
        from .catalog import refresh
        meta=json.loads(row['metadata']);spec=json.loads(row['spec']) if row.get('spec') else None
        slots=min(10,meta.get('max_images',1));samples=[Image.new('RGBA',(256,256),'white') for _ in range(max(1,slots))]
        if spec:
            plate=Image.open(render(spec,samples)).convert('RGBA');windows=[]
            for layer in spec['layers']:
                if layer['type'] in ('subject','face'):windows.append({'slot':layer['slot'],'box':layer['box']})
            alpha=Image.new('L',plate.size,255)
            from PIL import ImageDraw
            painter=ImageDraw.Draw(alpha)
            for window in windows:
                x,y,w,h=window['box'];painter.rectangle((x,y,x+w-1,y+h-1),fill=0)
            plate.putalpha(alpha)
        else:
            refresh();meme=get_meme(key);texts=meta.get('default_texts',[]) or ['示例文字']*meta.get('min_texts',0)
            base=meme(images=[_png(i) for i in samples[:slots]],texts=texts,args={})
            plate=Image.open(base).convert('RGBA');windows=[];alpha=np.full((plate.height,plate.width),255,dtype='uint8')
            import cv2
            for slot in range(slots):
                inputs=[_png(i) for i in samples[:slots]];inputs[slot]=_png(Image.new('RGBA',(256,256),'black'))
                other=Image.open(meme(images=inputs,texts=texts,args={})).convert('RGBA')
                if other.size!=plate.size:continue
                diff=np.max(np.abs(np.array(plate.convert('RGB')).astype('int16')-np.array(other.convert('RGB')).astype('int16')),axis=2)>30
                coverage=float(diff.mean())
                if not .002<coverage<.94:continue
                count,labels,stats,_=cv2.connectedComponentsWithStats(diff.astype('uint8'),8)
                candidates=[tuple(map(int,r[:4])) for r in stats[1:] if r[4]>max(64,plate.width*plate.height*.001)]
                candidates.sort(key=lambda box:box[2]*box[3],reverse=True)
                for box in candidates[:6]:windows.append({'slot':slot,'box':list(box)})
                alpha[diff]=0
            plate.putalpha(Image.fromarray(alpha))
        # Only render bounded guides. Unknown dynamic layouts remain honest generic crops.
        width,height=plate.size
        generic=not windows
        if generic:windows=[{'slot':0,'box':[0,0,width,height]}];plate.putalpha(Image.new('L',plate.size,0))
        plate.thumbnail((640,640));out=BytesIO();plate.save(out,'PNG',optimize=True)
        result={'width':width,'height':height,'windows':windows,'generic':generic,'overlay':out.getvalue()}
        with _lock:
            _guides[cachekey]=result
            while len(_guides)>24 or sum(len(r['overlay']) for r in _guides.values())>12*1024*1024:_guides.popitem(last=False)
        return result
    except HTTPException:raise
    except Exception:raise HTTPException(422,'这个模板暂时使用通用裁剪窗，仍可编辑和抠图')
    finally:_slots.release()

def _png(image):
    b=BytesIO();image.save(b,'PNG');return b.getvalue()

@router.get('/images/templates/{key}/guide')
def guide_info(key:str,request:Request):
    value=guide(key,request)
    return {k:v for k,v in value.items() if k!='overlay'}|{'overlay_url':f'/images/templates/{key}/overlay'}

@router.get('/images/templates/{key}/overlay')
def guide_overlay(key:str,request:Request):
    return Response(guide(key,request)['overlay'],media_type='image/png',headers={'Cache-Control':'private, no-store'})

def deliver_foreground(data,request):
    stamp=time.time();token=secrets.token_hex(20)
    with _lock:
        for key,value in list(_foreground.items()):
            if value[0]<stamp:del _foreground[key]
        _foreground[token]=(stamp+600,actor(request),data)
        while len(_foreground)>20 or sum(len(v[2]) for v in _foreground.values())>24*1024*1024:_foreground.popitem(last=False)
    return {'image_url':f'/images/subject-results/{token}','expires_in':600}

@router.get('/images/subject-results/{token}')
def foreground_result(token:str,request:Request):
    with _lock:value=_foreground.get(token)
    if not value or value[0]<time.time() or value[1]!=actor(request):raise HTTPException(404,'处理结果已过期，请重新抠图')
    return Response(value[2],media_type='image/png',headers={'Cache-Control':'private, no-store'})
