"""Verify real single-image renders before admitting bundled templates to AI matching."""

import argparse
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent
if ROOT.name == "qa":
    ROOT = ROOT.parent.parent
BACKEND = Path(os.getenv("GENSTICKER_QA_BACKEND") or ROOT / "backend/meme-generator")
sys.path.insert(0, str(BACKEND))


def probe(key, output):
    from PIL import Image, ImageDraw
    from meme_generator.manager import get_meme

    meme = get_meme(key)
    sample = Image.new("RGBA", (256, 256))
    draw = ImageDraw.Draw(sample)
    draw.ellipse((32, 12, 224, 244), fill="#eac392")
    draw.ellipse((80, 80, 100, 110), fill="black")
    draw.ellipse((156, 80, 176, 110), fill="black")
    draw.arc((80, 110, 176, 190), 0, 180, fill="black", width=6)
    buf = BytesIO()
    sample.save(buf, "PNG")
    start = time.perf_counter()
    raw = meme(images=[buf.getvalue()], texts=meme.params_type.default_texts).getvalue()
    elapsed = time.perf_counter() - start
    with Image.open(BytesIO(raw)) as image:
        frames = getattr(image, "n_frames", 1)
        eligible = (
            elapsed <= 2
            and len(raw) <= 1536 * 1024
            and frames <= 60
            and max(image.size) <= 1600
        )
        row = {
            "key": key,
            "name": meme.keywords[0],
            "status": "passed" if eligible else "over-budget",
            "seconds": round(elapsed, 4),
            "bytes": len(raw),
            "frames": frames,
            "width": image.width,
            "height": image.height,
        }
        # First frames are review aids, not animation-quality approval.
        image.convert("RGB").save(output / (key + ".jpg"))
    print("POOL_RESULT " + json.dumps(row, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key")
    parser.add_argument("--output", required=True)
    parser.add_argument("--policy", help="Only verify keys from this proposed policy")
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    if args.key:
        probe(args.key, output)
        return
    from meme_generator.manager import get_memes

    # These require identity/name input, sexual framing, or heavy transformations;
    # they remain available through explicit manual selection.
    excluded = {
        "rip_clothes",
        "abstinence",
        "saimin_app",
        "my_wife",
        "marriage",
        "divorce",
        "name_generator",
        "always_like",
        "alipay",
        "ask",
        "google_captcha",
        "make_friend",
        "wechat_pay",
        "why_have_hands",
    }
    keys = sorted(
        m.key
        for m in get_memes()
        if m.key not in excluded
        and m.params_type.min_images <= 1 <= m.params_type.max_images
        and m.params_type.min_texts
        <= len(m.params_type.default_texts)
        <= m.params_type.max_texts
    )
    if args.policy:
        proposed = set(json.loads(Path(args.policy).read_text())["keys"])
        keys = [key for key in keys if key in proposed]
    results = []
    with tempfile.TemporaryDirectory(prefix="gensticker-pool-") as state:
        env = {
            **os.environ,
            "GENSTICKER_STATE_DIR": state,
            "GENSTICKER_BOOTSTRAP_SEEDS": "0",
            "PYTHONPATH": str(BACKEND),
        }
        for index, key in enumerate(keys):
            try:
                result = subprocess.run(
                    [sys.executable, __file__, "--key", key, "--output", str(output)],
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=12,
                )
                lines = [
                    line[12:]
                    for line in result.stdout.splitlines()
                    if line.startswith("POOL_RESULT ")
                ]
                row = (
                    json.loads(lines[-1])
                    if result.returncode == 0 and lines
                    else {"key": key, "status": "failed"}
                )
            except subprocess.TimeoutExpired:
                row = {"key": key, "status": "timeout"}
            results.append(row)
            (output / "report.json").write_text(
                json.dumps(
                    {
                        "scope": "single transparent synthetic subject, default texts; local performance only",
                        "results": results,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n"
            )
            if (index + 1) % 25 == 0:
                print(
                    f"Pool {index + 1}/{len(keys)}: {sum(r['status'] == 'passed' for r in results)} passed",
                    flush=True,
                )


if __name__ == "__main__":
    main()
