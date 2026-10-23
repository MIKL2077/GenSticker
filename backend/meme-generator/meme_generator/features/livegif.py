"""Bounded, private Live Photo motion/video -> editable GIF. No network protocols."""
from meme_generator.safe_images import open_image
import json,os,shutil,subprocess,tempfile,time,uuid,threading,hashlib
import filetype
from io import BytesIO
from pathlib import Path
from typing import Literal
from PIL import Image,ImageDraw,ImageSequence
from fastapi import APIRouter,Depends,HTTPException,UploadFile,File,Form
from fastapi.responses import FileResponse
from pydantic import BaseModel,Field,model_validator
from ..account import current_user
from .store import root
from .caption import CaptionStyle,paint_caption
router=APIRouter(prefix='/studio/live');slots=threading.BoundedSemaphore(2)
TTL=7*86400
MAX_GIF_BYTES=500*1024

@router.post('/results',status_code=201)
async def save_result(file:UploadFile=File(...),idempotency_key:str=Form(min_length=8,max_length=100),user=Depends(current_user)):
    """Sync only the final local GIF. Never decode or upload the full source."""
    raw=await file.read(MAX_GIF_BYTES+1)
    if len(raw)>MAX_GIF_BYTES:raise HTTPException(413,'成品需要压缩到 500 KB 以内')
    from asyncio import to_thread
    return await to_thread(prepare_result,raw,idempotency_key,user)

def prepare_result(raw,idem,user):
    from meme_generator.features.storage import write_guard
    with write_guard(user['id'], len(raw) * 2 + 1024, ingress=len(raw),media=True):
        from .studio import enqueue
        if not slots.acquire(False):raise HTTPException(503,'动图同步繁忙，请稍后再试')
        try:
            try:
                with open_image(BytesIO(raw)) as image:
                    if image.format!='GIF' or max(image.size)>240 or min(image.size)<2 or not 1<=image.n_frames<=100:raise ValueError()
                    duration=0
                    for frame in ImageSequence.Iterator(image):
                        frame.load();duration+=frame.info.get('duration',100)
                    if not 100<=duration<=9100:raise ValueError()
                    width,height=image.size
            except (OSError,ValueError,Image.DecompressionBombError):raise HTTPException(422,'请选择最长 9 秒、长边 240 px 以内的动态 GIF')
            # Deterministic identifier makes interrupted upload retries idempotent.
            identifier=hashlib.sha256((user['id']+':'+idem).encode()+raw).hexdigest()[:32]
            path=directory()/(identifier+'.media');meta_path=directory()/(identifier+'.json')
            if not meta_path.exists():
                from .store import connect
                db=connect()
                try:
                    # Count ingress before retaining another file; deleting jobs cannot bypass it.
                    from .recommend import admit_generation
                    with db:
                        db.execute('BEGIN IMMEDIATE');admit_generation(db,user['id'],'live:'+identifier,time.time())
                finally:db.close()
                path.write_bytes(raw)
                meta_path.write_text(json.dumps({'user_id':user['id'],'created':time.time(),'duration':duration/1000,'width':width,'height':height,'ready':True}))
            job=enqueue('livegif',{'asset_id':identifier,'ready':True},idem,user)
            return job
        finally:slots.release()

def directory():
    path=root()/'live_sources';path.mkdir(exist_ok=True);return path

def run(args,timeout=25):
    try:return subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout,check=True).stdout
    except FileNotFoundError:raise HTTPException(503,'动图工作室还在准备编解码器')
    except (subprocess.SubprocessError,OSError):raise HTTPException(422,'没有读取到动态画面，请重新选择含视频片段的素材')

def motion(raw):
    if raw[:6] in (b'GIF87a',b'GIF89a'):return raw
    # MP4/MOV, or Android motion JPEG with an appended MP4 stream.
    start=0
    while True:
        offset=raw.find(b'ftyp',start)
        if offset<4:break
        brand=raw[offset+4:offset+8]
        size=int.from_bytes(raw[offset-4:offset],'big')
        if brand not in (b'heic',b'heix',b'hevc',b'hevx',b'mif1',b'avif') and 8<=size<=256:return raw[offset-4:]
        start=offset+8
    # QuickTime can start with wide/mdat/moov instead of an ftyp box.
    if len(raw)>12 and raw[4:8] in (b'moov',b'mdat',b'wide'):return raw
    raise HTTPException(422,'微信没有提供 Live 动态片段，请选择包含动态片段的原始文件或视频')

def own(asset,user):
    if len(asset)!=32 or any(c not in '0123456789abcdef' for c in asset):raise HTTPException(404,'素材不存在')
    meta_path=directory()/(asset+'.json')
    if not meta_path.exists():raise HTTPException(404,'动态素材已过期')
    meta=json.loads(meta_path.read_text())
    if meta['user_id']!=user or meta['created']<time.time()-TTL:raise HTTPException(404,'动态素材已过期')
    return meta

@router.post('/assets',status_code=201)
async def upload(file:UploadFile=File(...),user=Depends(current_user)):
    from asyncio import to_thread
    raw=await file.read(60*1024*1024+1)
    if len(raw)>60*1024*1024:raise HTTPException(413,'素材超过 60 MB，请先在时间轴截取或压缩视频')
    return await to_thread(prepare,raw,user['id'])

def prepare(raw,user):
    from meme_generator.features.storage import write_guard
    with write_guard(user, len(raw) + 1024 * 1024, ingress=len(raw),media=True):
        if not slots.acquire(False):raise HTTPException(503,'动态素材正在准备，请稍后再传')
        identifier=uuid.uuid4().hex;path=directory()/(identifier+'.media')
        try:
            # Per-user rolling ingress budget, independent of unlimited meme generation.
            recent=[p for p in directory().glob('*.json') if p.stat().st_mtime>time.time()-60]
            if sum(json.loads(p.read_text()).get('user_id')==user for p in recent)>=4:raise HTTPException(429,'视频上传有点快，休息一分钟再来')
            path.write_bytes(motion(raw))
            info=json.loads(run(['ffprobe','-v','error','-protocol_whitelist','file,pipe','-show_streams','-show_format','-of','json',str(path)]))
            stream=next((s for s in info['streams'] if s.get('codec_type')=='video'),None)
            if not stream or stream.get('width',0)*stream.get('height',0)>33_200_000:raise HTTPException(422,'视频分辨率过高，先导出 1080p 再试试')
            duration=float(info.get('format',{}).get('duration') or stream.get('duration') or 3)
            if not .08<=duration<=1800:raise HTTPException(422,'请选择 30 分钟以内的视频')
            poster=directory()/(identifier+'.jpg')
            run(['ffmpeg','-nostdin','-v','error','-threads','2','-protocol_whitelist','file,pipe','-i',str(path),'-frames:v','1','-vf','scale=640:640:force_original_aspect_ratio=decrease','-y',str(poster)])
            with open_image(poster) as image:width,height=image.size
            meta={'user_id':user,'created':time.time(),'duration':duration,'width':width,'height':height}
            (directory()/(identifier+'.json')).write_text(json.dumps(meta))
            return {**{k:v for k,v in meta.items() if k not in ('user_id','created')},'asset_id':identifier,'poster_url':f'/studio/live/assets/{identifier}/poster'}
        except Exception:
            path.unlink(missing_ok=True);(directory()/(identifier+'.jpg')).unlink(missing_ok=True);raise
        finally:slots.release()

@router.get('/assets/{identifier}/poster')
def poster(identifier:str,user=Depends(current_user)):
    own(identifier,user['id']);return FileResponse(directory()/(identifier+'.jpg'),media_type='image/jpeg',headers={'Cache-Control':'private, no-store'})

@router.get('/assets/{identifier}/source')
def edit_source(identifier:str,user=Depends(current_user)):
    own(identifier,user['id'])
    path=directory()/(identifier+'.media')
    if not path.is_file():raise HTTPException(410,'原视频已过期，无法恢复编辑')
    return FileResponse(path,media_type=filetype.guess_mime(str(path)) or 'application/octet-stream',headers={'Cache-Control':'private, no-store'})

class LiveJob(BaseModel):
    quality:Literal['balanced','smooth','clear']='balanced'
    asset_id:str=Field(pattern='^[a-f0-9]{32}$')
    idempotency_key:str=Field(min_length=8,max_length=100)
    start:float=Field(default=0,ge=0,le=1800)
    duration:float=Field(default=3,ge=.2,le=9)
    crop:tuple[float,float,float,float]=(0,0,1,1)
    text:str=Field(default='',max_length=100)
    caption_style:CaptionStyle=Field(default_factory=CaptionStyle)
    rotation:int=Field(default=0)
    flip:bool=False
    @model_validator(mode='after')
    def valid(self):
        x,y,w,h=self.crop
        import math
        if not all(math.isfinite(v) for v in self.crop) or min(x,y)<0 or min(w,h)<=0 or x+w>1.00001 or y+h>1.00001 or self.rotation not in (0,90,180,270):raise ValueError('invalid crop or rotation')
        return self

@router.post('/jobs',status_code=201)
def create(params:LiveJob,user=Depends(current_user)):
    meta=own(params.asset_id,user['id'])
    if params.start>=meta['duration']:raise HTTPException(422,'起始时间已经超出视频长度')
    from .store import connect
    from .recommend import admit_generation
    db=connect()
    try:
        with db:
            db.execute('BEGIN IMMEDIATE');admit_generation(db,user['id'],'gif:'+hashlib.sha256((user['id']+params.idempotency_key).encode()).hexdigest(),time.time())
    finally:db.close()
    from .studio import enqueue
    return enqueue('livegif',params.model_dump(exclude={'idempotency_key'}),params.idempotency_key,user)

def render_job(payload,user):
    meta=own(payload['asset_id'],user)
    if payload.get('ready'):
        if not meta.get('ready'):raise ValueError('invalid prepared GIF')
        return (directory()/(payload['asset_id']+'.media')).read_bytes()
    params=LiveJob.model_validate({**payload,'idempotency_key':'worker-render'})
    source=directory()/(params.asset_id+'.media');filters=[]
    if params.rotation==90:filters.append('transpose=1')
    elif params.rotation==180:filters.extend(['hflip','vflip'])
    elif params.rotation==270:filters.append('transpose=2')
    if params.flip:filters.append('hflip')
    x,y,w,h=params.crop;filters.extend([fr'crop=w=max(1\,floor(iw*{w})):h=max(1\,floor(ih*{h})):x=min(iw-ow\,floor(iw*{x})):y=min(ih-oh\,floor(ih*{y})):exact=1',r'scale=w=max(2\,trunc(iw*min(240/iw\,240/ih))):h=max(2\,trunc(ih*min(240/iw\,240/ih)))','fps=10'])
    with tempfile.TemporaryDirectory(dir=directory()) as temp:
        pattern=str(Path(temp)/'frame-%03d.png')
        run(['ffmpeg','-nostdin','-v','error','-threads','2','-filter_threads','2','-protocol_whitelist','file,pipe','-ss',str(params.start),'-i',str(source),'-t',str(params.duration),'-an','-vf',','.join(filters),'-frames:v','90','-y',pattern],timeout=30)
        frames=[]
        for file in sorted(Path(temp).glob('frame-*.png')):
            with open_image(file) as image:frame=image.convert('RGB')
            if params.text:paint_caption(frame,params.text,params.caption_style)
            frames.append(frame)
        if not frames:raise ValueError('视频没有可读取的画面')
        return fit_gif(frames,params.quality)

def fit_gif(frames,quality='balanced'):
    """Keep the whole selected interval. Bound size by resolution as well as color/fps."""
    # Never ask users to redo a valid edit merely because a busy scene has more entropy.
    attempts=((240,1,128),(240,2,128),(200,2,96),(160,2,64),(120,2,64),(96,3,48),(64,3,32),(32,3,16))
    if quality=='smooth':attempts=((240,1,128),(240,1,64),(200,1,64),(160,1,48),(120,1,32),(96,1,16))+attempts[1:]
    if quality=='clear':attempts=((240,1,128),(240,2,128),(240,3,96),(240,3,64))+attempts[2:]
    for edge,stride,colors in attempts:
        reduced=[]
        for frame in frames[::stride]:
            image=frame.copy();image.thumbnail((edge,edge),Image.Resampling.LANCZOS)
            reduced.append(image.quantize(colors=colors,method=Image.Quantize.MEDIANCUT))
        output=BytesIO();reduced[0].save(output,'GIF',save_all=True,append_images=reduced[1:],duration=[min(stride,len(frames)-i)*100 for i in range(0,len(frames),stride)],loop=0,optimize=True,disposal=2)
        if len(output.getvalue())<=MAX_GIF_BYTES:return output.getvalue()
    raise ValueError('GIF 压缩失败')

def cleanup():
    for meta_path in directory().glob('*.json'):
        try:
            if json.loads(meta_path.read_text())['created']>time.time()-TTL:continue
            for extension in ('.json','.jpg','.media'):(directory()/(meta_path.stem+extension)).unlink(missing_ok=True)
        except (ValueError,OSError,KeyError):pass
