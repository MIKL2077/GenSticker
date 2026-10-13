"""Bounded, licensed MediaWiki adapter and deterministic conversion pipeline."""

import hashlib
import html
import json
import re
import time
from urllib.parse import urlparse
from io import BytesIO
import httpx
from PIL import Image
from .store import connect, root
from .catalog import publish, emotion_tags
from .declarative import render, TemplateSpec
from .recommend import day

HEADERS = {
    "User-Agent": "GenSticker/1.0 (https://github.com/MIKL2077/GenSticker; licensed template collector)"
}
LICENSES = {"CC0", "CC BY 4.0", "CC BY-SA 4.0", "Public domain"}


def text(value):
    return html.unescape(re.sub("<[^>]+>", "", value or ""))[:500]


def download(url, client, max_bytes=2 * 1024 * 1024):
    parsed = urlparse(url)
    allowed = parsed.hostname == "upload.wikimedia.org" or (
        parsed.hostname == "raw.githubusercontent.com"
        and parsed.path.startswith("/hfg-gmuend/openmoji/")
    )
    if parsed.scheme != "https" or not allowed:
        raise ValueError("untrusted image host")
    with client.stream("GET", url, follow_redirects=False) as response:
        response.raise_for_status()
        parts = []
        total = 0
        started = time.monotonic()
        for chunk in response.iter_bytes():
            total += len(chunk)
            if time.monotonic() - started > 20:
                raise ValueError("download time budget exceeded")
            if total > max_bytes:
                raise ValueError("image too large")
            parts.append(chunk)
        return b"".join(parts)


def convert(raw, metadata):
    """Extract a foreground replacement slot when the local model is confident."""
    from . import vision
    import numpy as np

    if vision._session is None:
        raise ValueError("segmentation model unavailable")
    with Image.open(BytesIO(raw)) as original:
        if original.width * original.height > 16000000:
            raise ValueError("image too large")
        image = original.convert("RGBA")
        image.thumbnail((768, 768))
    cutout = vision.extract(image)
    mask = cutout.getchannel("A")
    coverage = sum(v > 100 for v in mask.resize((64, 64)).getdata()) / 4096
    if not 0.05 < coverage < 0.8:
        raise ValueError("uncertain foreground")
    box = mask.getbbox()
    if not box:
        raise ValueError("missing foreground")
    # Erase the original foreground, preserving surrounding text/background.
    import cv2

    source = np.array(image.convert("RGB"))
    binary = (np.array(mask) > 30).astype("uint8") * 255
    # Expose high-confidence captions outside the subject as editable text slots.
    text_layers = []
    defaults = []
    try:
        from rapidocr_onnxruntime import RapidOCR

        ocr = RapidOCR(intra_op_num_threads=2, inter_op_num_threads=1)
        recognized, _ = ocr(source)
        for polygon, caption, confidence in recognized or []:
            if confidence < 0.9 or len(defaults) >= 5:
                continue
            points = np.asarray(polygon, dtype="int32")
            x0, y0 = points.min(axis=0)
            x1, y1 = points.max(axis=0)
            x0 = max(0, int(x0))
            y0 = max(0, int(y0))
            x1 = min(image.width, int(x1))
            y1 = min(image.height, int(y1))
            if x1 - x0 < 8 or y1 - y0 < 10:
                continue
            if np.mean(binary[y0:y1, x0:x1] > 0) > 0.15:
                continue
            cv2.fillPoly(binary, [points], 255)
            slot = len(defaults)
            defaults.append(caption[:200])
            text_layers.append(
                {
                    "type": "text",
                    "box": [x0, y0, x1 - x0, y1 - y0],
                    "slot": slot,
                    "value": caption[:200],
                    "font_size": max(10, min(100, y1 - y0 - 2)),
                }
            )
    except ImportError:
        pass
    binary = cv2.dilate(binary, np.ones((5, 5), dtype="uint8"))
    background = Image.fromarray(cv2.inpaint(source, binary, 3, cv2.INPAINT_TELEA))
    output = BytesIO()
    background.save(output, "PNG")
    asset = hashlib.sha256(output.getvalue()).hexdigest()
    directory = root() / "template_assets"
    directory.mkdir(exist_ok=True)
    (directory / (asset + ".png")).write_bytes(output.getvalue())
    x, y, x2, y2 = box
    spec = TemplateSpec.model_validate(
        {
            "width": image.width,
            "height": image.height,
            "layers": [
                {
                    "type": "asset",
                    "box": [0, 0, image.width, image.height],
                    "value": asset,
                },
                {"type": "subject", "box": [x, y, x2 - x, y2 - y]},
            ]
            + text_layers,
            "defaults": defaults,
        }
    ).model_dump()
    # Round-trip gate catches badly reconstructed layouts before auto publication.
    reconstruction = Image.open(render(spec, [cutout.crop(box)])).convert("RGB")
    a = np.asarray(image.convert("RGB").resize((64, 64))).astype("float32")
    b = np.asarray(reconstruction.resize((64, 64))).astype("float32")
    if float(abs(a - b).mean()) > 28:
        raise ValueError("round-trip quality too low")
    digest = hashlib.sha256(raw).hexdigest()
    publish(
        "auto_" + digest[:24],
        {
            **metadata,
            "min_images": 1,
            "max_images": 1,
            "min_texts": len(defaults),
            "max_texts": len(defaults),
            "default_texts": defaults,
            "tags": emotion_tags(metadata["name"]),
            "original_hash": digest,
            "conversion": "foreground-slot-v1",
        },
        spec,
    )
    return spec


def run_commons(limit=20):
    from .vision import warmup

    warmup()
    db = connect()
    stats = {"published": 0, "skipped": 0, "downloaded": 0}
    try:
        with httpx.Client(timeout=15, headers=HEADERS) as client:
            response = client.get(
                "https://commons.wikimedia.org/w/api.php",
                params={
                    "action": "query",
                    "format": "json",
                    "generator": "search",
                    "gsrsearch": "intitle:meme",
                    "gsrnamespace": 6,
                    "gsrlimit": min(limit, 20),
                    "prop": "imageinfo",
                    "iiprop": "url|extmetadata",
                    "iiurlwidth": 768,
                },
            )
            response.raise_for_status()
            pages = response.json().get("query", {}).get("pages", {})
            for page in pages.values():
                info = (page.get("imageinfo") or [{}])[0]
                ext = info.get("extmetadata", {})
                license = text(ext.get("LicenseShortName", {}).get("value"))
                if license not in LICENSES:
                    stats["skipped"] += 1
                    continue
                source = info.get("descriptionurl", "")
                url = info.get("thumburl") or info.get("url", "")
                if db.execute(
                    "SELECT 1 FROM candidates WHERE source=?", (source,)
                ).fetchone():
                    continue
                # Reserve worst-case bytes before each download, including failed attempts.
                with db:
                    db.execute("BEGIN IMMEDIATE")
                    db.execute("INSERT OR IGNORE INTO budgets(day) VALUES(?)", (day(),))
                    budget = db.execute(
                        "SELECT * FROM budgets WHERE day=?", (day(),)
                    ).fetchone()
                    monthly = db.execute(
                        "SELECT COALESCE(SUM(bytes),0) FROM budgets WHERE day LIKE ?",
                        (day()[:7] + "%",),
                    ).fetchone()[0]
                    if (
                        budget["candidates"] >= 100
                        or budget["bytes"] + 2 * 1024 * 1024 > 200 * 1024 * 1024
                        or monthly + 2 * 1024 * 1024 > 1024 * 1024 * 1024
                    ):
                        break
                    db.execute(
                        "UPDATE budgets SET bytes=bytes+?,candidates=candidates+1 WHERE day=?",
                        (2 * 1024 * 1024, day()),
                    )
                try:
                    raw = download(url, client)
                    with db:
                        db.execute(
                            "UPDATE budgets SET bytes=bytes-?+? WHERE day=?",
                            (2 * 1024 * 1024, len(raw), day()),
                        )
                    stats["downloaded"] += 1
                    digest = hashlib.sha256(raw).hexdigest()
                    if db.execute(
                        "SELECT 1 FROM candidates WHERE hash=?", (digest,)
                    ).fetchone():
                        continue
                    metadata = {
                        "name": text(page["title"]).removeprefix("File:")[:80],
                        "origin": "wikimedia-commons",
                        "source_url": source,
                        "author": text(ext.get("Artist", {}).get("value")),
                        "license": license,
                        "license_url": text(ext.get("LicenseUrl", {}).get("value")),
                        "collected_at": time.time(),
                        "hotness_method": "source-search-order",
                    }
                    try:
                        convert(raw, metadata)
                        status = "published"
                        reason = ""
                        stats["published"] += 1
                    except Exception as e:
                        status = "pending"
                        reason = type(e).__name__ + ": " + str(e)[:200]
                        stats["skipped"] += 1
                    with db:
                        db.execute(
                            "INSERT INTO candidates VALUES(?,?,?,?,?)",
                            (digest, source, status, reason, time.time()),
                        )
                except (httpx.HTTPError, ValueError):
                    stats["skipped"] += 1
        return stats
    finally:
        db.close()


# Licensed baseline expressions, not a claimed internet trending chart.
OPENMOJI = [
    ("1F602", "笑哭", "happy"),
    ("1F60D", "喜欢", "happy"),
    ("1F62D", "大哭", "sad"),
    ("1F621", "生气", "angry"),
    ("1F632", "惊讶", "surprised"),
    ("1F914", "思考", "general"),
    ("1F60E", "酷", "happy"),
    ("1F634", "困了", "general"),
    ("1F973", "庆祝", "happy"),
]


def run_openmoji(limit=9):
    db = connect()
    stats = {"published": 0, "skipped": 0, "downloaded": 0}
    try:
        with httpx.Client(timeout=15, headers=HEADERS) as client:
            for code, name, emotion in OPENMOJI[:limit]:
                source = f"https://github.com/hfg-gmuend/openmoji/blob/master/color/72x72/{code}.png"
                if db.execute(
                    "SELECT 1 FROM candidates WHERE source=?", (source,)
                ).fetchone():
                    continue
                with db:
                    db.execute("BEGIN IMMEDIATE")
                    db.execute("INSERT OR IGNORE INTO budgets(day) VALUES(?)", (day(),))
                    budget = db.execute(
                        "SELECT * FROM budgets WHERE day=?", (day(),)
                    ).fetchone()
                    monthly = db.execute(
                        "SELECT COALESCE(SUM(bytes),0) FROM budgets WHERE day LIKE ?",
                        (day()[:7] + "%",),
                    ).fetchone()[0]
                    if (
                        budget["candidates"] >= 100
                        or budget["bytes"] + 2 * 1024 * 1024 > 200 * 1024 * 1024
                        or monthly + 2 * 1024 * 1024 > 1024 * 1024 * 1024
                    ):
                        break
                    db.execute(
                        "UPDATE budgets SET bytes=bytes+?,candidates=candidates+1 WHERE day=?",
                        (2 * 1024 * 1024, day()),
                    )
                try:
                    raw = download(
                        f"https://raw.githubusercontent.com/hfg-gmuend/openmoji/master/color/72x72/{code}.png",
                        client,
                    )
                    with db:
                        db.execute(
                            "UPDATE budgets SET bytes=bytes-?+? WHERE day=?",
                            (2 * 1024 * 1024, len(raw), day()),
                        )
                    stats["downloaded"] += 1
                    digest = hashlib.sha256(raw).hexdigest()
                    with Image.open(BytesIO(raw)) as image:
                        out = BytesIO()
                        image.convert("RGBA").save(out, "PNG")
                    asset = hashlib.sha256(out.getvalue()).hexdigest()
                    directory = root() / "template_assets"
                    directory.mkdir(exist_ok=True)
                    (directory / (asset + ".png")).write_bytes(out.getvalue())
                    spec = {
                        "width": 512,
                        "height": 512,
                        "defaults": [name + "一下"],
                        "layers": [
                            {"type": "subject", "box": [16, 16, 480, 382]},
                            {"type": "asset", "box": [20, 414, 72, 72], "value": asset},
                            {
                                "type": "text",
                                "box": [112, 424, 380, 68],
                                "font_size": 42,
                                "slot": 0,
                            },
                        ],
                    }
                    metadata = {
                        "name": name + "配图",
                        "min_images": 1,
                        "max_images": 1,
                        "min_texts": 1,
                        "max_texts": 1,
                        "default_texts": [name + "一下"],
                        "tags": [emotion],
                        "origin": "openmoji",
                        "source_url": source,
                        "author": "OpenMoji contributors",
                        "license": "CC BY-SA 4.0",
                        "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
                        "conversion": "emoji-frame-v1",
                        "hotness_method": "curated-baseline",
                        "original_hash": digest,
                        "collected_at": time.time(),
                        "subject_types": ["person", "animal", "object", "unknown"],
                        "slot_aspect": 480 / 382,
                    }
                    publish("auto_openmoji_" + code.lower(), metadata, spec)
                    with db:
                        db.execute(
                            "INSERT OR REPLACE INTO candidates VALUES(?,?,?,?,?)",
                            (digest, source, "published", "", time.time()),
                        )
                    stats["published"] += 1
                except (httpx.HTTPError, ValueError, OSError):
                    stats["skipped"] += 1
        return stats
    finally:
        db.close()


def run(limit=20):
    stats = {"openmoji": run_openmoji(min(9, limit))}
    try:
        stats["commons"] = run_commons(limit)
    except (httpx.HTTPError, ValueError):
        stats["commons"] = {
            "status": "source-unavailable",
            "retry": "next scheduled run",
        }
    return stats


if __name__ == "__main__":
    try:
        print(json.dumps(run(), ensure_ascii=False))
    except Exception as e:
        print("Ingestion unavailable:", type(e).__name__)
        raise SystemExit(1)
