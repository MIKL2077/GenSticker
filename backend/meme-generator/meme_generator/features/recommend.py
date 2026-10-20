from meme_generator.safe_images import open_image, open_input_image
import asyncio
import hashlib
import json
import os
import time
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo
from io import BytesIO
from pathlib import Path
from PIL import Image, ImageOps, UnidentifiedImageError
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Response, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from ..account import current_user
from .store import connect, root

router = APIRouter(prefix="/recommend")
normalization_slots = asyncio.Semaphore(2)
# Zero means unlimited; operators may still opt into a daily budget.
USER_LIMIT = max(0, int(os.getenv("GENSTICKER_DAILY_LIMIT", "0")))
GLOBAL_LIMIT = max(0, int(os.getenv("GENSTICKER_GLOBAL_LIMIT", "0")))


def admit_generation(db, user_id, identifier, stamp):
    """Call inside BEGIN IMMEDIATE. Reservations survive job deletion/restarts."""
    db.execute("CREATE TABLE IF NOT EXISTS generation_admissions(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,created REAL NOT NULL)")
    db.execute("CREATE INDEX IF NOT EXISTS generation_admissions_user_time ON generation_admissions(user_id,created)")
    if db.execute('SELECT 1 FROM generation_admissions WHERE id=?',(identifier,)).fetchone():return
    db.execute("DELETE FROM generation_admissions WHERE created<?", (stamp-3600,))
    for window, limit in ((60, 8), (3600, 80)):
        recent = list(db.execute("SELECT created FROM generation_admissions WHERE user_id=? AND created>? ORDER BY created", (user_id,stamp-window)))
        if len(recent) >= limit:
            retry = max(1, int(recent[0]['created']+window-stamp)+1)
            raise HTTPException(429, f"生成有点快，{retry} 秒后再来，已有作品都还在", headers={'Retry-After':str(retry)})
    db.execute("INSERT INTO generation_admissions VALUES(?,?,?)", (identifier,user_id,stamp))


def day():
    return datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()


def normalize(raw):
    if len(raw) > 3 * 1024 * 1024:
        raise HTTPException(413, "照片不能超过3MB，请压缩后上传")
    try:
        with open_input_image(BytesIO(raw)) as original:
            if original.width * original.height > 24000000:
                raise ValueError("too many pixels")
            image = ImageOps.exif_transpose(original).convert("RGBA")
            image.thumbnail((1280, 1280))
            image.info.clear()
            out = BytesIO()
            image.save(out, "PNG")
            return out.getvalue()
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError):
        raise HTTPException(422, "照片格式无效或尺寸过大")


@router.post("/assets", status_code=201)
async def upload(file: UploadFile = File(...), subject_selected:bool=Form(default=False), user=Depends(current_user)):
    from meme_generator.features.storage import write_guard
    raw = await file.read(3 * 1024 * 1024 + 1)
    if normalization_slots.locked():
        raise HTTPException(503, "照片处理繁忙，请稍后重试")
    async with normalization_slots:
        normalized = await asyncio.to_thread(normalize, raw)
    with write_guard(user['id'], len(normalized) + 65536, ingress=len(raw),photo=True):
        identifier = uuid.uuid4().hex
        db = connect()
        try:
            digest = hashlib.sha256(normalized+(b':user-selected' if subject_selected else b'')).hexdigest()
            duplicate = db.execute(
                "SELECT * FROM assets WHERE user_id=? AND hash=? AND created>?",
                (user["id"], digest, time.time() - 86400),
            ).fetchone()
            if duplicate and Path(duplicate["path"]).is_file():
                return {
                    "asset_id": duplicate["id"],
                    "expires_at": duplicate["created"] + 86400,
                }
            if db.execute(
                "SELECT COUNT(*) FROM assets WHERE user_id=? AND created>?",
                (user["id"], time.time() - 60),
            ).fetchone()[0] >= 6:
                raise HTTPException(429, "上传太快啦，请一分钟后再试")
            directory = root() / "private" / user["id"]
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            path = directory / (identifier + (".selected.png" if subject_selected else ".png"))
            path.write_bytes(normalized)
            thumbs=root()/"history_thumbs";thumbs.mkdir(exist_ok=True)
            with open_image(BytesIO(normalized)) as image:
                image.thumbnail((160,160));image.convert("RGB").save(thumbs/(identifier+".jpg"),"JPEG",quality=70)
            with db:
                db.execute(
                    "INSERT INTO assets VALUES(?,?,?,?,?)",
                    (identifier, user["id"], digest, time.time(), str(path)),
                )
        finally:
            db.close()
        return {"asset_id": identifier, "expires_at": time.time() + 86400}


# Detection is transient: return coordinates and discard photo bytes.
_detect_recent={}
@router.post('/subjects/detect')
async def detect_subjects(file:UploadFile=File(...),user=Depends(current_user)):
    now=time.time();recent=[stamp for stamp in _detect_recent.get(user['id'],[]) if stamp>now-60]
    if len(recent)>=12:raise HTTPException(429,'选图有点快，稍等一分钟再试；仍可手动框选')
    if len(_detect_recent)>1024:
        for key in list(_detect_recent):
            if not _detect_recent[key] or _detect_recent[key][-1]<now-60:_detect_recent.pop(key,None)
        if len(_detect_recent)>1024:raise HTTPException(503,'主体检测繁忙，可先手动框选')
    _detect_recent[user['id']]=recent+[now]
    raw=await file.read(3*1024*1024+1)
    if normalization_slots.locked():raise HTTPException(503,'主体检测繁忙，可先手动框选')
    def detect():
        normalized=normalize(raw)
        with open_image(BytesIO(normalized)) as image:
            from .portrait import candidate_boxes
            return {'candidates':candidate_boxes(image),'method':'server-opencv'}
    async with normalization_slots:return await asyncio.to_thread(detect)

@router.get('/jobs/{identifier}/source-preview')
def source_preview(identifier:str,user=Depends(current_user)):
    db=connect()
    try:
        job=db.execute('SELECT asset_id FROM jobs WHERE id=? AND user_id=? AND created>?',(identifier,user['id'],time.time()-7*86400)).fetchone()
        if not job:raise HTTPException(404,'记录不存在')
        path=root()/'history_thumbs'/(job['asset_id']+'.jpg')
        if not path.exists():
            source=db.execute('SELECT path FROM assets WHERE id=? AND user_id=?',(job['asset_id'],user['id'])).fetchone()
            if not source or not Path(source['path']).exists():raise HTTPException(404,'原图缩略图已过期')
            path.parent.mkdir(exist_ok=True)
            with open_image(source['path']) as image:
                image.thumbnail((160,160));image.convert('RGB').save(path,'JPEG',quality=70)
        return FileResponse(path,media_type='image/jpeg',headers={'Cache-Control':'private, no-store'})
    finally:db.close()

@router.get("/quota")
def quota(user=Depends(current_user)):
    db = connect()
    try:
        used = (
            db.execute(
                "SELECT COUNT(*) FROM quotas WHERE user_id=? AND day=? AND status!='refunded'",
                (user["id"], day()),
            ).fetchone()[0]
            if USER_LIMIT else 0
        )
        enabled = db.execute(
            "SELECT enabled FROM preferences WHERE user_id=?", (user["id"],)
        ).fetchone()
        return {
            "limit": USER_LIMIT,
            "remaining": max(0, USER_LIMIT - used) if USER_LIMIT else None,
            "unlimited": USER_LIMIT == 0,
            "day": day(),
            "personalization": bool(enabled["enabled"]) if enabled else True,
            "paid_ai_enabled": False,
            "features": {"reroll": True},
        }
    finally:
        db.close()


class CreateJob(BaseModel):
    asset_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    previous_job_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    idempotency_key: str = Field(min_length=8, max_length=100)


@router.post("/jobs", status_code=202)
def create(params: CreateJob, user=Depends(current_user)):
    from .storage import write_guard
    with write_guard(user['id'], 5 * 1024 * 1024,job=True):
        db = connect()
        stamp = time.time()
        identifier = uuid.uuid4().hex
        try:
            with db:
                db.execute("BEGIN IMMEDIATE")
                old = db.execute(
                    "SELECT * FROM jobs WHERE user_id=? AND idempotency=?",
                    (user["id"], params.idempotency_key),
                ).fetchone()
                if old:
                    variation = db.execute(
                        "SELECT parent_id FROM job_variations WHERE job_id=?", (old["id"],)
                    ).fetchone()
                    same_photo = not params.asset_id or old["asset_id"] == params.asset_id
                    same_parent = (variation["parent_id"] if variation else None) == params.previous_job_id
                    if not same_photo or not same_parent:
                        raise HTTPException(409, "重试标识与照片不一致")
                    return {"job_id": old["id"], "status": old["status"]}
                asset_id = params.asset_id
                excluded, previous = set(), set()
                if params.previous_job_id:
                    parent = owned(db, params.previous_job_id, user)
                    if parent["status"] not in ("completed", "failed"):
                        raise HTTPException(409, "上一批还在生成，请稍候")
                    if asset_id and asset_id != parent["asset_id"]:
                        raise HTTPException(409, "换一批需要使用同一张照片")
                    asset_id = parent["asset_id"]
                    previous = {
                        r["key"] for r in db.execute(
                            "SELECT key FROM results WHERE job_id=?", (parent["id"],)
                        )
                    }
                    prior = db.execute(
                        "SELECT excluded_keys FROM job_variations WHERE job_id=?", (parent["id"],)
                    ).fetchone()
                    excluded = set(json.loads(prior["excluded_keys"])) if prior else set()
                    excluded.update(previous)
                if not asset_id:
                    raise HTTPException(422, "请上传照片或选择上一批生成记录")
                heartbeat = db.execute("SELECT * FROM worker_state WHERE id=1").fetchone()
                if not heartbeat or heartbeat["updated"] < stamp - 60:
                    raise HTTPException(503, "生成服务正在准备，请稍后再试")
                asset = db.execute(
                    "SELECT * FROM assets WHERE id=? AND user_id=? AND created>?",
                    (asset_id, user["id"], stamp - 86400),
                ).fetchone()
                if not asset:
                    raise HTTPException(404, "照片不存在或已过期，请重新上传")
                if db.execute(
                    "SELECT 1 FROM jobs WHERE user_id=? AND status IN ('queued','running')",
                    (user["id"],),
                ).fetchone():
                    raise HTTPException(409, "已有任务正在生成，请稍候")
                if (
                    db.execute(
                        "SELECT COUNT(*) FROM jobs WHERE status IN ('queued','running')"
                    ).fetchone()[0]
                    >= 10
                ):
                    raise HTTPException(503, "服务繁忙，请稍后再试")
                if USER_LIMIT and (
                    db.execute(
                        "SELECT COUNT(*) FROM quotas WHERE user_id=? AND day=? AND status!='refunded'",
                        (user["id"], day()),
                    ).fetchone()[0]
                    >= USER_LIMIT
                ):
                    raise HTTPException(429, "今日次数已用完，明天再来试试")
                if GLOBAL_LIMIT and (
                    db.execute(
                        "SELECT COUNT(*) FROM quotas WHERE day=? AND status!='refunded'",
                        (day(),),
                    ).fetchone()[0]
                    >= GLOBAL_LIMIT
                ):
                    raise HTTPException(429, "今天服务额度已用完，请明天再试")
                admit_generation(db, user['id'], identifier, stamp)
                db.execute(
                    "INSERT INTO jobs(id,user_id,idempotency,asset_id,day,status,created,updated,algorithm) VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        identifier,
                        user["id"],
                        params.idempotency_key,
                        asset_id,
                        day(),
                        "queued",
                        stamp,
                        stamp,
                        "rotation-history-v4",
                    ),
                )
                db.execute(
                    "INSERT INTO quotas VALUES(?,?,?,?)",
                    (identifier, user["id"], day(), "reserved"),
                )
                if params.previous_job_id:
                    db.execute(
                        "INSERT INTO job_variations VALUES(?,?,?,?)",
                        (identifier, params.previous_job_id, json.dumps(sorted(excluded)), json.dumps(sorted(previous))),
                    )
            return {"job_id": identifier, "status": "queued"}
        finally:
            db.close()


def owned(db, identifier, user):
    row = db.execute(
        "SELECT * FROM jobs WHERE id=? AND user_id=?", (identifier, user["id"])
    ).fetchone()
    if not row:
        raise HTTPException(404, "任务不存在或已过期")
    return row


@router.get("/jobs")
def history(user=Depends(current_user)):
    db = connect()
    try:
        return [
            {
                "job_id": r["id"],
                "source_preview_url": f"/recommend/jobs/{r['id']}/source-preview",
                "status": r["status"],
                "created_at": r["created"],
                "count": db.execute(
                    "SELECT COUNT(*) FROM results WHERE job_id=?", (r["id"],)
                ).fetchone()[0],
            }
            for r in db.execute(
                "SELECT * FROM jobs WHERE user_id=? AND created>strftime('%s','now')-604800 ORDER BY created DESC LIMIT 100",
                (user["id"],),
            )
        ]
    finally:
        db.close()


@router.get("/jobs/{identifier}")
def status(identifier: str, user=Depends(current_user)):
    db = connect()
    try:
        r = owned(db, identifier, user)
        results = []
        for result in db.execute(
            "SELECT * FROM results WHERE job_id=? ORDER BY slot", (identifier,)
        ):
            version = db.execute(
                "SELECT metadata FROM template_versions WHERE template_id=? AND version=?",
                (result["template_id"], result["version"]),
            ).fetchone()
            metadata = json.loads(version["metadata"]) if version else {}
            results.append(
                {
                    "attribution": {
                        k: metadata.get(k, "")
                        for k in ["author", "license", "source_url", "license_url"]
                    },
                    "slot": result["slot"],
                    "template_id": result["template_id"],
                    "version": result["version"],
                    "key": result["key"],
                    "preview_url": f"/recommend/jobs/{identifier}/results/{result['slot']}?preview=true",
                    "image_url": f"/recommend/jobs/{identifier}/results/{result['slot']}",
                    "animated": Path(result["path"]).suffix.lower()==".gif",
                }
            )
        asset = db.execute(
            "SELECT created,path FROM assets WHERE id=? AND user_id=?",
            (r["asset_id"], user["id"]),
        ).fetchone()
        return {
            "job_id": identifier,
            "status": r["status"],
            "message": r["message"],
            "analysis": json.loads(r["analysis"]),
            "results": results,
            "selected_slots": json.loads(r["selection"]),
            "algorithm": r["algorithm"],
            "reroll_available": bool(asset and asset["created"] > time.time() - 86400 and Path(asset["path"]).is_file()),
        }
    finally:
        db.close()


@router.get("/jobs/{identifier}/results/{slot}")
def result(
    identifier: str, slot: int, preview: bool = False, user=Depends(current_user)
):
    db = connect()
    try:
        owned(db, identifier, user)
        row = db.execute(
            "SELECT * FROM results WHERE job_id=? AND slot=?", (identifier, slot)
        ).fetchone()
        if not row:
            raise HTTPException(404, "结果尚未生成")
        path = Path(row["preview"] if preview else row["path"])
        if not path.is_file():
            raise HTTPException(410, "结果已过期")
        return FileResponse(
            path,
            media_type="image/gif" if path.suffix.lower()==".gif" else "image/jpeg",
            headers={"Cache-Control": "private, no-store"},
        )
    finally:
        db.close()


class Selection(BaseModel):
    event_id: str = Field(min_length=8, max_length=100)
    slots: list[int] = Field(max_length=9)
    action: str = Field(default="choose", pattern=r"^(choose|download|exposure)$")


@router.post("/jobs/{identifier}/selections")
def select(identifier: str, params: Selection, user=Depends(current_user)):
    db = connect()
    try:
        with db:
            db.execute("BEGIN IMMEDIATE")
            owned(db, identifier, user)
            valid = {
                r["slot"]
                for r in db.execute(
                    "SELECT slot FROM results WHERE job_id=?", (identifier,)
                )
            }
            slots = sorted(set(params.slots))
            if not set(slots) <= valid:
                raise HTTPException(422, "只能选择已生成的图片")
            existing = db.execute(
                "SELECT * FROM events WHERE id=?", (params.event_id,)
            ).fetchone()
            if existing:
                if (
                    existing["user_id"] != user["id"]
                    or existing["job_id"] != identifier
                    or existing["type"] != params.action
                    or json.loads(existing["data"]) != slots
                ):
                    raise HTTPException(409, "反馈标识已被使用")
                return {"saved": True}
            preference = db.execute(
                "SELECT enabled FROM preferences WHERE user_id=?", (user["id"],)
            ).fetchone()
            if preference and not preference["enabled"]:
                return {"saved": True, "personalization": False}
            if (
                db.execute(
                    "SELECT COUNT(*) FROM events WHERE user_id=? AND created>?",
                    (user["id"], time.time() - 86400),
                ).fetchone()[0]
                >= 200
            ):
                raise HTTPException(429, "反馈操作较多，请稍后再试")
            db.execute(
                "INSERT INTO events VALUES(?,?,?,?,?,?)",
                (
                    params.event_id,
                    user["id"],
                    identifier,
                    params.action,
                    json.dumps(slots),
                    time.time(),
                ),
            )
            from .popularity import record
            for result in db.execute('SELECT slot,key FROM results WHERE job_id=?', (identifier,)).fetchall():
                if result['slot'] in slots:
                    record(result['key'], 'user:' + user['id'], 'ai_' + {'choose':'choose','download':'download','exposure':'exposure'}[params.action], dedup=f"{identifier}:{result['slot']}", db=db)
            if params.action == "choose":
                db.execute(
                    "UPDATE jobs SET selection=? WHERE id=?",
                    (json.dumps(slots), identifier),
                )
                descriptors = [
                    {
                        "slot": r["slot"],
                        "template_id": r["template_id"],
                        "version": r["version"],
                        "tags": json.loads(r["tags"]),
                    }
                    for r in db.execute(
                        "SELECT * FROM results WHERE job_id=?", (identifier,)
                    )
                ]
                db.execute(
                    "INSERT INTO feedback_history VALUES(?,?,?,?,?,?) ON CONFLICT(job_id) DO UPDATE SET selected=excluded.selected,results=excluded.results",
                    (
                        identifier,
                        user["id"],
                        owned(db, identifier, user)["created"],
                        json.dumps(slots),
                        json.dumps(descriptors),
                        owned(db, identifier, user)["algorithm"],
                    ),
                )

        return {"saved": True}
    finally:
        db.close()


class Preference(BaseModel):
    enabled: bool


@router.put("/preferences")
def preferences(params: Preference, user=Depends(current_user)):
    db = connect()
    try:
        with db:
            db.execute(
                "INSERT INTO preferences(user_id,enabled) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET enabled=excluded.enabled,weights=CASE WHEN excluded.enabled=0 THEN '{}' ELSE weights END",
                (user["id"], int(params.enabled)),
            )
            if not params.enabled:
                db.execute("DELETE FROM events WHERE user_id=?", (user["id"],))
                db.execute(
                    "DELETE FROM feedback_history WHERE user_id=?", (user["id"],)
                )
                db.execute(
                    "UPDATE jobs SET selection='[]' WHERE user_id=?", (user["id"],)
                )
        return {"enabled": params.enabled}
    finally:
        db.close()


@router.delete("/jobs/{identifier}", status_code=204)
def delete(identifier: str, user=Depends(current_user)):
    db = connect()
    paths = []
    try:
        with db:
            db.execute("BEGIN IMMEDIATE")
            r = owned(db, identifier, user)
            if r["status"] in ("queued", "running"):
                raise HTTPException(409, "请等待生成完成后删除")
            paths = [
                Path(v)
                for row in db.execute(
                    "SELECT path,preview FROM results WHERE job_id=?", (identifier,)
                )
                for v in row
            ]
            asset = db.execute(
                "SELECT * FROM assets WHERE id=?", (r["asset_id"],)
            ).fetchone()
            # Retain quota tombstones so deleting history cannot reset today's allowance.
            db.execute("DELETE FROM events WHERE job_id=?", (identifier,))
            db.execute("DELETE FROM feedback_history WHERE job_id=?", (identifier,))
            db.execute("DELETE FROM results WHERE job_id=?", (identifier,))
            db.execute("DELETE FROM job_variations WHERE job_id=?", (identifier,))
            db.execute("DELETE FROM jobs WHERE id=?", (identifier,))
            if (
                asset
                and not db.execute(
                    "SELECT 1 FROM jobs WHERE asset_id=?", (r["asset_id"],)
                ).fetchone()
            ):
                paths.extend(
                    [
                        Path(asset["path"]),
                        Path(asset["path"]).with_suffix(".subject.png"),
                        Path(asset["path"]).with_suffix(".analysis.json"),
                        root()/"history_thumbs"/(r["asset_id"]+".jpg"),
                    ]
                )
                db.execute("DELETE FROM assets WHERE id=?", (r["asset_id"],))
        for path in paths:
            path.unlink(missing_ok=True)
    finally:
        db.close()
    return Response(status_code=204)
