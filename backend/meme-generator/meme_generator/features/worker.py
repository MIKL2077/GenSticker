from meme_generator.safe_images import open_image
import json
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from pathlib import Path
from io import BytesIO
from PIL import Image
from .store import connect, root
from .catalog import bootstrap, refresh, rows
from .declarative import render
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
                        "UPDATE jobs SET status='failed',message='服务中断，可以再换一批重试',updated=? WHERE id=?",
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
        variation = db.execute("SELECT * FROM job_variations WHERE job_id=?", (job["id"],)).fetchone()
        excluded = set(json.loads(variation["excluded_keys"])) if variation else set()
        previous = set(json.loads(variation["previous_keys"])) if variation else set()
        # All entry points share exposure history, including starting again without a parent.
        usage = {r['key']: (r['uses'], r['last_seen']) for r in db.execute(
            "SELECT r.key,COUNT(*) AS uses,MAX(j.created) AS last_seen FROM results r JOIN jobs j ON j.id=r.job_id WHERE j.user_id=? AND j.id!=? AND j.created>? GROUP BY r.key",
            (job['user_id'], job['id'], time.time()-7*86400))}
        latest = db.execute("SELECT id FROM jobs WHERE user_id=? AND id!=? AND status='completed' ORDER BY created DESC LIMIT 1", (job['user_id'],job['id'])).fetchone()
        if latest:
            previous.update(r['key'] for r in db.execute('SELECT key FROM results WHERE job_id=?',(latest['id'],)))
    finally:
        db.close()
    from .popularity import snapshot
    global_heat = snapshot()
    available = []
    from .recommendation import exclusion_reason
    for row in rows():
        m = json.loads(row["metadata"])
        if exclusion_reason(row, analysis.get('subject', 'unknown')) is not None:
            continue
        tags = m["tags"]
        score = sum(weights.get(t, 0) for t in tags)
        score += min(.35, global_heat.get(row["key"], {}).get("heat", 0) / 300)
        score += (
            2 if analysis["expression"] in tags and analysis["confidence"] > 0.2 else 0
        )
        score += 0.25 / (1 + abs(analysis.get("aspect", 1) - m.get("slot_aspect", 1)))
        # Seed by job: crash recovery keeps the same order, new batches get new variety.
        score += (
            int(
                hashlib.sha256(
                    (job["id"] + row["key"]).encode()
                ).hexdigest()[:8],
                16,
            )
            / 0xFFFFFFFF
        )
        available.append((score, row))
    # Fresh templates first; when a cycle is nearly exhausted, fill from the
    # least recently used templates instead of returning six images. The last
    # batch stays excluded whenever the catalog can supply nine alternatives.
    ordered = [r for _, r in sorted(available, key=lambda pair: (
        pair[1]['key'] in previous,
        pair[1]['key'] in excluded or pair[1]['key'] in usage,
        usage.get(pair[1]['key'], (0, 0)),
        -pair[0],
    ))]
    return ordered



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
            subject = open_image(processed).convert("RGBA")
            analysis = cached_analysis
        else:
            subject, analysis = process(asset["path"],subject_selected=True) if Path(asset["path"]).stem.endswith(".selected") else process(asset["path"])
            from .storage import write_bytes
            prepared=BytesIO();subject.save(prepared,"PNG")
            write_bytes(processed,prepared.getvalue(),job["user_id"])
            write_bytes(analysis_file,json.dumps(analysis,ensure_ascii=False).encode(),job["user_id"])
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
            from .animation import save_result_files
            path,preview=save_result_files(output,directory,slot,job["user_id"])
            return slot, row, metadata, path, preview

        used = {r['key'] for r in db.execute('SELECT key FROM results WHERE job_id=?', (job['id'],))}
        remaining = iter(r for r in choices if r['key'] not in used)
        with ThreadPoolExecutor(max_workers=2) as executor:
            while len(done) < 9:
                batch = []
                for slot in (i for i in range(9) if i not in done):
                    row = next(remaining, None)
                    if row is None: break
                    batch.append(executor.submit(render_one, slot, row))
                    if len(batch) == 2: break
                if not batch: break
                for future in as_completed(batch):
                    try:
                        slot, row, metadata, path, preview = future.result()
                    except Exception:
                        # Broken templates don't shrink a batch while alternatives remain.
                        continue
                    with db:
                        from .popularity import record
                        record(row['key'], 'user:' + job['user_id'], 'ai_generate', dedup=f"{job['id']}:{slot}", db=db)
                        db.execute('INSERT OR REPLACE INTO results VALUES(?,?,?,?,?,?,?,?)',
                            (job['id'], slot, row['id'], row['version'], row['key'], json.dumps(metadata['tags']), str(path), str(preview)))
                        done.add(slot)
                        stamp = time.time()
                        db.execute('UPDATE jobs SET lease=?,updated=?,message=? WHERE id=?',
                            (stamp+300, stamp, f'已生成{len(done)}张', job['id']))
                        db.execute('UPDATE worker_state SET updated=? WHERE id=1', (stamp,))
        count = db.execute(
            "SELECT COUNT(*) FROM results WHERE job_id=?", (job["id"],)
        ).fetchone()[0]
        if not count:
            raise ValueError("no valid results" if choices else "templates exhausted")
        message = (
            "九张表情已准备好" if count == 9 else f"已生成{count}张，按本次可用模板展示"
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
    except Exception as error:
        with db:
            db.execute(
                "UPDATE jobs SET status='failed',updated=?,lease=0,message=? WHERE id=?",
                (time.time(), "这张照片的可用模板已经试完啦，换张照片再玩吧" if str(error) == "templates exhausted" else "这次生成没成功，可以重试或换张照片", job["id"]),
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
                db.execute("DELETE FROM job_variations WHERE job_id=?", (job["id"],))

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
        thumbs=root()/'history_thumbs'
        if thumbs.exists():
            active_assets={r['asset_id'] for r in db.execute('SELECT DISTINCT asset_id FROM jobs')}
            for thumbnail in thumbs.glob('*.jpg'):
                if thumbnail.stem not in active_assets:paths.append(thumbnail)
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
            from .studio import cleanup
            cleanup()
            last = time.time()
        db = connect()
        with db:
            db.execute(
                "INSERT OR REPLACE INTO worker_state VALUES(1,?,?)",
                (time.time(), int(model_ready)),
            )
        db.close()
        from .studio import work_one
        work_one()
        job = claim()
        if job:
            run_job(job)
        else:
            time.sleep(1)


if __name__ == "__main__":
    main()
