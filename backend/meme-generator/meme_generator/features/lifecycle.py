"""Owner initiated deletion, withdrawal and content reports; fail closed on work."""

import hashlib
import json
import shutil
import time
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from ..account import current_user, connection
from . import studio
from .store import connect, root
from .storage import exclusive, user_usage, collect_orphans, limit, MIB

router = APIRouter()


def ensure_idle(db, user_id, template_id=None):
    if template_id:
        active = db.execute(
            "SELECT payload FROM studio_jobs WHERE status IN ('queued','running')"
        )
        if any(template_id in r[0] for r in active):
            raise HTTPException(409, "模板正在被制作，请任务完成后再操作")
        if any(
            template_id in r[0]
            for r in db.execute(
                "SELECT selection FROM jobs WHERE status IN ('queued','running')"
            )
        ):
            raise HTTPException(409, "模板正在被制作，请稍后再操作")
    elif (
        db.execute(
            "SELECT 1 FROM studio_jobs WHERE user_id=? AND status IN ('queued','running')",
            (user_id,),
        ).fetchone()
        or db.execute(
            "SELECT 1 FROM jobs WHERE user_id=? AND status IN ('queued','running')",
            (user_id,),
        ).fetchone()
    ):
        raise HTTPException(409, "还有任务在制作，请完成后再注销")


def forget_public(db, identifier):
    row = db.execute("SELECT id FROM templates WHERE key=?", (identifier,)).fetchone()
    if row:
        db.execute("DELETE FROM template_versions WHERE template_id=?", (row["id"],))
        db.execute("DELETE FROM templates WHERE key=?", (identifier,))


def clear_private_caches():
    # A deletion must not leave previous photos in the foreground inference cache.
    import sys

    app = sys.modules.get("meme_generator.app")
    with studio.thumbnail_cache.lock:
        studio.thumbnail_cache.items.clear()
        studio.thumbnail_cache.bytes = 0
    for name in ("render_cache", "subject_cache"):
        cache = getattr(app, name, None)
        if cache:
            cache.items.clear()
            cache.bytes = 0


@router.get("/account/storage")
def storage_usage(user=Depends(current_user)):
    db = studio.init()
    try:
        used, templates = user_usage(user["id"], db)
        return {
            "used_bytes": used,
            "limit_bytes": limit("USER_STORAGE_BYTES", 256 * MIB),
            "templates": templates,
            "template_limit": limit("USER_TEMPLATE_LIMIT", 100),
        }
    finally:
        db.close()


@router.post("/studio/templates/{identifier}/withdraw")
def withdraw(identifier: str, user=Depends(current_user)):
    with exclusive():
        studio.own_template(identifier, user)
        db = studio.init()
        try:
            ensure_idle(db, user["id"], identifier)
            with db:
                forget_public(db, identifier)
                db.execute(
                    "UPDATE studio_templates SET status='private',message='已撤回，仅自己可见',updated=? WHERE id=?",
                    (time.time(), identifier),
                )
        finally:
            db.close()
        clear_private_caches()
        from .catalog import refresh

        refresh()
    return studio.template_view(studio.own_template(identifier, user))


@router.delete("/studio/templates/{identifier}", status_code=204)
def delete_template(identifier: str, user=Depends(current_user)):
    with exclusive():
        studio.own_template(identifier, user)
        db = studio.init()
        try:
            ensure_idle(db, user["id"], identifier)
            with db:
                forget_public(db, identifier)
                db.execute(
                    "DELETE FROM studio_templates WHERE id=? AND user_id=?",
                    (identifier, user["id"]),
                )
        finally:
            db.close()
        clear_private_caches()
        from .catalog import refresh

        refresh()
        collect_orphans()
    return Response(status_code=204)


@router.get("/studio/live/assets")
def list_videos(user=Depends(current_user)):
    from .livegif import directory

    videos = []
    for path in directory().glob("*.json"):
        try:
            meta = json.loads(path.read_text())
            if meta.get("user_id") == user["id"]:
                videos.append(
                    {
                        "id": path.stem,
                        "created_at": meta["created"],
                        "duration": meta.get("duration", 0),
                        "bytes": path.with_suffix(".media").stat().st_size,
                    }
                )
        except (ValueError, OSError, KeyError):
            continue
    return sorted(videos, key=lambda v: v["created_at"], reverse=True)


@router.delete("/studio/live/assets/{identifier}", status_code=204)
def delete_video(identifier: str, user=Depends(current_user)):
    from .livegif import directory, own

    with exclusive():
        own(identifier, user["id"])
        db = studio.init()
        try:
            if any(
                identifier in r[0]
                for r in db.execute(
                    "SELECT payload FROM studio_jobs WHERE status IN ('queued','running')"
                )
            ):
                raise HTTPException(409, "视频正在制作，完成后再删除")
        finally:
            db.close()
        for extension in (".json", ".jpg", ".media"):
            (directory() / (identifier + extension)).unlink(missing_ok=True)
    return Response(status_code=204)


class CaptionReview(BaseModel):
    texts: list[str] = Field(min_length=1, max_length=5)
    confirmed: bool = False
    rights_attested: bool = False
    preview_digest: str = Field(default="", max_length=64)


@router.patch("/studio/templates/{identifier}/captions")
def review_captions(identifier: str, params: CaptionReview, user=Depends(current_user)):
    from .storage import write_guard

    with write_guard(user["id"], 16384):
        row = studio.own_template(identifier, user)
        metadata = json.loads(row["metadata"])
        spec = json.loads(row["spec"])
        if not metadata.get("requires_review") or row["status"] == "published":
            raise HTTPException(409, "这个模板不是待校对的私有草稿")
        texts = [t.strip() for t in params.texts]
        if len(texts) != metadata["max_texts"] or any(
            not t or len(t) > 200 for t in texts
        ):
            raise HTTPException(422, "请按识别数量填写文字，每段 1～200 字")
        db = studio.init()
        try:
            ensure_idle(db, user["id"], identifier)
        finally:
            db.close()
        quality = metadata.setdefault("quality", {})
        if params.confirmed:
            if not params.rights_attested:
                raise HTTPException(422, "请确认拥有素材使用及公开的权利")
            if (
                not params.preview_digest
                or params.preview_digest != quality.get("preview_digest")
                or texts != spec.get("defaults")
            ):
                raise HTTPException(409, "文字已改变，请先保存并查看最新预览")
            metadata["requires_review"] = False
            quality["human_reviewed_at"] = time.time()
        else:
            spec["defaults"] = texts
            for layer in spec["layers"]:
                if layer["type"] == "text":
                    layer["value"] = texts[layer["slot"]]
            try:
                studio.render(spec, [], texts, preview=True)
            except (ValueError, OSError):
                raise HTTPException(422, "文字超出画布，请缩短后再预览")
            metadata["default_texts"] = texts
            quality["preview_digest"] = hashlib.sha256(
                json.dumps(spec, sort_keys=True).encode()
            ).hexdigest()
        stamp = time.time()
        db = studio.init()
        try:
            with db:
                db.execute(
                    "UPDATE studio_templates SET spec=?,metadata=?,updated=?,message=? WHERE id=?",
                    (
                        json.dumps(spec),
                        json.dumps(metadata, ensure_ascii=False),
                        stamp,
                        "已校对，仍需内容检查"
                        if params.confirmed
                        else "草稿已保存，请检查预览",
                        identifier,
                    ),
                )
        finally:
            db.close()
        publication = None
        if params.confirmed:
            try:
                publication = studio.enqueue(
                    "publish",
                    {"template_id": identifier},
                    identifier + str(stamp),
                    user,
                )
            except HTTPException:
                pass
            if publication:
                db = studio.init()
                with db:
                    db.execute(
                        "UPDATE studio_templates SET status='pending',message='等待内容检查' WHERE id=?",
                        (identifier,),
                    )
                db.close()
        result = studio.template_view(studio.own_template(identifier, user))
        if publication:
            result["publication_job"] = publication
        return result


class Deletion(BaseModel):
    confirmation: str = Field(pattern="^注销账号$")


@router.delete("/account", status_code=204)
def delete_account(params: Deletion, user=Depends(current_user)):
    uid = user["id"]
    with exclusive():
        db = studio.init()
        try:
            ensure_idle(db, uid)
            owned = [
                r[0]
                for r in db.execute(
                    "SELECT id FROM studio_templates WHERE user_id=?", (uid,)
                )
            ]
            for identifier in owned:
                ensure_idle(db, uid, identifier)
            studio_ids = [
                r[0]
                for r in db.execute(
                    "SELECT id FROM studio_jobs WHERE user_id=?", (uid,)
                )
            ]
            asset_ids = [
                r[0]
                for r in db.execute("SELECT id FROM assets WHERE user_id=?", (uid,))
            ]
            job_ids = [
                r[0] for r in db.execute("SELECT id FROM jobs WHERE user_id=?", (uid,))
            ]
            with db:
                db.execute(
                    "CREATE TABLE IF NOT EXISTS deleted_accounts(user_id TEXT PRIMARY KEY,created REAL NOT NULL)"
                )
                db.execute(
                    "INSERT OR REPLACE INTO deleted_accounts VALUES(?,?)",
                    (uid, time.time()),
                )
                db.execute('DELETE FROM template_trial_uses WHERE actor=?',(hashlib.sha256(('user:'+uid).encode()).hexdigest(),))
                for identifier in owned:
                    forget_public(db, identifier)
                for jid in job_ids:
                    for table in ("results", "job_variations", "cost_ledger"):
                        db.execute(f"DELETE FROM {table} WHERE job_id=?", (jid,))
                for table in (
                    "assets",
                    "jobs",
                    "quotas",
                    "feedback_history",
                    "events",
                    "preferences",
                    "studio_templates",
                    "studio_jobs",
                    "studio_ai_daily",
                    "studio_views",
                ):
                    db.execute(f"DELETE FROM {table} WHERE user_id=?", (uid,))
                db.execute(
                    "DELETE FROM popularity_seen WHERE actor=?", ("user:" + uid,)
                )
                tables = {
                    r[0]
                    for r in db.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
                for table in ("studio_ai_attempts", "content_reports"):
                    if table in tables:
                        db.execute(f"DELETE FROM {table} WHERE user_id=?", (uid,))
            for sid in studio_ids:
                (root() / "studio_results" / sid).unlink(missing_ok=True)
                (root() / "studio_replays" / (sid + ".json")).unlink(missing_ok=True)
            for aid in asset_ids:
                (root() / "history_thumbs" / (aid + ".jpg")).unlink(missing_ok=True)
            shutil.rmtree(root() / "private" / uid, ignore_errors=True)
            for video in list_videos(user):
                from .livegif import directory

                for ext in (".json", ".jpg", ".media"):
                    (directory() / (video["id"] + ext)).unlink(missing_ok=True)
        finally:
            db.close()
        accounts = connection()
        try:
            with accounts:
                for table in ("sessions", "favorites", "history"):
                    accounts.execute(f"DELETE FROM {table} WHERE user_id=?", (uid,))
                accounts.execute("DELETE FROM users WHERE id=?", (uid,))
        finally:
            accounts.close()
        collect_orphans()
        clear_private_caches()
        from .catalog import refresh

        refresh()
    return Response(status_code=204)


class Report(BaseModel):
    key: str = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=2, max_length=500)


@router.post("/templates/reports", status_code=201)
def report_content(params: Report, user=Depends(current_user)):
    if len(params.reason.strip()) < 2:
        raise HTTPException(422, "请填写具体问题")
    db = connect()
    try:
        db.execute(
            "CREATE TABLE IF NOT EXISTS content_reports(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,key TEXT NOT NULL,reason TEXT NOT NULL,created REAL NOT NULL,status TEXT NOT NULL)"
        )
        if (
            db.execute(
                "SELECT count(*) FROM content_reports WHERE user_id=? AND created>?",
                (user["id"], time.time() - 86400),
            ).fetchone()[0]
            >= 5
        ):
            raise HTTPException(429, "今天已提交较多举报，请等待处理")
        identifier = hashlib.sha256(
            (user["id"] + params.key + params.reason).encode()
        ).hexdigest()
        with db:
            db.execute(
                "INSERT OR IGNORE INTO content_reports VALUES(?,?,?,?,?,'pending')",
                (
                    identifier,
                    user["id"],
                    params.key,
                    params.reason.strip(),
                    time.time(),
                ),
            )
        return {
            "id": identifier,
            "status": "pending",
            "message": "已记录，等待维护者核查",
        }
    finally:
        db.close()


def resume_deletions():
    import logging
    import sqlite3

    db = connect()
    try:
        exists = db.execute(
            "SELECT 1 FROM sqlite_master WHERE name='deleted_accounts'"
        ).fetchone()
        rows = (
            [
                dict(r)
                for r in db.execute("SELECT user_id,created FROM deleted_accounts")
            ]
            if exists
            else []
        )
    finally:
        db.close()
    for row in rows:
        uid = row["user_id"]
        account_db = connection()
        try:
            present = account_db.execute(
                "SELECT 1 FROM users WHERE id=?", (uid,)
            ).fetchone()
        finally:
            account_db.close()
        if present:
            try:
                delete_account(Deletion(confirmation="注销账号"), {"id": uid})
            except (OSError, sqlite3.Error, HTTPException):
                logging.getLogger(__name__).warning(
                    "pending account cleanup will retry"
                )
                continue
        if row["created"] < time.time() - 31 * 86400:
            db = connect()
            try:
                with db:
                    db.execute("DELETE FROM deleted_accounts WHERE user_id=?", (uid,))
            finally:
                db.close()
