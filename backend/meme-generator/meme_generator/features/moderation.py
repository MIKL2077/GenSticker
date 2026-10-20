"""Local operator CLI; never expose these controls through an unauthenticated API."""

import argparse
import json
import time
from .store import connect
from .storage import exclusive


def withdraw(key, reason):
    from .lifecycle import ensure_idle, clear_private_caches
    from .studio import init

    with exclusive():
        db = init()
        try:
            ensure_idle(db, "operator", key)
            with db:
                db.execute(
                    "INSERT OR REPLACE INTO template_blocks VALUES(?,?,?)",
                    (key, reason, time.time()),
                )
                db.execute(
                    "UPDATE templates SET status='withdrawn' WHERE key=?", (key,)
                )
                db.execute(
                    "UPDATE studio_templates SET status='rejected',message='维护者已下架，请检查素材使用权和内容',updated=? WHERE id=?",
                    (time.time(), key),
                )
                exists = db.execute(
                    "SELECT 1 FROM sqlite_master WHERE name='content_reports'"
                ).fetchone()
                if exists:
                    db.execute(
                        "UPDATE content_reports SET status='resolved' WHERE key=?",
                        (key,),
                    )
        finally:
            db.close()
        from .catalog import refresh

        refresh()
        clear_private_caches()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    w = sub.add_parser("withdraw")
    w.add_argument("--key", required=True)
    w.add_argument("--reason", required=True)
    args = p.parse_args()
    if args.command == "withdraw":
        if len(args.reason.strip()) < 2:
            raise SystemExit("provide a specific reason")
        withdraw(args.key, args.reason)
        print("withdrawn")
        return
    db = connect()
    try:
        exists = db.execute(
            "SELECT 1 FROM sqlite_master WHERE name='content_reports'"
        ).fetchone()
        rows = (
            [
                dict(r)
                for r in db.execute(
                    "SELECT id,key,reason,created,status FROM content_reports WHERE status='pending' ORDER BY created LIMIT 100"
                )
            ]
            if exists
            else []
        )
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    finally:
        db.close()


if __name__ == "__main__":
    main()


class AvailabilityGuard:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            parts = scope["path"].strip("/").split("/")
            if len(parts) >= 3 and parts[0] == "memes":
                key = parts[1]
                db = connect()
                try:
                    blocked = db.execute(
                        "SELECT 1 FROM template_blocks WHERE key=?", (key,)
                    ).fetchone()
                    withdrawn = (
                        key.startswith("user_")
                        and not db.execute(
                            "SELECT 1 FROM templates WHERE key=? AND status='published'",
                            (key,),
                        ).fetchone()
                    )
                finally:
                    db.close()
                if blocked or withdrawn:
                    from starlette.responses import JSONResponse

                    return await JSONResponse(
                        {"detail": "模板已撤回或下架"},
                        status_code=404,
                        headers={"Cache-Control": "no-store"},
                    )(scope, receive, send)
        return await self.app(scope, receive, send)
