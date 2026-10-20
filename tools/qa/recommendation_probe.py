"""Limited real-worker regression with synthetic data; never a load test."""

import argparse
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import secrets
import shutil
import time
import uuid

import httpx
from PIL import Image, ImageDraw
from meme_generator import account
from meme_generator.features.lifecycle import Deletion, delete_account

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--allow-fixtures", action="store_true")
p.add_argument("--output", required=True)
a = p.parse_args()
if not a.allow_fixtures:
    raise SystemExit("Explicit fixture authorization required")
if (
    os.getloadavg()[0] > 3.5
    or shutil.disk_usage("/var/lib/gensticker").free < 10 * 1024**3
):
    raise SystemExit("Shared host resource guard")
user = "pool_qa_" + uuid.uuid4().hex
token = secrets.token_urlsafe(32)
db = account.connection()
with db:
    db.execute(
        "INSERT INTO users(id,openid,name) VALUES(?,?,?)",
        (user, user, "Synthetic pool QA"),
    )
    db.execute(
        "INSERT INTO sessions VALUES(?,?,?)",
        (hashlib.sha256(token.encode()).hexdigest(), user, int(time.time()) + 1800),
    )
db.close()
report = {
    "status": "running",
    "scope": "four sequential batches, synthetic selected subject, real API and worker",
    "batches": [],
}
try:
    photo = Image.new("RGBA", (256, 256))
    draw = ImageDraw.Draw(photo)
    draw.ellipse((32, 12, 224, 244), fill="#eac392")
    draw.ellipse((80, 80, 100, 110), fill="black")
    draw.ellipse((156, 80, 176, 110), fill="black")
    raw = BytesIO()
    photo.save(raw, "PNG")
    with httpx.Client(
        base_url="http://127.0.0.1:3001",
        headers={"Authorization": "Bearer " + token},
        timeout=30,
    ) as client:
        pool = client.get("/recommend/catalog")
        pool.raise_for_status()
        report["pool"] = pool.json()
        assert report["pool"]["photo_templates"] > 100
        response = client.post(
            "/recommend/assets",
            files={"file": ("synthetic.png", raw.getvalue(), "image/png")},
            data={"subject_selected": "true"},
        )
        response.raise_for_status()
        asset = response.json()["asset_id"]
        previous = None
        seen = set()
        for index in range(4):
            started = time.perf_counter()
            response = client.post(
                "/recommend/jobs",
                json={
                    "asset_id": asset,
                    "previous_job_id": previous,
                    "idempotency_key": uuid.uuid4().hex,
                },
            )
            response.raise_for_status()
            identifier = response.json()["job_id"]
            deadline = time.time() + 120
            while time.time() < deadline:
                response = client.get("/recommend/jobs/" + identifier)
                response.raise_for_status()
                job = response.json()
                if job["status"] in {"completed", "failed"}:
                    break
                time.sleep(0.4)
            assert job["status"] == "completed", job.get("message")
            keys = {r["key"] for r in job["results"]}
            assert len(keys) == 9 and not keys & seen
            downloaded = 0
            for result in job["results"]:
                response = client.get(result["image_url"])
                response.raise_for_status()
                downloaded += len(response.content)
                with Image.open(BytesIO(response.content)) as image:
                    assert min(image.size) > 0
            seen.update(keys)
            previous = identifier
            batch = {
                "index": index + 1,
                "keys": sorted(keys),
                "seconds": round(time.perf_counter() - started, 3),
                "bytes": downloaded,
            }
            report["batches"].append(batch)
            print(json.dumps(batch), flush=True)
        report.update(status="passed", unique_templates=len(seen))
except Exception:
    report["status"] = "failed"
    raise
finally:
    try:
        delete_account(Deletion(confirmation="注销账号"), {"id": user})
        report["fixture_cleaned"] = True
    except Exception:
        report["fixture_cleaned"] = False
    Path(a.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "batches"}), flush=True)
