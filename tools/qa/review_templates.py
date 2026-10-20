"""Make source/default/changed-caption sheets for actual visual review, never auto-approve."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend/meme-generator"))
from PIL import Image, ImageDraw
from meme_generator.features.declarative import render

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--drafts", required=True)
p.add_argument("--output", required=True)
p.add_argument("--exclude-reviewed", action="store_true")
p.add_argument("--ids", help="Review only this saved list of candidate identifiers")
a = p.parse_args()
base = Path(a.drafts)
output = Path(a.output)
output.mkdir(parents=True, exist_ok=True)
reviewed = set()
included = set(json.loads(Path(a.ids).read_text())) if a.ids else None
if a.exclude_reviewed and (base / "decisions.json").exists():
    decisions = json.loads((base / "decisions.json").read_text())
    reviewed = set(decisions.get("approved", [])) | set(decisions.get("rejected", {}))
rows = []
for path in sorted(base.glob("*.json")):
    data = json.loads(path.read_text())
    if (
        not isinstance(data, dict)
        or "spec" not in data
        or path.stem in reviewed
        or (included is not None and path.stem not in included)
    ):
        continue
    rows.append((path.stem, data))
(output / "order.json").write_text(json.dumps([r[0] for r in rows]) + "\n")
for start in range(0, len(rows), 6):
    sheet = Image.new("RGB", (990, 1410), "#e5e5e5")
    draw = ImageDraw.Draw(sheet)
    for index, (identifier, data) in enumerate(rows[start : start + 6]):
        caption = "今天不想上班"
        try:
            changed = render(
                data["spec"], [], [caption] * len(data["metadata"]["default_texts"])
            )
        except ValueError as error:
            if str(error) != "text overflows":
                raise
            caption = "累"
            changed = render(
                data["spec"], [], [caption] * len(data["metadata"]["default_texts"])
            )
        images = [
            Image.open(base / "sources" / (identifier + ".image")).convert("RGB"),
            Image.open(render(data["spec"], [], data["metadata"]["default_texts"])),
            Image.open(changed),
        ]
        draw.text(
            (5, index * 235 + 2),
            f"{start + index + 1} {identifier[:12]} SOURCE / DEFAULT / CHANGED"
            + (" (short; long rejected)" if caption == "累" else ""),
            fill="black",
        )
        for column, image in enumerate(images):
            image.thumbnail((320, 205))
            sheet.paste(
                image, (column * 330 + (320 - image.width) // 2, index * 235 + 22)
            )
    sheet.save(output / f"sheet-{start // 6 + 1}.jpg")
print(json.dumps({"drafts": len(rows), "sheets": (len(rows) + 5) // 6}))
