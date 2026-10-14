"""Public, bounded Canvas recipes, never executable code or user images."""
import base64
import hashlib
import hmac
import json
import secrets
import time
from fastapi import APIRouter, Request, HTTPException, Response
from .catalog import declared
from .declarative import TemplateSpec
from .store import connect, root

router = APIRouter()


def secret():
    db = connect()
    try:
        with db:
            db.execute('INSERT OR IGNORE INTO feature_settings VALUES(?,?)', ('render_secret', secrets.token_bytes(32)))
        return db.execute('SELECT value FROM feature_settings WHERE name=?', ('render_secret',)).fetchone()[0]
    finally:
        db.close()


def receipt(key, version, identity):
    payload = base64.urlsafe_b64encode(json.dumps({'key':key, 'version':version, 'actor':identity, 'expires':int(time.time())+300, 'nonce':secrets.token_hex(16)}, separators=(',',':')).encode()).decode()
    return payload + '.' + hmac.new(secret(), payload.encode(), hashlib.sha256).hexdigest()


def verify_receipt(token, key, identity):
    try:
        payload, signature = token.split('.')
        if not hmac.compare_digest(signature, hmac.new(secret(), payload.encode(), hashlib.sha256).hexdigest()):
            raise ValueError()
        data = json.loads(base64.urlsafe_b64decode(payload))
        if data['key'] != key or data['actor'] != identity or data['expires'] < time.time() or declared(key)['version'] != data['version']:
            raise ValueError()
        return data['nonce']
    except (ValueError, KeyError, TypeError):
        raise HTTPException(422, '本地生成凭据已失效')


@router.get('/memes/{key}/client-template')
def recipe(key: str, request: Request, response: Response):
    response.headers['Cache-Control'] = 'private, no-store'
    try:
        row = declared(key)
    except HTTPException:
        return {'supported':False}
    spec = TemplateSpec.model_validate_json(row['spec'])
    metadata = json.loads(row['metadata'])
    # Static bounded DSL only. No rotations, effects, animation or custom args.
    if spec.width > 768 or spec.height > 768 or len(spec.layers)>12:
        return {'supported':False}
    assets = sorted({l.value for l in spec.layers if l.type == 'asset'})
    if len(assets)>6 or any(not (root()/'template_assets'/f'{a}.png').is_file() for a in assets):
        return {'supported':False}
    if sum((root()/'template_assets'/f'{a}.png').stat().st_size for a in assets)>1024*1024:
        return {'supported':False}
    from .popularity import actor
    return {'supported':True, 'key':key, 'version':row['version'], 'spec':spec.model_dump(), 'assets':{a:f'/template-assets/{a}.png' for a in assets}, 'attribution':{k:metadata.get(k,'') for k in ('author','license','source_url','license_url')}, 'receipt':receipt(key,row['version'],actor(request)), 'expires':int(time.time())+300}


@router.get('/template-assets/{identifier}.png')
def asset(identifier: str):
    if len(identifier)!=64 or any(c not in '0123456789abcdef' for c in identifier):
        raise HTTPException(404, '素材不存在')
    # Serve only hashes referenced by published public templates.
    db = connect()
    try:
        specs = db.execute("SELECT spec FROM templates WHERE spec IS NOT NULL AND status='published'").fetchall()
        if not any(any(l.get('type')=='asset' and l.get('value')==identifier for l in json.loads(r['spec'])['layers']) for r in specs):
            raise HTTPException(404, '素材不存在')
    finally:
        db.close()
    path = root()/'template_assets'/f'{identifier}.png'
    if not path.is_file() or path.stat().st_size>1024*1024:
        raise HTTPException(404, '素材不存在')
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest()!=identifier:
        raise HTTPException(503, '素材校验失败')
    return Response(data, media_type='image/png', headers={'Cache-Control':'public, max-age=86400', 'ETag':identifier})
