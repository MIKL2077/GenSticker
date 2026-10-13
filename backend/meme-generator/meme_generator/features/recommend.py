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
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from ..account import current_user
from .store import connect, root

router = APIRouter(prefix="/recommend")
normalization_slots = asyncio.Semaphore(2)
USER_LIMIT = int(os.getenv("GENSTICKER_DAILY_LIMIT", "3"))
GLOBAL_LIMIT = int(os.getenv("GENSTICKER_GLOBAL_LIMIT", "100"))


def day():
    return datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()


def normalize(raw):
    if len(raw) > 3 * 1024 * 1024:
        raise HTTPException(413, "照片不能超过3MB，请压缩后上传")
    try:
        with Image.open(BytesIO(raw)) as original:
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
async def upload(file: UploadFile = File(...), user=Depends(current_user)):
    raw = await file.read(3 * 1024 * 1024 + 1)
    if normalization_slots.locked():
        raise HTTPException(503, "照片处理繁忙，请稍后重试，未扣除次数")
    async with normalization_slots:
        normalized = await asyncio.to_thread(normalize, raw)
    identifier = uuid.uuid4().hex
    db = connect()
    try:
        if (
            db.execute(
                "SELECT COUNT(*) FROM assets WHERE user_id=? AND created>?",
                (user["id"], time.time() - 86400),
            ).fetchone()[0]
            >= 12
        ):
            raise HTTPException(429, "今天上传的照片较多，请明天再试")
        digest = hashlib.sha256(normalized).hexdigest()
        duplicate = db.execute(
            "SELECT * FROM assets WHERE user_id=? AND hash=? AND created>?",
            (user["id"], digest, time.time() - 86400),
        ).fetchone()
        if duplicate and Path(duplicate["path"]).is_file():
            return {
                "asset_id": duplicate["id"],
                "expires_at": duplicate["created"] + 86400,
            }
        directory = root() / "private" / user["id"]
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = directory / (identifier + ".png")
        path.write_bytes(normalized)
        with db:
            db.execute(
                "INSERT INTO assets VALUES(?,?,?,?,?)",
                (identifier, user["id"], digest, time.time(), str(path)),
            )
    finally:
        db.close()
    return {"asset_id": identifier, "expires_at": time.time() + 86400}


@router.get("/quota")
def quota(user=Depends(current_user)):
    db = connect()
    try:
        used = db.execute(
            "SELECT COUNT(*) FROM quotas WHERE user_id=? AND day=? AND status!='refunded'",
            (user["id"], day()),
        ).fetchone()[0]
        enabled = db.execute(
            "SELECT enabled FROM preferences WHERE user_id=?", (user["id"],)
        ).fetchone()
        return {
            "limit": USER_LIMIT,
            "remaining": max(0, USER_LIMIT - used),
            "day": day(),
            "personalization": bool(enabled["enabled"]) if enabled else True,
            "paid_ai_enabled": False,
        }
    finally:
        db.close()


class CreateJob(BaseModel):
    asset_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    idempotency_key: str = Field(min_length=8, max_length=100)


@router.post("/jobs", status_code=202)
def create(params: CreateJob, user=Depends(current_user)):
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
                if old["asset_id"] != params.asset_id:
                    raise HTTPException(409, "重试标识与照片不一致")
                return {"job_id": old["id"], "status": old["status"]}
            heartbeat = db.execute("SELECT * FROM worker_state WHERE id=1").fetchone()
            if not heartbeat or heartbeat["updated"] < stamp - 60:
                raise HTTPException(503, "生成服务正在准备，请稍后再试，未扣除次数")
            asset = db.execute(
                "SELECT * FROM assets WHERE id=? AND user_id=? AND created>?",
                (params.asset_id, user["id"], stamp - 86400),
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
                raise HTTPException(503, "服务繁忙，请稍后再试，未扣除次数")
            if (
                db.execute(
                    "SELECT COUNT(*) FROM quotas WHERE user_id=? AND day=? AND status!='refunded'",
                    (user["id"], day()),
                ).fetchone()[0]
                >= USER_LIMIT
            ):
                raise HTTPException(429, "今日次数已用完，明天再来试试")
            if (
                db.execute(
                    "SELECT COUNT(*) FROM quotas WHERE day=? AND status!='refunded'",
                    (day(),),
                ).fetchone()[0]
                >= GLOBAL_LIMIT
            ):
                raise HTTPException(429, "今天服务额度已用完，请明天再试")
            db.execute(
                "INSERT INTO jobs(id,user_id,idempotency,asset_id,day,status,created,updated) VALUES(?,?,?,?,?,?,?,?)",
                (
                    identifier,
                    user["id"],
                    params.idempotency_key,
                    params.asset_id,
                    day(),
                    "queued",
                    stamp,
                    stamp,
                ),
            )
            db.execute(
                "INSERT INTO quotas VALUES(?,?,?,?)",
                (identifier, user["id"], day(), "reserved"),
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
                "status": r["status"],
                "created_at": r["created"],
                "count": db.execute(
                    "SELECT COUNT(*) FROM results WHERE job_id=?", (r["id"],)
                ).fetchone()[0],
            }
            for r in db.execute(
                "SELECT * FROM jobs WHERE user_id=? ORDER BY created DESC LIMIT 20",
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
                }
            )
        return {
            "job_id": identifier,
            "status": r["status"],
            "message": r["message"],
            "analysis": json.loads(r["analysis"]),
            "results": results,
            "selected_slots": json.loads(r["selection"]),
            "algorithm": r["algorithm"],
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
            media_type="image/jpeg",
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
                if params.action == "choose":
                    db.execute(
                        "UPDATE jobs SET selection=? WHERE id=?",
                        (json.dumps(slots), identifier),
                    )
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
            if params.action == "choose":
                db.execute(
                    "UPDATE jobs SET selection=? WHERE id=?",
                    (json.dumps(slots), identifier),
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
            db.execute("DELETE FROM results WHERE job_id=?", (identifier,))
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
                    ]
                )
                db.execute("DELETE FROM assets WHERE id=?", (r["asset_id"],))
        for path in paths:
            path.unlink(missing_ok=True)
    finally:
        db.close()
    return Response(status_code=204)
