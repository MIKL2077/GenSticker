"""Owned authoring and durable manual jobs. Model output is bounded declarative data."""
from meme_generator.safe_images import open_image, open_input_image
import base64
import binascii
import hashlib
import json
import os
import time
import uuid
import threading
from io import BytesIO
from datetime import datetime
from zoneinfo import ZoneInfo
import filetype
import httpx
from PIL import Image, ImageOps
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, ConfigDict
from ..account import current_user, connection, profile
from .store import connect, root
from .storage import write_bytes
from .declarative import TemplateSpec, render

router = APIRouter(prefix='/studio')
TTL = 7 * 86400
normalization_slots=threading.BoundedSemaphore(2)


def init():
    db = connect()
    db.executescript('''
    CREATE TABLE IF NOT EXISTS studio_jobs(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,kind TEXT NOT NULL,idem TEXT NOT NULL,digest TEXT NOT NULL,payload TEXT NOT NULL,status TEXT NOT NULL,created REAL NOT NULL,updated REAL NOT NULL,lease REAL NOT NULL DEFAULT 0,attempts INTEGER NOT NULL DEFAULT 0,message TEXT NOT NULL DEFAULT '',result TEXT NOT NULL DEFAULT '',UNIQUE(user_id,kind,idem));
    CREATE TABLE IF NOT EXISTS studio_templates(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,name TEXT NOT NULL,spec TEXT NOT NULL,metadata TEXT NOT NULL,status TEXT NOT NULL,created REAL NOT NULL,updated REAL NOT NULL,message TEXT NOT NULL DEFAULT '');
    CREATE TABLE IF NOT EXISTS studio_ai_attempts(user_id TEXT NOT NULL,created REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS studio_ai_daily(user_id TEXT NOT NULL,day TEXT NOT NULL,job_id TEXT NOT NULL,PRIMARY KEY(user_id,day));
    CREATE TABLE IF NOT EXISTS studio_views(job_id TEXT PRIMARY KEY,user_id TEXT NOT NULL,viewed REAL NOT NULL);
    CREATE INDEX IF NOT EXISTS studio_jobs_user_time ON studio_jobs(user_id,created);
    CREATE INDEX IF NOT EXISTS studio_templates_owner ON studio_templates(user_id,created);
    CREATE INDEX IF NOT EXISTS studio_queue ON studio_jobs(status,created);
    ''')
    db.commit()
    return db


def decode_image(encoded, limit=4*1024*1024):
    if not normalization_slots.acquire(blocking=False):raise HTTPException(503,'图片处理繁忙，稍后再试一下')
    try:
        raw = base64.b64decode(encoded.split(',')[-1], validate=True)
        if len(raw)>limit: raise ValueError()
        with open_input_image(BytesIO(raw)) as source:
            if source.width*source.height>16000000 or getattr(source,'n_frames',1)>1: raise ValueError()
            image=ImageOps.exif_transpose(source).convert('RGBA'); image.thumbnail((1024,1024))
            out=BytesIO();image.save(out,'PNG');return out.getvalue()
    except (ValueError, binascii.Error, OSError, Image.DecompressionBombError):
        raise HTTPException(422,'请选择 4 MB 以内的静态图片')
    finally:normalization_slots.release()


def asset(raw):
    digest=hashlib.sha256(raw).hexdigest();directory=root()/'template_assets';directory.mkdir(exist_ok=True)
    path=directory/(digest+'.png')
    if not path.exists(): path.write_bytes(raw)
    return digest


def own_template(identifier, user):
    db=init()
    try: row=db.execute('SELECT * FROM studio_templates WHERE id=? AND user_id=?',(identifier,user['id'])).fetchone()
    finally: db.close()
    if not row: raise HTTPException(404,'模板不在你的小窝里')
    return dict(row)


def get_spec(key, user_id):
    if not key.startswith('user_'): return None
    db=init()
    try: row=db.execute("SELECT * FROM studio_templates WHERE id=? AND (user_id=? OR status='published')",(key,user_id)).fetchone()
    finally: db.close()
    if not row: raise HTTPException(404,'模板不存在或仅创作者可见')
    return json.loads(row['spec'])


class ManualJob(BaseModel):
    model_config=ConfigDict(extra='forbid')
    template_key: str=Field(min_length=1,max_length=100)
    images: list[str]=Field(default_factory=list,max_length=10)
    texts: list[str]=Field(default_factory=list,max_length=20)
    args: dict=Field(default_factory=dict,max_length=32)
    extract_subject: bool=False
    idempotency_key: str=Field(min_length=8,max_length=100)


class Creation(BaseModel):
    model_config=ConfigDict(extra='forbid')
    name: str=Field(min_length=1,max_length=40)
    spec: TemplateSpec
    background_image: str=Field(default='',max_length=6*1024*1024)
    operations: list[dict]=Field(default_factory=list,max_length=100)
    publish: bool=False
    rights_attested: bool=False


class AIRequest(BaseModel):
    rights_attested: bool=False
    image: str=Field(min_length=1,max_length=6*1024*1024)
    idempotency_key: str=Field(min_length=8,max_length=100)


def enqueue(kind, payload, idem, user):
    from meme_generator.features.storage import write_guard
    with write_guard(user['id'], len(json.dumps(payload).encode()) * 2 + 512 * 1024, ingress=len(json.dumps(payload).encode()) if kind in ('manual', 'template') else 0,job=True):
        stamp=time.time();digest=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
        db=init()
        try:
            with db:
                db.execute('BEGIN IMMEDIATE')
                old=db.execute('SELECT * FROM studio_jobs WHERE user_id=? AND kind=? AND idem=?',(user['id'],kind,idem)).fetchone()
                if old:
                    if old['digest']!=digest: raise HTTPException(409,'这次提交的内容已改变，请重新提交')
                    return job_view(old)
                if db.execute("SELECT count(*) FROM studio_jobs WHERE user_id=? AND status IN ('queued','running')",(user['id'],)).fetchone()[0]>=3: raise HTTPException(429,'小窝里已有 3 个任务，等一个出炉再来吧')
                if db.execute("SELECT count(*) FROM studio_jobs WHERE status IN ('queued','running')").fetchone()[0]>=40: raise HTTPException(503,'工作室排队中，请稍后再来')
                identifier=uuid.uuid4().hex
                if kind=='template':
                    if db.execute('SELECT count(*) FROM studio_ai_attempts WHERE user_id=? AND created>?',(user['id'],stamp-3600)).fetchone()[0]>=3:
                        raise HTTPException(429,'识图已尝试 3 次，请一小时后再试，手动创作仍可使用')
                    day=datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat()
                    if db.execute('SELECT 1 FROM studio_ai_daily WHERE user_id=? AND day=?',(user['id'],day)).fetchone():
                        raise HTTPException(429,'今天的 AI 模板机会已经用过啦，明天再来')
                    db.execute('INSERT INTO studio_ai_daily VALUES(?,?,?)',(user['id'],day,identifier))
                    db.execute('INSERT INTO studio_ai_attempts VALUES(?,?)',(user['id'],stamp))
                db.execute('INSERT INTO studio_jobs(id,user_id,kind,idem,digest,payload,status,created,updated) VALUES(?,?,?,?,?,?,\'queued\',?,?)',(identifier,user['id'],kind,idem,digest,json.dumps(payload),stamp,stamp))
            return {'id':identifier,'kind':kind,'status':'queued','created_at':stamp,'message':'已交给小窝，排队制作中','result_url':''}
        finally:db.close()


def job_view(row):
    return {'id':row['id'],'kind':row['kind'],'status':row['status'],'created_at':row['created'],'message':row['message'],'template_id':row['result'] if row['kind']=='template' else '', 'viewed':bool(row['viewed']) if 'viewed' in row.keys() else False,'can_regenerate':(root()/'studio_replays'/(row['id']+'.json')).exists(),'result_url':f"/studio/jobs/{row['id']}/image" if row['kind'] in ('manual','livegif') and row['status']=='completed' else ''}


@router.post('/jobs',status_code=201)
def create_manual(params:ManualJob,user=Depends(current_user)):
    if sum(len(i) for i in params.images)>14*1024*1024 or any(len(t)>2000 for t in params.texts):raise HTTPException(413,'素材过大，请先裁剪')
    if len(json.dumps(params.args).encode())>32768:raise HTTPException(413,'模板参数过大，请减少参数后重试')
    # Validate ownership before persisting a job. Published built-ins stay unchanged.
    spec=get_spec(params.template_key,user['id'])
    if spec is None:
        from ..manager import get_meme
        from .catalog import refresh
        refresh()
        try:get_meme(params.template_key)
        except Exception:raise HTTPException(404,'模板暂时不可用')
    images=[base64.b64encode(decode_image(i)).decode() for i in params.images]
    if sum(map(len,images))>14*1024*1024:raise HTTPException(413,'图片处理后过大，请减少图片或先裁剪')
    return enqueue('manual',{**params.model_dump(exclude={'idempotency_key'}),'images':images},params.idempotency_key,user)


@router.get('/jobs')
def jobs(user=Depends(current_user)):
    db=init()
    try:return [job_view(r) for r in db.execute('SELECT j.*,v.viewed FROM studio_jobs j LEFT JOIN studio_views v ON j.id=v.job_id AND j.user_id=v.user_id WHERE j.user_id=? AND j.created>? ORDER BY j.created DESC LIMIT 100',(user['id'],time.time()-TTL))]
    finally:db.close()


@router.get('/jobs/{identifier}')
def get_job(identifier:str,user=Depends(current_user)):
    db=init()
    try:row=db.execute('SELECT * FROM studio_jobs WHERE id=? AND user_id=? AND created>?',(identifier,user['id'],time.time()-TTL)).fetchone()
    finally:db.close()
    if not row:raise HTTPException(404,'任务已过期或不存在')
    return job_view(row)


# Separate bounded thumbnail cache: queue entry never needs full animated bytes.
from .render_cache import RenderCache
thumbnail_cache=RenderCache(max_bytes=2*1024*1024,max_entries=100,ttl=300)
thumbnail_slots=threading.BoundedSemaphore(2)

@router.get('/jobs/{identifier}/thumbnail')
def job_thumbnail(identifier:str,user=Depends(current_user)):
    item=get_job(identifier,user)
    if item['status']!='completed' or item['kind'] not in ('manual','livegif'):raise HTTPException(404,'图片还没出炉')
    path=root()/'studio_results'/identifier
    if not path.exists():raise HTTPException(404,'图片已过期')
    stat=path.stat();key=(str(root()),identifier,stat.st_mtime_ns,stat.st_size)
    raw=thumbnail_cache.get(key)
    if raw is None:
        if not thumbnail_slots.acquire(False):raise HTTPException(503,'缩略图准备中，请稍后再试')
        try:
            with open_image(path) as image:
                frame=image.convert('RGBA');frame.thumbnail((144,144))
                plate=Image.new('RGB',frame.size,'white');plate.paste(frame,mask=frame.getchannel('A'))
                buf=BytesIO();plate.save(buf,'JPEG',quality=72,optimize=True);raw=buf.getvalue()
            thumbnail_cache.put(key,raw)
        finally:thumbnail_slots.release()
    return Response(raw,media_type='image/jpeg',headers={'Cache-Control':'private, no-store'})

@router.get('/jobs/{identifier}/image')
def job_image(identifier:str,user=Depends(current_user)):
    item=get_job(identifier,user)
    if item['status']!='completed' or item['kind'] not in ('manual','livegif'):raise HTTPException(404,'图片还没出炉')
    path=root()/'studio_results'/identifier
    if not path.exists():raise HTTPException(404,'图片已过期')
    return FileResponse(path,media_type=filetype.guess_mime(str(path)) or 'image/png',headers={'Cache-Control':'private, no-store'})


@router.delete('/jobs/{identifier}',status_code=204)
def delete_job(identifier:str,user=Depends(current_user)):
    item=get_job(identifier,user)
    if item['status'] in ('queued','running'):raise HTTPException(409,'任务还在制作中，出炉后可删除')
    db=init()
    with db:db.execute('DELETE FROM studio_jobs WHERE id=? AND user_id=?',(identifier,user['id']))
    db.close();(root()/'studio_results'/identifier).unlink(missing_ok=True);(root()/'studio_replays'/(identifier+'.json')).unlink(missing_ok=True)
    return Response(status_code=204)


@router.get('/unread')
def unread(user=Depends(current_user)):
    db=init()
    try:return {'count':db.execute("SELECT count(*) FROM studio_jobs j LEFT JOIN studio_views v ON j.id=v.job_id AND j.user_id=v.user_id WHERE j.user_id=? AND j.kind IN ('manual','livegif') AND j.status='completed' AND j.created>? AND v.job_id IS NULL",(user['id'],time.time()-TTL)).fetchone()[0]}
    finally:db.close()

@router.post('/jobs/{identifier}/view',status_code=204)
def mark_viewed(identifier:str,user=Depends(current_user)):
    item=get_job(identifier,user)
    if item['status']=='completed':
        db=init()
        with db:db.execute('INSERT OR REPLACE INTO studio_views VALUES(?,?,?)',(identifier,user['id'],time.time()))
        db.close()
    return Response(status_code=204)

class Regenerate(BaseModel):
    idempotency_key:str=Field(min_length=8,max_length=100)

@router.post('/jobs/{identifier}/regenerate',status_code=201)
def regenerate(identifier:str,params:Regenerate,user=Depends(current_user)):
    item=get_job(identifier,user);path=root()/'studio_replays'/(identifier+'.json')
    if not path.exists():raise HTTPException(410,'旧版任务没有保留制作素材，选一个模板重新制作吧')
    payload=json.loads(path.read_text())
    if item['kind']=='manual':get_spec(payload['template_key'],user['id'])
    return enqueue(item['kind'],payload,params.idempotency_key,user)


def creator(user_id):
    db=connection()
    try:return profile(user_id,db)
    finally:db.close()


def save_template(user_id,name,spec,operations=None,conversion_metadata=None):
    from meme_generator.features.storage import write_guard
    with write_guard(user_id, len(json.dumps(spec).encode()) + 8192, template=True):
        identifier='user_'+uuid.uuid4().hex[:24];stamp=time.time();who=creator(user_id)
        layers=spec['layers'];images=max([l.get('slot',0)+1 for l in layers if l['type']=='subject'] or [0]);texts=max([l.get('slot',0)+1 for l in layers if l['type']=='text'] or [0])
        metadata={'name':name,'tags':['user-created'],'origin':'user-provided','license':'用户声明拥有使用及发布权利，未经许可不得转载','review':{'explicit_user_request':True},'creator':{'id':who['id'],'name':who['name'],'avatar':who['avatar']},'min_images':images,'max_images':images,'min_texts':texts,'max_texts':texts,'default_texts':spec.get('defaults',[]),'created_at':stamp,'operations':operations or []}
        if conversion_metadata:
            metadata.update({k:conversion_metadata[k] for k in ('conversion','quality','intent','original_hash','perceptual_hash','intent_signature','quality_score','requires_review') if k in conversion_metadata})
        db=init()
        with db:db.execute('INSERT INTO studio_templates VALUES(?,?,?,?,?,?,?,?,?)',(identifier,user_id,name,json.dumps(spec),json.dumps(metadata,ensure_ascii=False),'private',stamp,stamp,'仅自己可见'))
        db.close();return identifier


@router.post('/templates',status_code=201)
def create_template(params:Creation,user=Depends(current_user)):
    from meme_generator.features.storage import write_guard
    with write_guard(user['id'], len(params.background_image) + 65536, ingress=len(params.background_image) * 3 // 4, template=True):
        if params.publish and not params.rights_attested:raise HTTPException(422,'发布前请确认拥有素材使用及公开的权利')
        if len(json.dumps(params.operations))>32000:raise HTTPException(413,'编辑记录过大，请重新保存')
        if not params.name.strip():raise HTTPException(422,'请给模板起个名字')
        spec=params.spec.model_dump()
        if any(len(t)>200 for t in spec['defaults']):raise HTTPException(422,'默认文字最多 200 字')
        if any(l['type']=='face' for l in spec['layers']) or spec['reference_asset'] or spec['background_prepared']:raise HTTPException(422,'手动创作仅支持图片、文字和背景图层')
        backgrounds=[l for l in spec['layers'] if l['type']=='asset']
        if backgrounds:
            if len(backgrounds)!=1 or not params.background_image:raise HTTPException(422,'请重新上传背景图')
            backgrounds[0]['value']=asset(decode_image(params.background_image))
        # Render with the creator's avatar by default; reject invalid/overflowing layouts.
        who=creator(user['id']);sample=open_image(BytesIO(decode_image(who['avatar']))) if who['avatar'] else Image.new('RGBA',(256,256),'#ffe8c7')
        try:render(spec,[sample,sample])
        except (ValueError,OSError):raise HTTPException(422,'文字超出画布，请缩短文字或放大文字框')
        identifier=save_template(user['id'],params.name.strip(),spec,params.operations)
        publication=None
        if params.publish:
            try:publication=enqueue('publish',{'template_id':identifier},identifier,user)
            except HTTPException:pass
            db=init()
            with db:db.execute("UPDATE studio_templates SET status=?,message=? WHERE id=?",('pending' if publication else 'private','已保存，正在排队做内容检查' if publication else '已私藏成功，发布队列繁忙，稍后可在我的模板中重试发布',identifier))
            db.close()
        result=template_view(own_template(identifier,user))
        if publication:result['publication_job']=publication
        return result


def template_view(row):
    m=json.loads(row['metadata']);return {'id':row['id'],'key':row['id'],'name':row['name'],'status':row['status'],'message':row['message'],'created_at':row['created'],'spec':json.loads(row['spec']),'creator':m['creator'],'requires_review':bool(m.get('requires_review')),'review_digest':m.get('quality',{}).get('preview_digest',''),'params_type':{k:m[k] for k in ('min_images','max_images','min_texts','max_texts','default_texts')},'preview_url':f"/studio/templates/{row['id']}/preview?v={int(row['updated']*1000)}"}


@router.get('/templates')
def my_templates(user=Depends(current_user)):
    db=init()
    try:return [template_view(r) for r in db.execute('SELECT * FROM studio_templates WHERE user_id=? ORDER BY created DESC',(user['id'],))]
    finally:db.close()


@router.get('/templates/{identifier}')
def template_detail(identifier:str,user=Depends(current_user)):
    return template_view(own_template(identifier,user))


@router.get('/templates/{identifier}/preview')
def template_preview(identifier:str,user=Depends(current_user)):
    row=own_template(identifier,user);who=json.loads(row['metadata'])['creator'];sample=open_image(BytesIO(decode_image(who['avatar']))) if who.get('avatar') else Image.new('RGBA',(256,256),'#ffe8c7')
    return Response(render(json.loads(row['spec']),[sample,sample],preview=True).getvalue(),media_type='image/jpeg',headers={'Cache-Control':'private, no-store'})


_token={'value':'','expires':0}
def moderate(row):
    """Real WeChat content checks, fail closed on unavailable/unsupported providers."""
    appid,secret=os.getenv('WX_APPID'),os.getenv('WX_APP_SECRET')
    if not appid or not secret:return 'pending','内容检查暂未连接，已保存到我的模板，暂不公开'
    m=json.loads(row['metadata']);spec=json.loads(row['spec']);db=connection()
    try:who=db.execute('SELECT openid FROM users WHERE id=?',(row['user_id'],)).fetchone()
    finally:db.close()
    try:
        with httpx.Client(timeout=15) as client:
            if time.time()>_token['expires']:
                result=client.get('https://api.weixin.qq.com/cgi-bin/token',params={'grant_type':'client_credential','appid':appid,'secret':secret}).json()
                if not result.get('access_token'):return 'pending','内容检查暂不可用，模板先私藏，稍后可重试发布'
                _token.update(value=result['access_token'],expires=time.time()+min(result.get('expires_in',7200),7000))
            params={'access_token':_token['value']}
            text=' '.join([row['name'],m['creator']['name'],*spec.get('defaults',[]),*[l.get('value','') for l in spec['layers'] if l['type']=='text']])
            check=client.post('https://api.weixin.qq.com/wxa/msg_sec_check',params=params,json={'version':2,'scene':2,'openid':who['openid'],'content':text}).json()
            if check.get('errcode')==87014 or check.get('result',{}).get('suggest') in ('risky','review'):return 'rejected','文字未通过内容检查，请修改后重新制作'
            if check.get('errcode') in (40001,40014,42001):_token['expires']=0
            if check.get('errcode')!=0 or check.get('result',{}).get('suggest')!='pass':return 'pending','文字检查尚未通过，已私密保存'
            # Check original fixed artwork, avatar and the rendered sample, not just its title.
            images=[]
            for layer in spec['layers']:
                if layer['type']=='asset':images.append((root()/'template_assets'/(layer['value']+'.png')).read_bytes())
            avatar=m['creator'].get('avatar','');sample=open_image(BytesIO(decode_image(avatar))) if avatar else Image.new('RGBA',(256,256),'#ffe8c7')
            if avatar:images.append(decode_image(avatar))
            images.append(render(spec,[sample,sample]).getvalue())
            for raw in images:
                with open_input_image(BytesIO(raw)) as image:
                    image.thumbnail((740,1000));output=BytesIO();image.convert('RGB').save(output,'JPEG',quality=80)
                check=client.post('https://api.weixin.qq.com/wxa/img_sec_check',params=params,files={'media':('template.jpg',output.getvalue(),'image/jpeg')}).json()
                if check.get('errcode')==87014:return 'rejected','图片未通过内容检查，模板暂不公开'
                if check.get('errcode') in (40001,40014,42001):_token['expires']=0
                if check.get('errcode')!=0:return 'pending','图片检查尚未通过，已保存到我的模板，可稍后重试发布'
        return 'published','检查通过，已经加入模板仓库'
    except (httpx.HTTPError,ValueError,KeyError,OSError):return 'pending','内容检查暂时繁忙，已私密保存，稍后可重试发布'


def publish_owned(identifier,user):
    row=own_template(identifier,user)
    if json.loads(row['metadata']).get('requires_review'):raise HTTPException(409,'请先校对草稿中的文字和布局，再申请发布')
    if row['status']=='published':return template_view(row)
    status,message=moderate(row)
    if status=='published':
        from .catalog import publish
        public_metadata={k:v for k,v in json.loads(row['metadata']).items() if k!='operations'}
        publish(identifier,public_metadata,json.loads(row['spec']))
    db=init()
    with db:db.execute('UPDATE studio_templates SET status=?,message=?,updated=? WHERE id=?',(status,message,time.time(),identifier))
    db.close();return template_view(own_template(identifier,user))


class PublishRequest(BaseModel):
    rights_attested: bool=False


@router.post('/templates/{identifier}/publish')
def publish_template(identifier:str,params:PublishRequest,user=Depends(current_user)):
    if not params.rights_attested:raise HTTPException(422,'请确认你有权发布这些素材')
    # Persisted queue avoids repeated taps and expensive moderation in the API thread.
    row=own_template(identifier,user)
    if json.loads(row['metadata']).get('requires_review'):raise HTTPException(409,'请先校对草稿中的文字和布局，再申请发布')
    return enqueue('publish',{'template_id':identifier},identifier+str(row['updated']),user)


@router.post('/templates/ai',status_code=201)
def create_ai_template(params:AIRequest,user=Depends(current_user)):
    if not params.rights_attested:raise HTTPException(422,'请确认你有权制作并发布这张表情图')
    raw=decode_image(params.image)
    return enqueue('template',{'image':base64.b64encode(raw).decode()},params.idempotency_key,user)


@router.get('/quota')
def authoring_quota(user=Depends(current_user)):
    db=init();day=datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat()
    try:used=db.execute('SELECT 1 FROM studio_ai_daily WHERE user_id=? AND day=?',(user['id'],day)).fetchone()
    finally:db.close()
    return {'ai_template_limit':1,'remaining':0 if used else 1,'day':day}


def work_one():
    db=init();stamp=time.time()
    try:
        with db:
            db.execute('BEGIN IMMEDIATE')
            db.execute("UPDATE studio_jobs SET status=CASE WHEN attempts>=2 THEN 'failed' ELSE 'queued' END,message='任务中断，正在恢复',updated=? WHERE status='running' AND lease<?",(stamp,stamp))
            job=db.execute("SELECT * FROM studio_jobs WHERE status='queued' ORDER BY created LIMIT 1").fetchone()
            if not job:return False
            db.execute("UPDATE studio_jobs SET status='running',lease=?,attempts=attempts+1,updated=?,message='小窝正在认真制作中' WHERE id=?",(stamp+300,stamp,job['id']))
        payload=json.loads(job['payload']);result='';message=''
        try:
            if job['kind'] in ('manual','livegif'):
                directory=root()/'studio_replays';directory.mkdir(exist_ok=True)
                write_bytes(directory/(job['id']+'.json'),json.dumps(payload).encode(),job['user_id'])
            if job['kind']=='livegif':
                from .livegif import render_job
                output=render_job(payload,job['user_id'])
                directory=root()/'studio_results';directory.mkdir(exist_ok=True);write_bytes(directory/job['id'],output,job['user_id'])
                message='动图已经活起来啦！';status='completed'
            elif job['kind']=='manual':
                images=[base64.b64decode(i) for i in payload['images']]
                if payload['extract_subject']:
                    from .subjects import extract_subject
                    images=[extract_subject(i) for i in images]
                spec=get_spec(payload['template_key'],job['user_id'])
                if spec is not None:output=render(spec,[open_image(BytesIO(i)).convert('RGBA') for i in images],payload['texts'])
                else:
                    from .catalog import refresh
                    from ..manager import get_meme
                    refresh();output=get_meme(payload['template_key'])(images=images,texts=payload['texts'],args=payload['args'])
                directory=root()/'studio_results';directory.mkdir(exist_ok=True);write_bytes(directory/job['id'],output.getvalue(),job['user_id'])
                from .popularity import record
                record(payload['template_key'],'studio:'+job['user_id'],'generate')
                message='损图出炉啦，快来收下！';status='completed'
            elif job['kind']=='template':
                from .storage import write_guard
                with write_guard(job['user_id'], 4*1024*1024, template=True):
                    from .quality import convert_caption
                    raw=base64.b64decode(payload['image'])
                    spec,metadata=convert_caption(raw,{'origin':'user-provided','review':{'explicit_user_request':True}},publish_result=False,allow_draft=True)
                    result=save_template(job['user_id'],metadata['name'],spec,[{'action':'ai-caption-detection','quality':metadata.get('quality',{})}],metadata)
                    if metadata.get('requires_review'):
                        status='completed';message='已识别为私有草稿，请在管理素材中校对文字和布局后申请发布'
                    else:
                        published=publish_owned(result,{'id':job['user_id']})
                        status='completed';message='模板识别完成，'+published['message']
            else:
                published=publish_owned(payload['template_id'],{'id':job['user_id']});result=payload['template_id'];status='completed';message=published['message']
        except Exception as error:
            status='needs_manual' if job['kind']=='template' else 'failed'
            message='未能可靠识别，次数已退回；可改用手动创作（不会自动公开）' if job['kind']=='template' else '这次没出炉，请检查素材和文字后重试'
            if isinstance(error,HTTPException):message=error.detail
            # No private payloads/provider URLs in logs.
            print('studio job',job['id'],type(error).__name__,flush=True)
        with db:
            db.execute('UPDATE studio_jobs SET status=?,result=?,message=?,payload=\'{}\',updated=? WHERE id=?',(status,result,message,time.time(),job['id']))
            if job['kind']=='template' and status in ('needs_manual','failed'):
                db.execute('DELETE FROM studio_ai_daily WHERE job_id=?',(job['id'],))
        return True
    finally:db.close()


def cleanup():
    db=init()
    try:
        paths=[r['id'] for r in db.execute('SELECT id FROM studio_jobs WHERE created<?',(time.time()-TTL,))]
        with db:
            db.execute('DELETE FROM studio_jobs WHERE created<?',(time.time()-TTL,))
            db.execute("DELETE FROM studio_ai_daily WHERE day<date('now','-30 days')")
        for identifier in paths:
            (root()/'studio_results'/identifier).unlink(missing_ok=True)
            (root()/'studio_replays'/(identifier+'.json')).unlink(missing_ok=True)
        with db:db.execute('DELETE FROM studio_views WHERE job_id NOT IN (SELECT id FROM studio_jobs)')
        from .livegif import cleanup as clean_live
        clean_live()
        from .storage import collect_orphans
        collect_orphans()
        from .lifecycle import resume_deletions
        resume_deletions()
        with db:
            db.execute('DELETE FROM studio_ai_attempts WHERE created<?',(time.time()-86400,))
            db.execute("DELETE FROM studio_ai_daily WHERE job_id IN (SELECT id FROM studio_jobs WHERE status IN ('failed','needs_manual'))")
    finally:db.close()
