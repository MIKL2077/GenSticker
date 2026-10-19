"""WeChat identity and a user-scoped template library. No uploaded images are stored."""
import base64
import binascii
from io import BytesIO
from PIL import Image, UnidentifiedImageError
import hashlib
import os
from pathlib import Path
import secrets
import sqlite3
import time
import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from .dirs import get_data_dir
from .manager import get_meme_keys

router = APIRouter()
bearer = HTTPBearer(auto_error=False)
SESSION_DAYS = 7
MAX_RECORDS = 100


def connection():
    directory = Path(os.environ['GENSTICKER_STATE_DIR']) if os.environ.get('GENSTICKER_STATE_DIR') else get_data_dir()
    directory.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(directory / 'accounts.sqlite3', timeout=10)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('PRAGMA journal_mode=WAL')
    db.executescript('''
        CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, openid TEXT UNIQUE NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions (hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), expires INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS favorites (user_id TEXT NOT NULL REFERENCES users(id), key TEXT NOT NULL, added_at INTEGER NOT NULL, PRIMARY KEY(user_id,key));
        CREATE TABLE IF NOT EXISTS history (user_id TEXT NOT NULL REFERENCES users(id), key TEXT NOT NULL, visited_at INTEGER NOT NULL, PRIMARY KEY(user_id,key));
    ''')
    columns = {r[1] for r in db.execute("PRAGMA table_info(users)")}
    for column in ("name", "avatar"):
        if column not in columns:
            db.execute(f"ALTER TABLE users ADD COLUMN {column} TEXT")
    db.commit()
    return db


def now_ms():
    return int(time.time() * 1000)


def check_key(key: str):
    if key not in get_meme_keys():
        raise HTTPException(404, '这个模板暂时不可用')


def current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer)):
    if not credentials or credentials.scheme.lower() != 'bearer':
        raise HTTPException(401, '请先登录', headers={'WWW-Authenticate': 'Bearer'})
    digest = hashlib.sha256(credentials.credentials.encode()).hexdigest()
    db = connection()
    try:
        row = db.execute('SELECT user_id FROM sessions WHERE hash=? AND expires>?', (digest, int(time.time()))).fetchone()
        if not row:
            raise HTTPException(401, '登录已过期，请重新登录', headers={'WWW-Authenticate': 'Bearer'})
        return {'id': row['user_id'], 'token_hash': digest}
    finally:
        db.close()


class LoginRequest(BaseModel):
    code: str = Field(min_length=1, max_length=256)


class HistoryRecord(BaseModel):
    key: str = Field(min_length=1, max_length=100)
    visited_at: int = Field(ge=0)


class MergeRequest(BaseModel):
    favorite_keys: list[str] = Field(default_factory=list, max_length=MAX_RECORDS)
    history: list[HistoryRecord] = Field(default_factory=list, max_length=MAX_RECORDS)


def trim(db, user_id, table, column):
    # table and column are fixed internal identifiers, never request values.
    db.execute(f'DELETE FROM {table} WHERE user_id=? AND key NOT IN (SELECT key FROM {table} WHERE user_id=? ORDER BY {column} DESC LIMIT ?)', (user_id, user_id, MAX_RECORDS))


@router.get('/account/config')
def account_config():
    # AppID is public; never expose AppSecret or provider credentials.
    return {'login_enabled': bool(os.getenv('WX_APPID') and os.getenv('WX_APP_SECRET')), 'app_id': os.getenv('WX_APPID') or '', 'features': {'studio': True, 'reroll': True, 'template_editor': True, 'livegif': True}}


@router.post('/auth/wechat')
async def login(params: LoginRequest):
    appid, secret = os.getenv('WX_APPID'), os.getenv('WX_APP_SECRET')
    if not appid or not secret:
        raise HTTPException(503, '微信登录尚未配置，历史和收藏仍可在本机使用')
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get('https://api.weixin.qq.com/sns/jscode2session', params={'appid': appid, 'secret': secret, 'js_code': params.code, 'grant_type': 'authorization_code'})
            response.raise_for_status()
            identity = response.json()
    except (httpx.HTTPError, ValueError):
        # Never surface the provider URL: its query contains AppSecret.
        raise HTTPException(502, '微信登录服务暂时不可用，请稍后重试')
    if not isinstance(identity, dict):
        raise HTTPException(502, '微信登录服务返回格式错误，请稍后重试')
    openid = identity.get('openid')
    if identity.get('errcode') or not isinstance(openid, str) or not openid:
        raise HTTPException(400, '微信登录凭证无效，请重新登录')
    token = secrets.token_urlsafe(32)
    expires = int(time.time()) + SESSION_DAYS * 86400
    db = connection()
    try:
        with db:
            db.execute('INSERT OR IGNORE INTO users(id,openid) VALUES (?,?)', (uuid.uuid4().hex, openid))
            user_id = db.execute('SELECT id FROM users WHERE openid=?', (openid,)).fetchone()['id']
            db.execute('DELETE FROM sessions WHERE expires<=?', (int(time.time()),))
            db.execute('INSERT INTO sessions VALUES (?,?,?)', (hashlib.sha256(token.encode()).hexdigest(), user_id, expires))
        return {'access_token': token, 'expires_at': expires, 'profile': profile(user_id, db)}
    finally:
        db.close()


@router.get('/auth/me')
def me(user=Depends(current_user)):
    db = connection()
    try:
        return profile(user['id'], db)
    finally:
        db.close()


def profile(user_id, db):
    row = db.execute('SELECT name,avatar FROM users WHERE id=?', (user_id,)).fetchone()
    return {'id': user_id, 'name': row['name'] or '微信用户', 'avatar': row['avatar'] or ''}


class ProfileRequest(BaseModel):
    name: str = Field(min_length=1, max_length=32)
    avatar: str | None = Field(default=None, max_length=350000)


@router.put('/account/profile')
def update_profile(params: ProfileRequest, user=Depends(current_user)):
    name = params.name.strip()
    if not name:
        raise HTTPException(422, '请输入昵称')
    avatar = None
    if params.avatar is not None:
        try:
            raw = base64.b64decode(params.avatar, validate=True)
            with Image.open(BytesIO(raw)) as image:
                if image.width * image.height > 16000000:
                    raise ValueError('image too large')
                image.thumbnail((128, 128))
                output = BytesIO()
                image.convert('RGB').save(output, format='JPEG', quality=80)
                avatar = base64.b64encode(output.getvalue()).decode()
        except (ValueError, binascii.Error, UnidentifiedImageError, OSError, Image.DecompressionBombError):
            raise HTTPException(422, '头像无效，请重新选择')
    db = connection()
    try:
        with db:
            db.execute('UPDATE users SET name=?,avatar=COALESCE(?,avatar) WHERE id=?', (name, avatar, user['id']))
        return profile(user['id'], db)
    finally:
        db.close()


@router.delete('/auth/session', status_code=204)
def logout(user=Depends(current_user)):
    db = connection()
    try:
        with db:
            db.execute('DELETE FROM sessions WHERE hash=?', (user['token_hash'],))
    finally:
        db.close()
    return Response(status_code=204)


@router.get('/account/library')
def library(user=Depends(current_user)):
    db = connection()
    try:
        valid = set(get_meme_keys())
        favorites = [r['key'] for r in db.execute('SELECT key FROM favorites WHERE user_id=? ORDER BY added_at DESC', (user['id'],)) if r['key'] in valid]
        history = [dict(r) for r in db.execute('SELECT key,visited_at FROM history WHERE user_id=? ORDER BY visited_at DESC', (user['id'],)) if r['key'] in valid]
        return {'favorite_keys': favorites, 'history': history}
    finally:
        db.close()


@router.post('/account/library/merge')
def merge(params: MergeRequest, user=Depends(current_user)):
    valid = set(get_meme_keys())
    db = connection()
    try:
        with db:
            for key in params.favorite_keys:
                if key in valid:
                    db.execute('INSERT OR IGNORE INTO favorites VALUES (?,?,?)', (user['id'], key, now_ms()))
            for record in params.history:
                if record.key in valid:
                    db.execute('INSERT INTO history VALUES (?,?,?) ON CONFLICT(user_id,key) DO UPDATE SET visited_at=MAX(visited_at,excluded.visited_at)', (user['id'], record.key, min(record.visited_at, now_ms())))
            trim(db, user['id'], 'favorites', 'added_at')
            trim(db, user['id'], 'history', 'visited_at')
    finally:
        db.close()
    return library(user)


@router.put('/account/favorites/{key}')
def favorite(key: str, user=Depends(current_user)):
    check_key(key)
    db = connection()
    try:
        with db:
            db.execute('BEGIN IMMEDIATE')
            count = db.execute('SELECT COUNT(*) FROM favorites WHERE user_id=?', (user['id'],)).fetchone()[0]
            exists = db.execute('SELECT 1 FROM favorites WHERE user_id=? AND key=?', (user['id'], key)).fetchone()
            if count >= MAX_RECORDS and not exists:
                raise HTTPException(409, '收藏最多 100 个模板，请先取消一些收藏')
            db.execute('INSERT OR IGNORE INTO favorites VALUES (?,?,?)', (user['id'], key, now_ms()))
    finally:
        db.close()
    from .features.popularity import record
    if not exists:
        record(key, 'user:' + user['id'], 'favorite')
    return {'key': key, 'favorite': True}


@router.delete('/account/favorites/{key}', status_code=204)
def unfavorite(key: str, user=Depends(current_user)):
    db = connection()
    try:
        with db:
            db.execute('DELETE FROM favorites WHERE user_id=? AND key=?', (user['id'], key))
    finally:
        db.close()
    return Response(status_code=204)


@router.put('/account/history/{key}')
def visit(key: str, user=Depends(current_user)):
    check_key(key)
    db = connection()
    try:
        with db:
            db.execute('INSERT INTO history VALUES (?,?,?) ON CONFLICT(user_id,key) DO UPDATE SET visited_at=excluded.visited_at', (user['id'], key, now_ms()))
            trim(db, user['id'], 'history', 'visited_at')
    finally:
        db.close()
    return {'key': key}


@router.delete('/account/history', status_code=204)
def clear_history(user=Depends(current_user)):
    db = connection()
    try:
        with db:
            db.execute('DELETE FROM history WHERE user_id=?', (user['id'],))
    finally:
        db.close()
    return Response(status_code=204)
