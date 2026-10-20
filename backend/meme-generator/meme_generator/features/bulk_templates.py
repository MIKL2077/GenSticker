"""Offline, resumable source inventory and skill conversion. Counts never imply publication."""

import argparse
import base64
from datetime import datetime
from collections import Counter, defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path, PurePosixPath
import subprocess
import time
from urllib.parse import quote, urlsplit
from zoneinfo import ZoneInfo

from .store import connect

TREE_URL = (
    "https://api.github.com/repos/zhaoolee/ChineseBQB/git/trees/master?recursive=1"
)
WESHINE_URL = "https://u.weshineapp.com/"
STATIC = {".jpg", ".jpeg", ".png", ".webp"}


def fetch(url, cap=12 * 1024 * 1024):
    """Fixed public source hosts, no redirect following or credentials, bounded bytes/time."""
    parsed = urlsplit(url)
    allowed = url == TREE_URL or (
        parsed.hostname == "u.weshineapp.com"
        and parsed.path in {"/", "/hot", "/rank/expression_tot_1"}
    )
    allowed |= (
        parsed.hostname == "raw.githubusercontent.com"
        and parsed.path.startswith("/zhaoolee/ChineseBQB/")
    )
    allowed |= parsed.hostname == "dl5.weshineapp.com" and parsed.path.startswith(
        "/gif/"
    )
    if (
        not allowed
        or parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
    ):
        raise ValueError("untrusted source URL")
    result = subprocess.run(
        [
            "curl",
            "--fail",
            "--silent",
            "--show-error",
            "--connect-timeout",
            "10",
            "--max-time",
            "45",
            "--max-filesize",
            str(cap),
            "--proto",
            "=https",
            "-H",
            "User-Agent: GenSticker-template-discovery",
            url,
        ],
        capture_output=True,
        timeout=50,
        check=True,
    )
    if len(result.stdout) > cap:
        raise ValueError("source byte limit exceeded")
    return result.stdout


def chinese_inventory(payload):
    if payload.get("truncated") or not isinstance(payload.get("tree"), list):
        raise ValueError("incomplete GitHub tree; do not count it as a full inventory")
    revision = payload.get("sha", "")
    if len(revision) != 40 or any(c not in "0123456789abcdef" for c in revision):
        raise ValueError("missing immutable source revision")
    seen = set()
    items = []
    for node in payload["tree"]:
        path = node.get("path", "")
        p = PurePosixPath(path)
        if node.get("type") != "blob" or p.suffix.lower() not in STATIC | {".gif"}:
            continue
        if p.is_absolute() or ".." in p.parts or len(p.parts) < 2 or len(path) > 1000:
            continue
        if not 0 < node.get("size", 0) <= 2 * 1024 * 1024:
            continue
        identity = node.get("sha")
        if not identity or identity in seen:
            continue
        seen.add(identity)
        encoded = quote(path, safe="/")
        source = f"https://github.com/zhaoolee/ChineseBQB/blob/{revision}/{encoded}"
        items.append(
            {
                "id": hashlib.sha256(source.encode()).hexdigest(),
                "origin": "chinesebqb",
                "name": p.stem[:100],
                "category": p.parts[0],
                "source_url": source,
                "image_url": f"https://raw.githubusercontent.com/zhaoolee/ChineseBQB/{revision}/{encoded}",
                "source_revision": revision,
                "source_blob": identity,
                "bytes": node["size"],
                "animated": p.suffix.lower() == ".gif",
                "license_status": "unverified",
                "author": None,
                "license": None,
                "license_url": None,
                "status": "license-pending",
                "conversion_status": "not-attempted",
            }
        )
    return items


class WeshineImages(HTMLParser):
    def __init__(self):
        super().__init__()
        self.items = {}

    def handle_starttag(self, tag, attrs):
        if tag != "img":
            return
        attrs = dict(attrs)
        url = attrs.get("src", "")
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "dl5.weshineapp.com"
            or not parsed.path.startswith("/gif/")
        ):
            return
        # Keep the observed URL, including thumbnail prefix; never invent an original URL.
        if PurePosixPath(parsed.path).suffix.lower() not in STATIC | {".gif"}:
            return
        self.items[url] = attrs.get("alt") or ""


def weshine_inventory(html, page_url=WESHINE_URL):
    if page_url not in {
        WESHINE_URL,
        WESHINE_URL + "hot",
        WESHINE_URL + "rank/expression_tot_1",
    }:
        raise ValueError("untrusted source page")
    parser = WeshineImages()
    parser.feed(html)
    return [
        {
            "id": hashlib.sha256(url.encode()).hexdigest(),
            "origin": "weshine",
            "name": name[:100],
            "category": "weshine-public-page",
            "source_url": page_url,
            "image_url": url,
            "animated": urlsplit(url).path.lower().endswith(".gif"),
            "license_status": "unverified",
            "author": None,
            "license": None,
            "license_url": None,
            "status": "license-pending",
            "conversion_status": "not-attempted",
        }
        for url, name in parser.items.items()
    ]


def weshine_state_inventory(state, *, ranked=False):
    data = state["data"][0]
    observed = []
    if ranked:
        observed = data.get("rankListData", [])
    else:
        observed += data.get("sendBoardData", [])
        for group in data.get("sentimentData", []):
            observed += [
                {"img": url, "category": group.get("desc", "")}
                for url in group.get("img", [])
            ]
    items = []
    for entry in observed:
        url = entry.get("img", "")
        if not isinstance(url, str):
            continue
        # Reuse the exact same observed-host/media filter as the HTML adapter.
        import html

        parsed = weshine_inventory(
            '<img src="' + html.escape(url, quote=True) + '">',
            WESHINE_URL + "rank/expression_tot_1" if ranked else WESHINE_URL,
        )
        if parsed:
            item = parsed[0]
            item.update(
                category="weshine-" + entry.get("category", "rank"),
                source_rank=entry.get("rank"),
                source_heat=entry.get("hot_num"),
                hotness_method="weshine-public-ranking"
                if entry.get("rank")
                else "weshine-reaction-category",
            )
            items.append(item)
    return items


def select_candidates(items, target):
    """Static layouts first, round-robin categories; stable order across retries."""
    groups = defaultdict(list)
    seen = set()
    for item in items:
        if not item["animated"] and item["id"] not in seen:
            seen.add(item["id"])
            groups[item["category"]].append(item)
    queues = [
        deque(
            sorted(group, key=lambda row: (row.get("source_rank") or 100000, row["id"]))
        )
        for _, group in sorted(groups.items())
    ]
    chosen = []
    while queues and len(chosen) < target:
        for queue in queues:
            if queue and len(chosen) < target:
                chosen.append(queue.popleft())
        queues = [queue for queue in queues if queue]
    return chosen


def register(items):
    db = connect()
    count = 0
    try:
        with db:
            for item in items:
                count += db.execute(
                    "INSERT OR IGNORE INTO candidates VALUES(?,?,?,?,?)",
                    (
                        item["id"],
                        item["source_url"],
                        "license-pending",
                        json.dumps(item, ensure_ascii=False),
                        time.time(),
                    ),
                ).rowcount
        return count
    finally:
        db.close()


def checked_candidates(manifest):
    items = manifest.get("candidates")
    if not isinstance(items, list) or len(items) > 10000:
        raise ValueError("invalid candidate manifest")
    for item in items:
        identifier = item.get("id", "")
        if (
            not isinstance(identifier, str)
            or len(identifier) != 64
            or any(c not in "0123456789abcdef" for c in identifier)
            or item.get("origin") not in {"chinesebqb", "weshine"}
        ):
            raise ValueError("invalid candidate identity or source")
    return items


def download_candidates(manifest, output, limit=1200, byte_budget=512 * 1024 * 1024):
    cache = output / "sources"
    cache.mkdir(parents=True, exist_ok=True)
    items = checked_candidates(manifest)[:limit]
    # Reserve the worst-case response bytes before submission; failures also consume a reservation.
    pending = [x for x in items if not (cache / (x["id"] + ".image")).exists()]
    existing_bytes = sum(p.stat().st_size for p in cache.glob("*.image"))
    pending = pending[: max(0, (byte_budget - existing_bytes) // (2 * 1024 * 1024))]
    results = []

    def one(item):
        try:
            raw = fetch(item["image_url"], 2 * 1024 * 1024)
            (cache / (item["id"] + ".image")).write_bytes(raw)
            return {"id": item["id"], "status": "downloaded", "bytes": len(raw)}
        except (ValueError, OSError, subprocess.SubprocessError):
            return {"id": item["id"], "status": "source-unavailable"}

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(one, item) for item in pending]
        for future in as_completed(futures):
            results.append(future.result())
            if len(results) % 20 == 0:
                print(
                    json.dumps(
                        {
                            "downloaded": sum(
                                r["status"] == "downloaded" for r in results
                            ),
                            "processed": len(results),
                            "scheduled": len(pending),
                        }
                    ),
                    flush=True,
                )
            (output / "download-report.json").write_text(
                json.dumps(results, indent=2) + "\n"
            )
    return {
        "cached": len(list(cache.glob("*.image"))),
        "processed": len(results),
        "cache_bytes": sum(p.stat().st_size for p in cache.glob("*.image")),
    }


def prepare(
    manifest, rights, output, limit=20, *, attributed_references=False, cache_only=False
):
    """Apply the skill's strict converter to individually licensed items; leave visual review pending."""
    from .ingest import LICENSES
    from .quality import convert_caption

    output.mkdir(parents=True, exist_ok=True)
    approvals = {item["id"]: item for item in rights}
    results = []
    attempted = 0
    intents = set()
    visuals = set()
    for item in checked_candidates(manifest):
        approval = approvals.get(item["id"], {})
        metadata = {
            **item,
            **{k: approval.get(k) for k in ("author", "license", "license_url")},
        }
        required = ("author", "license_url", "evidence_url")
        user_reference = attributed_references and item["origin"] in {
            "chinesebqb",
            "weshine",
        }
        if not user_reference and (
            metadata["license"] not in LICENSES
            or any(not approval.get(k) for k in required)
        ):
            results.append({"id": item["id"], "status": "license-pending"})
            continue
        path = output / (item["id"] + ".json")
        if path.exists():
            old = json.loads(path.read_text())["metadata"]
            intents.add(old["intent_signature"])
            visuals.add(old["perceptual_hash"])
            results.append(
                {"id": item["id"], "status": "review-pending", "resumed": True}
            )
            continue
        if attempted >= limit:
            results.append({"id": item["id"], "status": "queued"})
            continue
        attempted += 1
        try:
            metadata["rights_evidence_url"] = approval.get("evidence_url")
            if user_reference:
                metadata.update(
                    license="unverified",
                    license_status="unverified",
                    source_use="explicit-user-request-with-attribution",
                    author="ChineseBQB 收录（原作者未标明）"
                    if item["origin"] == "chinesebqb"
                    else "闪萌收录（原作者未标明）",
                    license_url="",
                )
            cache = output / "sources"
            cache.mkdir(exist_ok=True)
            source = cache / (item["id"] + ".image")
            if cache_only and not source.exists():
                results.append({"id": item["id"], "status": "source-unavailable"})
                continue
            raw = (
                source.read_bytes()
                if source.exists()
                else fetch(item["image_url"], 2 * 1024 * 1024)
            )
            if not source.exists():
                source.write_bytes(raw)
            spec, metadata = convert_caption(raw, metadata, publish_result=False)
            if metadata["intent_signature"] in intents or any(
                (int(metadata["perceptual_hash"], 16) ^ int(old, 16)).bit_count() <= 4
                for old in visuals
            ):
                raise ValueError("duplicate draft intent or visual")
            intents.add(metadata["intent_signature"])
            visuals.add(metadata["perceptual_hash"])
            from .declarative import render

            path.with_suffix(".png").write_bytes(
                render(spec, [], metadata["default_texts"]).getvalue()
            )
            path.write_text(
                json.dumps(
                    {"metadata": metadata, "spec": spec, "status": "review-pending"},
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n"
            )
            results.append({"id": item["id"], "status": "review-pending"})
        except (ValueError, OSError, subprocess.SubprocessError) as error:
            results.append(
                {
                    "id": item["id"],
                    "status": "quality-pending",
                    "reason": str(error)[:200],
                }
            )
        if attempted % 20 == 0:
            print(
                json.dumps({"attempted": attempted, "drafts": len(intents)}), flush=True
            )
        (output / "report.json").write_text(
            json.dumps(
                {
                    "attempted": attempted,
                    "published": 0,
                    "counts": dict(Counter(row["status"] for row in results)),
                    "results": results,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        )
    report = {
        "attempted": attempted,
        "published": 0,
        "counts": dict(Counter(row["status"] for row in results)),
        "results": results,
    }
    (output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    )
    return {k: v for k, v in report.items() if k != "results"}


def export_reviewed(directory, decisions, destination, *, version=1):
    """Export only explicitly inspected reconstructions plus changed-text outputs."""
    import numpy as np
    from PIL import Image
    from .declarative import render, TemplateSpec
    from .store import root

    if len(decisions["approved"]) > 100:
        raise ValueError("split reviewed templates into batches of at most 100")
    if not 1 <= version <= 1000000:
        raise ValueError("invalid template version")
    bundle = {"templates": [], "assets": {}}
    intents = set()
    visuals = set()
    for identifier in decisions["approved"]:
        if len(identifier) != 64 or any(
            c not in "0123456789abcdef" for c in identifier
        ):
            raise ValueError("invalid review identifier")
        item = json.loads((directory / (identifier + ".json")).read_text())
        m = item["metadata"]
        m.setdefault("created_at", time.time())
        if m["intent_signature"] in intents or any(
            (int(m["perceptual_hash"], 16) ^ int(old, 16)).bit_count() <= 4
            for old in visuals
        ):
            raise ValueError("duplicate approved intent or visual")
        intents.add(m["intent_signature"])
        visuals.add(m["perceptual_hash"])
        spec = TemplateSpec.model_validate(item["spec"]).model_dump()
        if (
            m.get("origin") not in {"chinesebqb", "weshine"}
            or m.get("source_use") != "explicit-user-request-with-attribution"
        ):
            raise ValueError("unexpected reviewed source")
        with Image.open(directory / "sources" / (identifier + ".image")) as image:
            source = image.convert("RGB")
            source.thumbnail((768, 768))
        rebuilt = Image.open(render(spec, [], m["default_texts"])).convert("RGB")
        changed_caption = "今天不想上班"
        long_rejected = False
        try:
            render(spec, [], [changed_caption] * len(m["default_texts"]))
        except ValueError as error:
            if str(error) != "text overflows":
                raise
            changed_caption = "累"
            long_rejected = True
            render(spec, [], [changed_caption] * len(m["default_texts"]))
            m["input_hint"] = "此模板适合短词，文字过长时请缩短后重试"
        error = float(
            np.abs(
                np.asarray(source.resize((128, 128))).astype("float32")
                - np.asarray(rebuilt.resize((128, 128))).astype("float32")
            ).mean()
        )
        if error > 12:
            raise ValueError("reviewed reconstruction exceeds quality budget")
        m["quality"]["round_trip_mae"] = round(error, 2)
        m["review"] = {
            **m.get("review", {}),
            "visual_status": "approved",
            "checks": ["source", "default-caption", "changed-caption"],
            "date": datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat(),
            "changed_caption": changed_caption,
            "long_caption_rejected": long_rejected,
        }
        bundle["templates"].append(
            {
                "key": "auto_" + m["original_hash"][:24],
                "version": version,
                "metadata": m,
                "spec": spec,
            }
        )
        # Keep the collection date stable across subsequent version exports.
        item["metadata"] = m
        (directory / (identifier + ".json")).write_text(
            json.dumps(item, ensure_ascii=False, indent=2) + "\n"
        )
        for layer in spec["layers"]:
            if layer["type"] == "asset":
                digest = layer["value"]
                raw = (root() / "template_assets" / (digest + ".png")).read_bytes()
                if hashlib.sha256(raw).hexdigest() != digest:
                    raise ValueError("asset checksum mismatch")
                bundle["assets"][digest] = base64.b64encode(raw).decode()
    destination.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(bundle, ensure_ascii=False, separators=(",", ":")) + "\n"
    if len(serialized.encode()) > 32 * 1024 * 1024:
        raise ValueError("split the asset bundle below 32 MiB")
    destination.write_text(serialized)
    return {"exported": len(bundle["templates"]), "assets": len(bundle["assets"])}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    inventory = sub.add_parser("inventory")
    inventory.add_argument("--tree-file")
    inventory.add_argument("--weshine-file")
    inventory.add_argument("--weshine-state-file")
    inventory.add_argument("--weshine-rank-file")
    inventory.add_argument("--target", type=int, default=1200)
    inventory.add_argument("--output", required=True)
    inventory.add_argument("--register", action="store_true")
    draft = sub.add_parser("prepare")
    draft.add_argument("--manifest", required=True)
    draft.add_argument("--rights")
    draft.add_argument(
        "--attributed-references",
        action="store_true",
        help="Use only when the user explicitly requests these reference sources without a license manifest; record unverified rights honestly",
    )
    draft.add_argument("--output", required=True)
    draft.add_argument("--limit", type=int, default=20)
    draft.add_argument("--cache-only", action="store_true")
    download = sub.add_parser("download")
    download.add_argument("--manifest", required=True)
    download.add_argument("--output", required=True)
    download.add_argument("--limit", type=int, default=1200)
    download.add_argument("--byte-budget", type=int, default=512 * 1024 * 1024)
    export = sub.add_parser("export-reviewed")
    export.add_argument("--drafts", required=True)
    export.add_argument("--decisions", required=True)
    export.add_argument("--output", required=True)
    export.add_argument(
        "--version",
        type=int,
        default=1,
        help="Bump when updating an already-published batch",
    )
    a = p.parse_args()
    if a.command == "export-reviewed":
        print(
            json.dumps(
                export_reviewed(
                    Path(a.drafts),
                    json.loads(Path(a.decisions).read_text()),
                    Path(a.output),
                    version=a.version,
                )
            )
        )
        return
    if a.command == "download":
        if not 1 <= a.limit <= 10000 or not 0 < a.byte_budget <= 2 * 1024**3:
            p.error("invalid download bounds")
        print(
            json.dumps(
                download_candidates(
                    json.loads(Path(a.manifest).read_text()),
                    Path(a.output),
                    a.limit,
                    a.byte_budget,
                )
            )
        )
        return
    if a.command == "prepare":
        if not 1 <= a.limit <= 2000:
            p.error("limit must be 1..2000")
        if not a.rights and not a.attributed_references:
            p.error(
                "provide --rights, or an explicitly user-authorized --attributed-references run"
            )
        print(
            json.dumps(
                prepare(
                    json.loads(Path(a.manifest).read_text()),
                    json.loads(Path(a.rights).read_text()) if a.rights else [],
                    Path(a.output),
                    a.limit,
                    attributed_references=a.attributed_references,
                    cache_only=a.cache_only,
                )
            )
        )
        return
    if not 1 <= a.target <= 10000:
        p.error("target must be 1..10000")
    tree = json.loads(Path(a.tree_file).read_text() if a.tree_file else fetch(TREE_URL))
    html = (
        Path(a.weshine_file).read_text()
        if a.weshine_file
        else fetch(WESHINE_URL, 2 * 1024 * 1024).decode()
    )
    # Prefer entries carrying actual source ranking over duplicate HTML images.
    items = []
    if a.weshine_rank_file:
        items += weshine_state_inventory(
            json.loads(Path(a.weshine_rank_file).read_text()), ranked=True
        )
    if a.weshine_state_file:
        items += weshine_state_inventory(
            json.loads(Path(a.weshine_state_file).read_text())
        )
    items += weshine_inventory(html) + chinese_inventory(tree)
    selected = select_candidates(items, a.target)
    report = {
        "version": 1,
        "target": a.target,
        "indexed": len(items),
        "selected": len(selected),
        "categories": len({x["category"] for x in selected}),
        "sources": dict(Counter(x["origin"] for x in selected)),
        "published": 0,
        "ai_eligible_added": 0,
        "license_pending": len(selected),
        "note": "Candidates are not usable templates. Caption conversion does not add a photo slot.",
        "candidates": selected,
    }
    output = Path(a.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    if a.register:
        report["newly_registered"] = register(selected)
    print(
        json.dumps(
            {k: v for k, v in report.items() if k != "candidates"}, ensure_ascii=False
        )
    )


if __name__ == "__main__":
    main()
