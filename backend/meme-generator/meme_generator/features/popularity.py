"""Bounded aggregate popularity. No photos, captions or raw IPs in analytics."""
import hashlib
import math
import time
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from .store import connect, root

router = APIRouter()
KINDS = ('click', 'favorite', 'generate', 'ai_generate', 'ai_exposure', 'ai_choose', 'ai_download')
_snapshots = {}


def actor(request: Request):
    authorization = request.headers.get('authorization', '')
    if authorization.lower().startswith('bearer '):
        from ..account import current_user
        try:
            return 'user:' + current_user(HTTPAuthorizationCredentials(scheme='Bearer', credentials=authorization[7:]))['id']
        except HTTPException:
            pass
    visitor = request.headers.get('x-gensticker-visitor', '')
    if len(visitor) < 16 or len(visitor) > 80 or not visitor.replace('-', '').isalnum():
        visitor = 'anonymous'
    return 'guest:' + hashlib.sha256(visitor.encode()).hexdigest()


def record(key, identity, kind, *, dedup=None, db=None):
    if kind not in KINDS:
        return False
    own = db is None
    db = db or connect()
    now = time.time()
    date = datetime.fromtimestamp(now, timezone.utc).strftime('%Y-%m-%d')
    # Clicks: once/minute/template/actor. Other interactions: once/day,
    # server generated AI slots: once/job/slot even after crash recovery.
    token = dedup or (uuid.uuid4().hex if kind == 'generate' else str(int(now // 60)) if kind == 'click' else date)
    digest = hashlib.sha256(f'{identity}:{key}:{kind}:{token}'.encode()).hexdigest()
    try:
        if not db.execute('SELECT 1 FROM templates WHERE key=? AND status=?', (key, 'published')).fetchone():
            return False
        if own:
            db.execute('BEGIN IMMEDIATE')
        identity = hashlib.sha256(identity.encode()).hexdigest()
        # Bounds protect SQLite and reduce simple client event replay.
        if db.execute('SELECT COUNT(*) FROM popularity_seen WHERE actor=? AND created>?', (identity, now-86400)).fetchone()[0] >= 300:
            return False
        cursor = db.execute('INSERT OR IGNORE INTO popularity_seen VALUES(?,?,?)', (digest, identity, now))
        if not cursor.rowcount:
            return False
        db.execute('INSERT INTO popularity_daily(key,day,kind,count) VALUES(?,?,?,1) ON CONFLICT(key,day,kind) DO UPDATE SET count=count+1', (key, date, kind))
        db.execute('INSERT INTO popularity_totals(key,kind,count) VALUES(?,?,1) ON CONFLICT(key,kind) DO UPDATE SET count=count+1', (key, kind))
        if own:
            db.commit()
        _snapshots.pop(str(root()), None)
        return True
    finally:
        if own:
            db.close()


def snapshot():
    cache_key = str(root())
    hit = _snapshots.get(cache_key)
    if hit and time.time() - hit[0] < 30:
        return hit[1]
    db = connect()
    now = time.time()
    metrics = {}
    try:
        for row in db.execute('SELECT * FROM popularity_totals'):
            metrics.setdefault(row['key'], {'counts': {k: 0 for k in KINDS}, 'heat': 0, 'recent': {}})['counts'][row['kind']] = row['count']
        for row in db.execute('SELECT * FROM popularity_daily WHERE day>=date("now","-7 days")'):
            stats = metrics.setdefault(row['key'], {'counts': {k: 0 for k in KINDS}, 'heat': 0, 'recent': {}})
            age = max(0, (now-datetime.strptime(row['day'], '%Y-%m-%d').replace(tzinfo=timezone.utc).timestamp())/86400)
            stats['recent'][row['kind']] = stats['recent'].get(row['kind'], 0) + row['count'] * 2**(-age/3)
        for stats in metrics.values():
            r = stats.pop('recent')
            usage = .4*r.get('click',0) + 4*r.get('favorite',0) + 3*r.get('generate',0) + .4*r.get('ai_generate',0) + 3*r.get('ai_choose',0) + 4*r.get('ai_download',0)
            # Exposure alone cannot dominate the chart; smoothed conversion is bounded.
            conversion = min(1, (r.get('ai_choose',0)+1)/(r.get('ai_exposure',0)+10))
            stats['heat'] = round(20*math.log1p(usage)*(1+.2*conversion), 1)
        _snapshots[cache_key] = (now, metrics)
        return metrics
    finally:
        db.close()


class Event(BaseModel):
    key: str = Field(min_length=1, max_length=100)
    kind: str = Field(pattern='^(click|favorite)$')
    receipt: str = Field(default='', max_length=512)


@router.post('/templates/events')
def event(params: Event, request: Request):
    identity = actor(request)
    return {'recorded': record(params.key, identity, params.kind)}


@router.get('/templates/popularity')
def popularity():
    return {'algorithm': 'decayed-usage-v1', 'window_days': 7, 'metrics': snapshot()}


def maintenance(db):
    db.execute('DELETE FROM popularity_seen WHERE created<?', (time.time()-90*86400,))
    db.execute('DELETE FROM popularity_daily WHERE day<date("now","-90 days")')
