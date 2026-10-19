"""One-use, account-bound bridge from Apple's native Live Photo picker.

The shortcut holds no account credential. A random upload capability expires in
10 minutes and can create one private, bounded media asset, never a generation.
"""
import hashlib,secrets,time
from fastapi import APIRouter,Depends,Header,HTTPException,Request
from fastapi.responses import FileResponse
from .store import connect
from . import livegif
from ..account import current_user
router=APIRouter(prefix='/studio/live/imports')
TTL=600
MAX_BYTES=8*1024*1024

def db_open():
    db=connect()
    db.execute('''CREATE TABLE IF NOT EXISTS live_imports (
        id TEXT PRIMARY KEY,user_id TEXT NOT NULL,created REAL NOT NULL,
        status TEXT NOT NULL,asset_id TEXT)''')
    db.commit()
    return db

def lookup(identifier,user=None):
    if len(identifier)!=64 or any(c not in '0123456789abcdef' for c in identifier):raise HTTPException(404,'导入入口不存在')
    db=db_open()
    try:row=db.execute('SELECT * FROM live_imports WHERE id=?',(identifier,)).fetchone()
    finally:db.close()
    if not row or (user is not None and row['user_id']!=user):raise HTTPException(404,'导入入口不存在')
    if row['created']<time.time()-TTL:raise HTTPException(410,'导入口令已过期，请重新复制')
    return dict(row)

@router.post('',status_code=201)
def create(user=Depends(current_user)):
    token=secrets.token_hex(32);identifier=hashlib.sha256(token.encode()).hexdigest();now=time.time();db=db_open()
    try:
        with db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT COUNT(*) FROM live_imports WHERE user_id=? AND created>?',(user['id'],now-60)).fetchone()[0]>=4:raise HTTPException(429,'口令已准备好，稍等一分钟再换新的')
            db.execute('DELETE FROM live_imports WHERE created<?',(now-86400,))
            db.execute('INSERT INTO live_imports VALUES(?,?,?,?,NULL)',(identifier,user['id'],now,'waiting'))
    finally:db.close()
    return {'id':identifier,'token':token,'expires_at':now+TTL}

@router.post('/receive',status_code=201)
async def receive(request:Request,x_live_import:str=Header(default='')):
    if len(x_live_import)!=64 or any(c not in '0123456789abcdef' for c in x_live_import):raise HTTPException(401,'请先在小程序复制 Live 导入口令')
    identifier=hashlib.sha256(x_live_import.encode()).hexdigest();row=lookup(identifier)
    db=db_open()
    try:
        with db:
            changed=db.execute("UPDATE live_imports SET status='uploading' WHERE id=? AND status='waiting'",(identifier,)).rowcount
        if not changed:raise HTTPException(409,'这个口令已经使用，请回到小程序接收动态片段')
    finally:db.close()
    result=None
    try:
        raw=bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw)>MAX_BYTES:raise HTTPException(413,'Live 动态片段最多 8 MB，请选择一张原始 Live 图')
        from asyncio import to_thread
        result=await to_thread(livegif.prepare,bytes(raw),row['user_id'])
        if result['duration']>10:raise HTTPException(422,'Live 直连接受 10 秒内动态片段，长视频请在小程序选取')
        db=db_open()
        try:
            with db:db.execute("UPDATE live_imports SET status='ready',asset_id=? WHERE id=?",(result['asset_id'],identifier))
        finally:db.close()
        return {'message':'动态片段已送达。回到 GenSticker，点击“接收动态片段”继续裁剪。'}
    except BaseException:
        if result:
            for ext in ('.media','.jpg','.json'):(livegif.directory()/(result['asset_id']+ext)).unlink(missing_ok=True)
        db=db_open()
        try:
            with db:db.execute("UPDATE live_imports SET status='waiting' WHERE id=? AND status='uploading'",(identifier,))
        finally:db.close()
        raise

@router.get('/{identifier}')
def status(identifier:str,user=Depends(current_user)):
    row=lookup(identifier,user['id'])
    if row['status']!='ready':return {'status':row['status']}
    meta=livegif.own(row['asset_id'],user['id'])
    return {'status':'ready','asset':{'asset_id':row['asset_id'],**{k:meta[k] for k in ('width','height','duration')},'poster_url':f"/studio/live/assets/{row['asset_id']}/poster"}}

@router.get('/{identifier}/media')
def media(identifier:str,user=Depends(current_user)):
    row=lookup(identifier,user['id'])
    if row['status']!='ready':raise HTTPException(409,'动态片段还没有送达')
    livegif.own(row['asset_id'],user['id'])
    return FileResponse(livegif.directory()/(row['asset_id']+'.media'),media_type='video/mp4',headers={'Cache-Control':'private, no-store'})
