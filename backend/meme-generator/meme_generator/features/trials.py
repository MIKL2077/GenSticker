"""A batch winner, or a daily rotating fallback; never fabricated popularity."""
from datetime import datetime, timedelta, timezone
import json
import hashlib
import time
from fastapi import APIRouter, Response, Request, HTTPException
from pydantic import BaseModel, Field
from .popularity import actor
from .store import connect

router=APIRouter()
BEIJING=timezone(timedelta(hours=8))


@router.get('/templates/trial')
def current_trial(response:Response,request:Request):
    response.headers['Cache-Control']='no-store'
    response.headers['Vary']='Authorization, X-Gensticker-Visitor'
    db=connect()
    try:
        rows=list(db.execute("SELECT t.id,t.key,t.version,t.metadata,p.batch_id,p.published,p.score FROM templates t LEFT JOIN template_publications p ON p.key=t.key WHERE t.status='published' AND t.key NOT IN (SELECT key FROM template_blocks)"))
        automated=[r for r in rows if r['batch_id']]
        if automated:
            latest=max(r['published'] for r in automated)
            batch=max(automated,key=lambda r:r['published'])['batch_id']
            candidates=[r for r in automated if r['batch_id']==batch]
            candidates.sort(key=lambda r:(-r['score'],r['key']))
            # Even a partial one-template batch must not freeze the daily card.
            others=sorted((r for r in automated if r['batch_id']!=batch),key=lambda r:(-r['published'],-r['score'],r['key']))
            candidates.extend(others[:max(0,14-len(candidates))])
            if len(candidates)<2:
                curated=[r for r in rows if not r['batch_id'] and json.loads(r['metadata']).get('origin') not in {'user-provided','user'}]
                curated.sort(key=lambda r:r['key'])
                candidates.extend(curated[:14-len(candidates)])
            first=datetime.fromtimestamp(latest,BEIJING).date()
            offset=max(0,(datetime.now(BEIJING).date()-first).days)
            selected=candidates[offset%len(candidates)]
            fresh=bool(selected['published'] and (datetime.now(BEIJING).timestamp()-selected['published'])<14*86400)
        else:
            candidates=[r for r in rows if json.loads(r['metadata']).get('origin') not in {'user-provided','user'}]
            if not candidates:return None
            candidates.sort(key=lambda r:(-float(json.loads(r['metadata']).get('created_at') or json.loads(r['metadata']).get('collected_at') or 0),r['key']))
            candidates=candidates[:14]
            selected=candidates[datetime.now(BEIJING).date().toordinal()%len(candidates)]
            fresh=False
        meta=json.loads(selected['metadata'])
        identity=hashlib.sha256(actor(request).encode()).hexdigest()
        used=bool(db.execute('SELECT 1 FROM template_trial_uses WHERE actor=? AND key=?',(identity,selected['key'])).fetchone())
        return {'key':selected['key'],'version':selected['version'],'name':meta['name'],
                'trial_id':f"{selected['batch_id'] or datetime.now(BEIJING).date().isoformat()}:{selected['key']}:{selected['version']}",
                'label':'新模板试用' if fresh else '精选模板试用','image_slots':meta.get('max_images',0),'used':used}
    finally:db.close()


class TrialUse(BaseModel):
    key:str=Field(min_length=1,max_length=100,pattern=r'^[A-Za-z0-9_-]+$')


@router.post('/templates/trial/use',status_code=204)
def use_trial(params:TrialUse,request:Request):
    identity=hashlib.sha256(actor(request).encode()).hexdigest();db=connect()
    try:
        if not db.execute("SELECT 1 FROM templates WHERE key=? AND status='published'",(params.key,)).fetchone():raise HTTPException(404,'模板暂时不可用')
        with db:
            db.execute('INSERT OR REPLACE INTO template_trial_uses VALUES(?,?,?)',(identity,params.key,time.time()))
            db.execute('DELETE FROM template_trial_uses WHERE actor=? AND key NOT IN (SELECT key FROM template_trial_uses WHERE actor=? ORDER BY used DESC LIMIT 128)',(identity,identity))
    finally:db.close()
