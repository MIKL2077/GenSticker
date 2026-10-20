"""Shared-process storage admission. All writers use one reentrant file lock.

Measure legacy files as well as new ones: a deployment cannot reset quotas by
starting a fresh ledger. Daily ingress survives deletion. Limits are configurable.
"""

import fcntl
import hashlib
import json
import os
import shutil
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from fastapi import HTTPException
from .store import connect, root

_local = threading.local()
_threads = threading.RLock()
MIB = 1024 * 1024


def limit(name, default):
    return max(1, int(os.getenv("GENSTICKER_" + name, str(default))))


@contextmanager
def exclusive():
    with _threads:
        if getattr(_local, "depth", 0):
            yield
            return
        with (root() / "storage.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            _local.depth = 1
            try:
                yield
            finally:
                _local.depth = 0
                fcntl.flock(lock, fcntl.LOCK_UN)


def size(path):
    try:
        if path.is_symlink():
            return 0
        return path.stat().st_size if path.is_file() else 0
    except OSError:
        return 0


def asset_refs(spec):
    spec = json.loads(spec) if isinstance(spec, str) else spec
    refs = {l["value"] for l in spec.get("layers", []) if l.get("type") == "asset"}
    if spec.get("reference_asset"):
        refs.add(spec["reference_asset"])
    return {r for r in refs if len(r) == 64 and all(c in "0123456789abcdef" for c in r)}


def user_usage(user_id, db):
    paths = set()
    extra = 0
    for p in (root() / "private" / user_id).rglob("*"):
        paths.add(p)
    for row in db.execute("SELECT id,path FROM assets WHERE user_id=?", (user_id,)):
        paths.add(Path(row["path"]))
        paths.add(root() / "history_thumbs" / (row["id"] + ".jpg"))
    for meta in (root() / "live_sources").glob("*.json"):
        try:
            if json.loads(meta.read_text()).get("user_id") == user_id:
                paths.update(
                    meta.with_suffix(ext) for ext in (".json", ".jpg", ".media")
                )
        except (OSError, ValueError):
            continue
    tables = {
        r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    count = 0
    if "studio_jobs" in tables:
        for row in db.execute(
            "SELECT id,payload FROM studio_jobs WHERE user_id=?", (user_id,)
        ):
            extra += len(row["payload"].encode())
            paths.add(root() / "studio_results" / row["id"])
            paths.add(root() / "studio_replays" / (row["id"] + ".json"))
    if "studio_templates" in tables:
        for row in db.execute(
            "SELECT spec,metadata FROM studio_templates WHERE user_id=?", (user_id,)
        ):
            count += 1
            extra += len(row["spec"].encode()) + len(row["metadata"].encode())
            paths.update(
                root() / "template_assets" / (ref + ".png")
                for ref in asset_refs(row["spec"])
            )
    return extra + sum(size(p) for p in paths), count


def state_bytes():
    return sum(size(p) for p in root().rglob("*"))


@contextmanager
def write_guard(
    user_id,
    incoming=0,
    *,
    ingress=0,
    template=False,
    media=False,
    photo=False,
    job=False,
):
    with exclusive():
        db = connect()
        try:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS storage_ingress(user_id TEXT NOT NULL,day TEXT NOT NULL,bytes INTEGER NOT NULL,PRIMARY KEY(user_id,day));
            CREATE TABLE IF NOT EXISTS deleted_accounts(user_id TEXT PRIMARY KEY,created REAL NOT NULL);
            """)
            if db.execute(
                "SELECT 1 FROM deleted_accounts WHERE user_id=?", (user_id,)
            ).fetchone():
                raise HTTPException(401, "账号已注销，请重新登录")
            tables = {
                r[0]
                for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            if job:
                count_jobs = db.execute(
                    "SELECT count(*) FROM jobs WHERE user_id=?", (user_id,)
                ).fetchone()[0]
                if "studio_jobs" in tables:
                    count_jobs += db.execute(
                        "SELECT count(*) FROM studio_jobs WHERE user_id=?", (user_id,)
                    ).fetchone()[0]
                if count_jobs >= limit("USER_JOB_LIMIT", 200):
                    raise HTTPException(
                        409, "最多保留 200 个任务，请在生成队列和历史中删除一些后再制作"
                    )
            if photo and db.execute(
                "SELECT count(*) FROM assets WHERE user_id=?", (user_id,)
            ).fetchone()[0] >= limit("USER_PHOTO_LIMIT", 100):
                raise HTTPException(
                    409, "照片素材较多，请等待过期清理，或复用已有照片换一批"
                )
            if media:
                count_media = 0
                for path in (root() / "live_sources").glob("*.json"):
                    try:
                        count_media += (
                            json.loads(path.read_text()).get("user_id") == user_id
                        )
                    except (ValueError, OSError):
                        continue
                if count_media >= limit("USER_MEDIA_LIMIT", 100):
                    raise HTTPException(
                        409, "最多保留 100 份视频或 GIF 素材，请在管理素材中先删除一些"
                    )
            used, count = user_usage(user_id, db)
            if used + incoming > limit("USER_STORAGE_BYTES", 256 * MIB):
                raise HTTPException(413, "你的小窝空间不足，请先删除旧视频、任务或模板")
            if template and count >= limit("USER_TEMPLATE_LIMIT", 100):
                raise HTTPException(409, "最多保留 100 个自制模板，请先删除一些")
            if shutil.disk_usage(root()).free - incoming < limit(
                "MIN_FREE_BYTES", 10 * 1024**3
            ) or state_bytes() + incoming > limit("STATE_MAX_BYTES", 12 * 1024**3):
                raise HTTPException(
                    507, "存储空间正在整理，暂不接收新素材，已有作品仍可领取"
                )
            day = time.strftime("%Y-%m-%d", time.gmtime(time.time() + 8 * 3600))
            from ..account import connection

            accounts = connection()
            try:
                identity = accounts.execute(
                    "SELECT openid FROM users WHERE id=?", (user_id,)
                ).fetchone()
            finally:
                accounts.close()
            budget_id = (
                "openid:" + hashlib.sha256(identity[0].encode()).hexdigest()
                if identity
                else user_id
            )
            old = db.execute(
                "SELECT bytes FROM storage_ingress WHERE user_id=? AND day=?",
                (budget_id, day),
            ).fetchone()
            if ingress and (old[0] if old else 0) + ingress > limit(
                "DAILY_UPLOAD_BYTES", 300 * MIB
            ):
                raise HTTPException(
                    429, "今天上传的素材较多，明天再来，已有作品仍可领取"
                )
        finally:
            db.close()
        if ingress:
            db = connect()
            try:
                with db:
                    db.execute(
                        "INSERT INTO storage_ingress VALUES(?,?,?) ON CONFLICT(user_id,day) DO UPDATE SET bytes=bytes+excluded.bytes",
                        (budget_id, day, ingress),
                    )
                    db.execute(
                        "DELETE FROM storage_ingress WHERE day<date('now','-31 days')"
                    )
            finally:
                db.close()
        yield


def write_bytes(path, raw, user_id):
    with write_guard(user_id, len(raw)):
        path.write_bytes(raw)


def collect_orphans(min_age=86400):
    """Only remove old, unreferenced template artwork, including all versions."""
    with exclusive():
        db = connect()
        try:
            tables = {
                r[0]
                for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            refs = set()
            for table in ("templates", "template_versions", "studio_templates"):
                if table in tables:
                    for row in db.execute(
                        f"SELECT spec FROM {table} WHERE spec IS NOT NULL"
                    ):
                        refs.update(asset_refs(row[0]))
        finally:
            db.close()
        removed = 0
        for path in (root() / "template_assets").glob("*.png"):
            if path.stem not in refs and path.stat().st_mtime < time.time() - min_age:
                path.unlink()
                removed += 1
        return removed
