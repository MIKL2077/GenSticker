import json
import hashlib
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from pathlib import Path
from io import BytesIO
from PIL import Image
from .store import connect, root
from .catalog import bootstrap, refresh, rows
from .declarative import render, add_attribution
from .vision import warmup, process, PROCESSOR_VERSION
from ..manager import get_meme


def claim():
    db = connect()
    stamp = time.time()
    try:
        with db:
            db.execute("BEGIN IMMEDIATE")
            # Recover crashes using a persisted lease and bounded attempts.
            stale = list(
                db.execute(
                    "SELECT * FROM jobs WHERE status='running' AND lease<?", (stamp,)
                )
            )
            for job in stale:
                if job["attempts"] >= 2:
                    db.execute(
                        "UPDATE jobs SET status='failed',message='服务中断，次数已退回',updated=? WHERE id=?",
                        (stamp, job["id"]),
                    )
                    db.execute(
                        "UPDATE quotas SET status='refunded' WHERE job_id=?",
                        (job["id"],),
                    )
                else:
                    db.execute(
                        "UPDATE jobs SET status='queued' WHERE id=?", (job["id"],)
                    )
            row = db.execute(
                "SELECT * FROM jobs WHERE status='queued' ORDER BY created LIMIT 1"
            ).fetchone()
            if not row:
                return None
            db.execute(
                "UPDATE jobs SET status='running',attempts=attempts+1,lease=?,updated=?,message='正在提取主体并匹配模板' WHERE id=?",
                (stamp + 300, stamp, row["id"]),
            )
        return dict(row)
    finally:
        db.close()


def candidates(job, analysis):
    db = connect()
    try:
        preference = db.execute(
            "SELECT * FROM preferences WHERE user_id=?", (job["user_id"],)
        ).fetchone()
        weights = (
            json.loads(preference["weights"])
            if preference and preference["enabled"]
            else {}
        )
    finally:
        db.close()
    from .popularity import snapshot
    global_heat = snapshot()
    available = []
    # Conservative latency-safe templates from the existing catalog; ingestion extends this set.
    safe = {
        "always",
        "petpet",
        "my_friend",
        "look_flat",
        "look_this_icon",
        "think_what",
        "confuse",
        "little_angel",
        "support",
        "perfect",
        "like",
        "love_you",
        "hug_leg",
        "kiss",
        "rub",
        "why_at_me",
        "addiction",
    }
    for row in rows():
        m = json.loads(row["metadata"])
        # The early foreground-only sample can lose the original expression.
        # Keep manual compatibility, but exclude it from automatic matching.
        if m.get('conversion') == 'foreground-slot-v1':
            continue
        if not (m["min_images"] <= 1 <= m["max_images"]) or m.get("min_texts", 0) > len(
            m.get("default_texts", [])
        ):
            continue
        if not row["spec"] and row["key"] not in safe:
            continue
        if analysis.get("subject", "unknown") not in m.get(
            "subject_types", ["person", "animal", "object", "unknown"]
        ):
            continue
        tags = m["tags"]
        score = sum(weights.get(t, 0) for t in tags)
        score += min(.35, global_heat.get(row["key"], {}).get("heat", 0) / 300)
        score += (
            2 if analysis["expression"] in tags and analysis["confidence"] > 0.2 else 0
        )
        score += 0.25 / (1 + abs(analysis.get("aspect", 1) - m.get("slot_aspect", 1)))
        # Stable user-scoped jitter ensures variety without re-running analysis per image.
        score += (
            int(
                hashlib.sha256(
                    (job["user_id"] + row["key"] + job["day"]).encode()
                ).hexdigest()[:8],
                16,
            )
            / 0xFFFFFFFF
        )
        available.append((score, row))
    ordered = [r for _, r in sorted(available, key=lambda pair: pair[0], reverse=True)]
    chosen = []
    counts = {}

    def take(row):
        metadata = json.loads(row["metadata"])
        family = (
            "emoji-frame-v1"
            if metadata.get("conversion") == "emoji-frame-v1"
            else row["key"]
        )
        if counts.get(family, 0) >= 2:
            return False
        counts[family] = counts.get(family, 0) + 1
        chosen.append(row)
        return True

    for row in ordered:
        take(row)
        if len(chosen) == 6:
            break
    remaining = [r for r in ordered if r not in chosen]
    random.Random(job["id"]).shuffle(remaining)
    for row in remaining:
        take(row)
        if len(chosen) == 9:
            break
    return chosen


def run_job(job):
    db = connect()
    started_cpu = time.process_time()
    try:
        asset = db.execute(
            "SELECT * FROM assets WHERE id=?", (job["asset_id"],)
        ).fetchone()
        if not asset or not Path(asset["path"]).is_file():
            raise ValueError("asset unavailable")
        processed = Path(asset["path"]).with_suffix(".subject.png")
        analysis_file = Path(asset["path"]).with_suffix(".analysis.json")
        cached_analysis = (
            json.loads(analysis_file.read_text()) if analysis_file.is_file() else {}
        )
        if (
            processed.is_file()
            and cached_analysis.get("processor_version") == PROCESSOR_VERSION
        ):
            subject = Image.open(processed).convert("RGBA")
            analysis = cached_analysis
        else:
            subject, analysis = process(asset["path"])
            subject.save(processed, "PNG")
            analysis_file.write_text(json.dumps(analysis, ensure_ascii=False))
        buf = BytesIO()
        subject.save(buf, "PNG")
        raw = buf.getvalue()
        with db:
            db.execute(
                "UPDATE jobs SET analysis=? WHERE id=?",
                (json.dumps(analysis, ensure_ascii=False), job["id"]),
            )
        refresh()
        choices = candidates(job, analysis)
        directory = root() / "private" / job["user_id"] / job["id"]
        directory.mkdir(parents=True, exist_ok=True)
        # Reuse completed slots after crash recovery; no second quota reservation.
        done = {
            r["slot"]
            for r in db.execute("SELECT slot FROM results WHERE job_id=?", (job["id"],))
        }

        def render_one(slot, row):
            metadata = json.loads(row["metadata"])
            if row["spec"]:
                output = render(
                    json.loads(row["spec"]),
                    [subject],
                    metadata.get("default_texts", []),
                )
            else:
                output = get_meme(row["key"])(
                    images=[raw], texts=metadata.get("default_texts", [])
                )
            output = add_attribution(output, metadata)
            with Image.open(output) as original:
                frame = original.convert("RGB")
                frame.thumbnail((1024, 1024))
                path = directory / f"{slot}.jpg"
                frame.save(path, "JPEG", quality=88)
                frame.thumbnail((256, 256))
                preview = directory / f"{slot}-preview.jpg"
                frame.save(preview, "JPEG", quality=75)
            return slot, row, metadata, path, preview

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(render_one, slot, row)
                for slot, row in enumerate(choices)
                if slot not in done
            ]
            for future in as_completed(futures):
                try:
                    slot, row, metadata, path, preview = future.result()
                    with db:
                        from .popularity import record
                        record(row['key'], 'user:' + job['user_id'], 'ai_generate', dedup=f"{job['id']}:{slot}", db=db)
                        db.execute(
                            "INSERT OR REPLACE INTO results VALUES(?,?,?,?,?,?,?,?)",
                            (
                                job["id"],
                                slot,
                                row["id"],
                                row["version"],
                                row["key"],
                                json.dumps(metadata["tags"]),
                                str(path),
                                str(preview),
                            ),
                        )
                        db.execute(
                            "UPDATE jobs SET lease=?,updated=?,message=? WHERE id=?",
                            (
                                time.time() + 300,
                                time.time(),
                                f"已生成{len(done) + 1}张",
                                job["id"],
                            ),
                        )
                    with db:
                        db.execute(
                            "UPDATE worker_state SET updated=? WHERE id=1",
                            (time.time(),),
                        )
                    done.add(slot)
                except Exception:
                    continue
        count = db.execute(
            "SELECT COUNT(*) FROM results WHERE job_id=?", (job["id"],)
        ).fetchone()[0]
        if not count:
            raise ValueError("no valid results")
        message = (
            "九张表情已准备好" if count == 9 else f"已生成{count}张，部分模板暂时不可用"
        )
        with db:
            db.execute(
                "UPDATE jobs SET status='completed',updated=?,lease=0,message=? WHERE id=?",
                (time.time(), message, job["id"]),
            )
            db.execute(
                "UPDATE quotas SET status='consumed' WHERE job_id=?", (job["id"],)
            )
            db.execute(
                "INSERT OR REPLACE INTO cost_ledger VALUES(?,?,?,?,?)",
                (
                    job["id"],
                    "local-cpu",
                    0,
                    time.process_time() - started_cpu,
                    sum(p.stat().st_size for p in directory.glob("*.jpg")),
                ),
            )
    except Exception:
        with db:
            db.execute(
                "UPDATE jobs SET status='failed',updated=?,lease=0,message='生成失败，次数已退回，请重新上传' WHERE id=?",
                (time.time(), job["id"]),
            )
            db.execute(
                "UPDATE quotas SET status='refunded' WHERE job_id=?", (job["id"],)
            )
    finally:
        db.close()


def maintenance():
    db = connect()
    stamp = time.time()
    paths = []
    try:
        with db:
            from .popularity import maintenance as clean_popularity
            clean_popularity(db)
            for asset in list(
                db.execute("SELECT * FROM assets WHERE created<?", (stamp - 86400,))
            ):
                if not db.execute(
                    "SELECT 1 FROM jobs WHERE asset_id=? AND status IN ('queued','running')",
                    (asset["id"],),
                ).fetchone():
                    paths.extend(
                        [
                            Path(asset["path"]),
                            Path(asset["path"]).with_suffix(".subject.png"),
                            Path(asset["path"]).with_suffix(".analysis.json"),
                        ]
                    )
                    db.execute("DELETE FROM assets WHERE id=?", (asset["id"],))
            for job in list(
                db.execute("SELECT * FROM jobs WHERE created<?", (stamp - 7 * 86400,))
            ):
                if job["status"] in ("queued", "running"):
                    continue
                paths.extend(
                    Path(v)
                    for r in db.execute(
                        "SELECT path,preview FROM results WHERE job_id=?", (job["id"],)
                    )
                    for v in r
                )
                db.execute("DELETE FROM results WHERE job_id=?", (job["id"],))

                db.execute("DELETE FROM jobs WHERE id=?", (job["id"],))
            db.execute("DELETE FROM events WHERE created<?", (stamp - 90 * 86400,))
            db.execute(
                "DELETE FROM feedback_history WHERE created<?", (stamp - 90 * 86400,)
            )
            exposures = [0] * 9
            choices = [0] * 9
            for event in db.execute(
                "SELECT data FROM events WHERE type='exposure' AND created>?",
                (stamp - 90 * 86400,),
            ):
                for slot in json.loads(event["data"]):
                    if 0 <= slot < 9:
                        exposures[slot] += 1
            for snapshot in db.execute(
                "SELECT selected FROM feedback_history WHERE created>?",
                (stamp - 90 * 86400,),
            ):
                selected = json.loads(snapshot["selected"])
                if len(selected) >= 9:
                    continue
                for slot in selected:
                    if 0 <= slot < 9:
                        choices[slot] += 1
            rates = [(choices[i] + 1) / (exposures[i] + 4) for i in range(9)]
            mean = sum(rates) / 9
            correction = [max(0.5, min(2, mean / r)) for r in rates]
            users = {
                r["user_id"]
                for r in db.execute(
                    "SELECT DISTINCT user_id FROM feedback_history WHERE selected!='[]'"
                )
            }
            for user in users:
                old = db.execute(
                    "SELECT * FROM preferences WHERE user_id=?", (user,)
                ).fetchone()
                if old and not old["enabled"]:
                    continue
                weights = {}
                for job in db.execute(
                    "SELECT * FROM feedback_history WHERE user_id=? AND selected!='[]' AND created>?",
                    (user, stamp - 90 * 86400),
                ):
                    selection = json.loads(job["selected"])
                    results = json.loads(job["results"])
                    if len(selection) == len(results):
                        continue
                    decay = 0.5 ** ((stamp - job["created"]) / (30 * 86400))
                    for result in results:
                        if result["slot"] in selection:
                            for tag in result["tags"]:
                                weights[tag] = weights.get(tag, 0) + correction[
                                    result["slot"]
                                ] * decay / max(1, len(selection))
                weights = {k: min(2, v / 5) for k, v in weights.items()}
                db.execute(
                    "INSERT INTO preferences(user_id,weights,updated) VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET weights=excluded.weights,updated=excluded.updated",
                    (user, json.dumps(weights), stamp),
                )
        for path in paths:
            path.unlink(missing_ok=True)
    finally:
        db.close()


def main():
    bootstrap()
    refresh()
    try:
        model_ready = warmup()
    except Exception:
        model_ready = False
        print(
            "Local segmentation unavailable; original-image fallback enabled",
            flush=True,
        )
    last = 0
    while True:
        if time.time() - last > 3600:
            maintenance()
            last = time.time()
        db = connect()
        with db:
            db.execute(
                "INSERT OR REPLACE INTO worker_state VALUES(1,?,?)",
                (time.time(), int(model_ready)),
            )
        db.close()
        job = claim()
        if job:
            run_job(job)
        else:
            time.sleep(1)


if __name__ == "__main__":
    main()
