"""Application egress budget, separate from the provider's authoritative bill."""

import os
import asyncio
import sqlite3
from datetime import datetime, timedelta, timezone
from starlette.responses import JSONResponse
from .store import root


def period():
    now = datetime.now(timezone(timedelta(hours=8)))
    start = min(28, max(1, int(os.getenv("GENSTICKER_BILLING_DAY", "1"))))
    if now.day < start:
        now = now.replace(day=1) - timedelta(days=1)
    return now.strftime("%Y-%m") + f"-{start:02d}"


def record_bytes(count):
    db = sqlite3.connect(root() / "traffic.sqlite3", timeout=3)
    try:
        with db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS traffic(period TEXT PRIMARY KEY,bytes INTEGER NOT NULL)"
            )
            db.execute(
                "INSERT INTO traffic VALUES(?,?) ON CONFLICT(period) DO UPDATE SET bytes=bytes+excluded.bytes",
                (period(), count),
            )
    finally:
        db.close()


def usage():
    path = root() / "traffic.sqlite3"
    if not path.exists():
        return 0
    db = sqlite3.connect(path, timeout=3)
    try:
        if not db.execute(
            "SELECT 1 FROM sqlite_master WHERE name='traffic'"
        ).fetchone():
            return 0
        row = db.execute(
            "SELECT bytes FROM traffic WHERE period=?", (period(),)
        ).fetchone()
        return row[0] if row else 0
    finally:
        db.close()


def budget():
    return max(1, int(os.getenv("GENSTICKER_API_MONTHLY_BYTES", "900000000000")))


def exhausted():
    # Reserve the last 15% for existing work and completed-result downloads.
    return usage() >= budget() * 0.85


def new_work(method, path):
    return method == "POST" and (
        (path.startswith('/recommend/jobs/') and path.endswith('/collage'))
        or
        path
        in {
            "/studio/jobs",
            "/studio/templates",
            "/studio/templates/ai",
            "/studio/live/jobs",
            "/studio/live/assets",
            "/studio/live/results",
            "/recommend/jobs",
            "/recommend/assets",
            "/recommend/subjects/detect",
            "/images/subject",
            "/images/subject-file",
            "/images/wechat-export",
        }
        or path.startswith("/studio/jobs/")
        and path.endswith("/regenerate")
        or path.startswith("/memes/")
        and (path.endswith("/generate") or path.endswith("/"))
    )


class TrafficBudget:
    def __init__(self, app):
        self.app = app
        self.slots = asyncio.Semaphore(2)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        used = usage()
        essential = (
            scope["path"]
            in {
                "/healthz",
                "/account/config",
                "/auth/wechat",
                "/auth/me",
                "/account/storage",
            }
            or scope["method"] == "DELETE"
        )
        if used >= budget() and not essential:
            return await JSONResponse(
                {
                    "detail": "本账期下载流量预算已达上限，暂缓领取；账号登录与数据删除仍可使用"
                },
                status_code=503,
            )(scope, receive, send)
        if new_work(scope["method"], scope["path"]) and used >= budget() * 0.85:
            return await JSONResponse(
                {
                    "detail": "接近本账期流量预算，暂缓新生成，已有作品仍可在预留预算内领取"
                },
                status_code=503,
            )(scope, receive, send)
        heavy = new_work(scope["method"], scope["path"]) or (
            scope["method"] == "GET"
            and scope["path"].startswith("/memes/")
            and scope["path"].endswith("/preview")
        )
        if heavy and self.slots.locked():
            return await JSONResponse(
                {"detail": "素材处理繁忙，请稍后再试"},
                status_code=503,
                headers={"Retry-After": "3"},
            )(scope, receive, send)
        if heavy:
            await self.slots.acquire()
        count = 0

        async def meter(message):
            nonlocal count
            if message["type"] == "http.response.body":
                count += len(message.get("body", b""))
            await send(message)

        try:
            await self.app(scope, receive, meter)
        finally:
            if heavy:
                self.slots.release()
            if count:
                # Keep metering failure from corrupting an already-streamed result.
                try:
                    record_bytes(count)
                except (OSError, sqlite3.Error):
                    import logging

                    logging.getLogger(__name__).error(
                        "traffic accounting unavailable; inspect private state"
                    )
