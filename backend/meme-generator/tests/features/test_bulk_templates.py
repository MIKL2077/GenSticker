import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from meme_generator.features.bulk_templates import (
    chinese_inventory,
    weshine_inventory,
    select_candidates,
    register,
    prepare,
    checked_candidates,
)
from meme_generator.features.recommendation import exclusion_reason, pool_summary
from meme_generator.features import catalog, worker
from meme_generator.features.store import connect
from meme_generator.features.declarative import font


class ExpansionTests(unittest.TestCase):
    def test_manifest_rejects_traversal_before_download_or_conversion(self):
        for identifier in ["../../outside", "../" + "a" * 64, "A" * 64, "a" * 63]:
            with self.assertRaisesRegex(ValueError, "identity"):
                checked_candidates(
                    {"candidates": [{"id": identifier, "origin": "chinesebqb"}]}
                )

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(
            os.environ,
            {"GENSTICKER_STATE_DIR": self.temp.name, "GENSTICKER_BOOTSTRAP_SEEDS": "0"},
        )
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def test_inventory_pins_revision_deduplicates_and_balances_categories(self):
        tree = {
            "sha": "a" * 40,
            "truncated": False,
            "tree": [
                {"type": "blob", "path": "cat/one.png", "sha": "1", "size": 100},
                {"type": "blob", "path": "cat/copy.png", "sha": "1", "size": 100},
                {"type": "blob", "path": "cat/two.png", "sha": "2", "size": 100},
                {"type": "blob", "path": "dog/one.jpg", "sha": "3", "size": 100},
                {"type": "blob", "path": "dog/animated.gif", "sha": "4", "size": 100},
                {"type": "blob", "path": "../bad.png", "sha": "5", "size": 100},
            ],
        }
        inventory = chinese_inventory(tree)
        self.assertEqual(len(inventory), 4)
        chosen = select_candidates(inventory, 2)
        self.assertEqual({x["category"] for x in chosen}, {"cat", "dog"})
        self.assertTrue(all("/" + "a" * 40 + "/" in x["source_url"] for x in chosen))
        self.assertEqual(register(chosen), 2)
        self.assertEqual(register(chosen), 0)
        with self.assertRaisesRegex(ValueError, "incomplete"):
            chinese_inventory({**tree, "truncated": True})

    def test_weshine_only_observed_media_without_executing_script(self):
        html = '<script>throw new Error("not code")</script><img src="https://dl5.weshineapp.com/gif/2026/s_a.jpg"><img src="https://dl5.weshineapp.com/gif/2026/s_a.jpg"><img src="https://evil.example/a.jpg"><img src="https://dl5.weshineapp.com/weshine/upload_user/avatar">'
        rows = weshine_inventory(html)
        self.assertEqual(len(rows), 1)
        self.assertIn("/s_a.jpg", rows[0]["image_url"])
        self.assertEqual(rows[0]["license_status"], "unverified")
        # No source material is downloaded without the appropriate explicit mode.
        with patch("meme_generator.features.bulk_templates.fetch") as fetch:
            result = prepare({"candidates": rows}, [], Path(self.temp.name) / "drafts")
            fetch.assert_not_called()
        self.assertEqual(result["published"], 0)

    def test_pool_count_and_recommendations_use_same_expanded_policy(self):
        catalog.bootstrap()
        available = catalog.rows()
        summary = pool_summary(available)
        choices = worker.candidates(
            {"id": "audit", "user_id": "audit"},
            {"expression": "general", "confidence": 0},
        )
        self.assertEqual(summary["photo_templates"], len(choices))
        self.assertGreater(len(choices), 100)
        self.assertNotIn("universal", [row["key"] for row in choices])
        row = dict(choices[0])
        metadata = json.loads(row["metadata"])
        metadata["min_texts"] = 2
        metadata["default_texts"] = []
        row["metadata"] = json.dumps(metadata)
        self.assertEqual(exclusion_reason(row), "requires-user-text")

    def test_many_batches_do_not_cycle_after_eighteen(self):
        catalog.bootstrap()
        seen = set()
        previous = set()
        for index in range(6):
            identifier = f"audit-{index}"
            db = connect()
            with db:
                db.execute(
                    "INSERT INTO job_variations VALUES(?,?,?,?)",
                    (
                        identifier,
                        "parent",
                        json.dumps(sorted(seen)),
                        json.dumps(sorted(previous)),
                    ),
                )
            db.close()
            choices = worker.candidates(
                {"id": identifier, "user_id": "audit"},
                {"expression": "general", "confidence": 0},
            )[:9]
            current = {row["key"] for row in choices}
            self.assertEqual(len(current), 9)
            self.assertFalse(current & seen)
            seen.update(current)
            previous = current
        self.assertEqual(len(seen), 54)

    def test_chinese_caption_font_has_real_distinct_glyphs(self):
        face = font(24)
        self.assertNotEqual(bytes(face.getmask("我")), bytes(face.getmask("想")))
        self.assertNotEqual(
            bytes(face.getmask("我")), bytes(face.getmask("\U0010ffff"))
        )

    def test_reviewed_reference_batches_restore_without_inflating_photo_pool(self):
        from meme_generator.features.seed import restore

        restored = restore()
        self.assertGreater(restored, 1)
        references = [
            row
            for row in catalog.rows()
            if json.loads(row["metadata"]).get("origin") in {"chinesebqb", "weshine"}
        ]
        self.assertTrue(references)
        for row in references:
            metadata = json.loads(row["metadata"])
            self.assertEqual(metadata["license"], "unverified")
            self.assertEqual(metadata["review"]["visual_status"], "approved")
            self.assertGreater(metadata["created_at"], 0)
            self.assertEqual(exclusion_reason(row), None if metadata.get('conversion') in {'reaction-story-v1','element-replacement-v1'} and metadata.get('max_images')==1 else 'requires-different-image-count')
        self.assertEqual(restore(), 0)


if __name__ == "__main__":
    unittest.main()
