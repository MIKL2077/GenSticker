"""One eligibility rule shared by recommendations and the displayed pool count."""

from functools import lru_cache
import json
from pathlib import Path


@lru_cache(maxsize=1)
def bundled_policy():
    return json.loads(
        Path(__file__).with_name("recommendation_policy.json").read_text()
    )


def exclusion_reason(row, subject=None):
    metadata = json.loads(row["metadata"])
    if metadata.get("conversion") == "foreground-slot-v1":
        return "unreviewed-subject-replacement"
    if not metadata.get("min_images", 0) <= 1 <= metadata.get("max_images", 0):
        return "requires-different-image-count"
    if (
        not metadata.get("min_texts", 0)
        <= len(metadata.get("default_texts", []))
        <= metadata.get("max_texts", 0)
    ):
        return "requires-user-text"
    if not row.get("spec") and row["key"] not in bundled_policy()["keys"]:
        return "single-image-render-not-reviewed"
    if subject is not None and subject not in metadata.get(
        "subject_types", ["person", "animal", "object", "unknown"]
    ):
        return "subject-type-mismatch"
    return None


def pool_summary(catalog_rows):
    eligible = [row for row in catalog_rows if exclusion_reason(row) is None]
    return {
        "catalog_total": len(catalog_rows),
        "photo_templates": len(eligible),
        "by_subject": {
            subject: sum(exclusion_reason(row, subject) is None for row in eligible)
            for subject in ("person", "animal", "object", "unknown")
        },
    }
