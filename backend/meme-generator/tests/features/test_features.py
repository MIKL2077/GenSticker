import os
import tempfile
import unittest
from io import BytesIO
from unittest.mock import patch
from PIL import Image
from fastapi import FastAPI
from fastapi.testclient import TestClient
from meme_generator.account import current_user
from meme_generator.features import catalog, recommend, worker
from meme_generator.features.store import connect
from meme_generator.features.declarative import TemplateSpec, render


class FeatureTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.env = patch.dict(
            os.environ,
            {
                "GENSTICKER_STATE_DIR": self.directory.name,
                "GENSTICKER_BOOTSTRAP_SEEDS": "0",
            },
        )
        self.env.start()
        catalog.bootstrap()
        db = connect()
        import time

        with db:
            db.execute("INSERT INTO worker_state VALUES(1,?,1)", (time.time(),))
        db.close()
        app = FastAPI()
        app.include_router(recommend.router)
        app.include_router(catalog.router)
        self.owner = "a"
        app.dependency_overrides[current_user] = lambda: {"id": self.owner}
        self.app = app
        self.client = TestClient(app)
        buf = BytesIO()
        Image.new("RGB", (512, 384), "red").save(buf, "JPEG")
        self.photo = buf.getvalue()

    def tearDown(self):
        self.client.close()
        self.env.stop()
        self.directory.cleanup()

    def upload(self):
        r = self.client.post(
            "/recommend/assets", files={"file": ("photo.jpg", self.photo, "image/jpeg")}
        )
        self.assertEqual(r.status_code, 201)
        return r.json()["asset_id"]

    def create(self, asset, key="test-idempotency"):
        return self.client.post(
            "/recommend/jobs", json={"asset_id": asset, "idempotency_key": key}
        )

    def finish(self):
        job = worker.claim()
        self.assertIsNotNone(job)

        def process(path):
            return Image.open(path).convert("RGBA"), {
                "expression": "general",
                "confidence": 0,
                "warnings": [],
            }

        def generator(key):
            def fn(**kwargs):
                out = BytesIO()
                Image.new("RGB", (512, 512), "blue").save(out, "JPEG")
                return out

            return fn

        with (
            patch.object(worker, "process", side_effect=process),
            patch.object(worker, "get_meme", side_effect=generator),
        ):
            worker.run_job(job)
        return job["id"]

    def test_dsl_and_stable_versions(self):
        spec = {
            "layers": [
                {"type": "subject", "box": [0, 0, 512, 400]},
                {"type": "text", "box": [20, 420, 472, 72], "value": "Hello"},
            ]
        }
        first = catalog.publish(
            "auto_test",
            {"name": "Test", "min_images": 1, "max_images": 1, "tags": ["happy"]},
            spec,
        )
        second = catalog.publish(
            "auto_test",
            {"name": "Test", "min_images": 1, "max_images": 1, "tags": ["happy"]},
            spec,
        )
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(second["version"], 1)
        third = catalog.publish(
            "auto_test",
            {
                "name": "Test changed",
                "min_images": 1,
                "max_images": 1,
                "tags": ["happy"],
            },
            spec,
        )
        self.assertEqual(third["id"], first["id"])
        self.assertEqual(third["version"], 2)
        with self.assertRaises(ValueError):
            TemplateSpec.model_validate(
                {
                    "layers": [
                        {
                            "type": "asset",
                            "box": [0, 0, 10, 10],
                            "value": "../../passwd",
                        }
                    ]
                }
            )
        with self.assertRaises(ValueError):
            TemplateSpec.model_validate(
                {"layers": [{"type": "subject", "box": [0, 0, 2000, 512]}]}
            )
        with self.assertRaises(ValueError):
            render(spec, [])

    def test_auth_ownership_and_idempotency(self):
        self.app.dependency_overrides.clear()
        self.assertEqual(self.client.get("/recommend/quota").status_code, 401)
        self.app.dependency_overrides[current_user] = lambda: {"id": self.owner}
        asset = self.upload()
        r = self.create(asset)
        self.assertEqual(r.status_code, 202)
        identifier = r.json()["job_id"]
        self.assertEqual(self.create(asset).json()["job_id"], identifier)
        self.assertEqual(self.client.get("/recommend/quota").json()["remaining"], 2)
        self.owner = "b"
        self.assertEqual(
            self.client.get("/recommend/jobs/" + identifier).status_code, 404
        )
        self.assertEqual(self.create(asset).status_code, 404)
        self.owner = "a"
        self.assertEqual(self.create(asset, "different-key").status_code, 409)

    def test_results_quota_feedback_and_delete(self):
        asset = self.upload()
        identifier = self.create(asset).json()["job_id"]
        self.finish()
        result = self.client.get("/recommend/jobs/" + identifier).json()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(result["results"]), 9)
        self.assertEqual(
            self.client.get(
                f"/recommend/jobs/{identifier}/results/0?preview=true"
            ).status_code,
            200,
        )
        event = {"event_id": "event-test-1", "slots": [0, 1]}
        self.assertEqual(
            self.client.post(
                f"/recommend/jobs/{identifier}/selections", json=event
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                f"/recommend/jobs/{identifier}/selections", json=event
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.post(
                f"/recommend/jobs/{identifier}/selections",
                json={"event_id": "event-test-1", "slots": [2]},
            ).status_code,
            409,
        )
        worker.maintenance()
        db = connect()
        self.assertTrue(
            db.execute("SELECT weights FROM preferences WHERE user_id='a'").fetchone()
        )
        db.close()
        self.assertEqual(
            self.client.put(
                "/recommend/preferences", json={"enabled": False}
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.delete("/recommend/jobs/" + identifier).status_code, 204
        )
        self.assertEqual(self.client.get("/recommend/quota").json()["remaining"], 2)
        for i in range(2):
            self.create(self.upload(), "next-key-" + str(i))
            self.finish()
        self.assertEqual(self.create(self.upload(), "over-quota").status_code, 429)

    def test_invalid_upload_and_worker_refund(self):
        self.assertEqual(
            self.client.post(
                "/recommend/assets", files={"file": ("bad.png", b"bad", "image/png")}
            ).status_code,
            422,
        )
        self.assertEqual(self.client.get("/recommend/quota").json()["remaining"], 3)
        identifier = self.create(self.upload()).json()["job_id"]
        job = worker.claim()
        with patch.object(worker, "process", side_effect=RuntimeError("test failure")):
            worker.run_job(job)
        self.assertEqual(
            self.client.get("/recommend/jobs/" + identifier).json()["status"], "failed"
        )
        self.assertEqual(self.client.get("/recommend/quota").json()["remaining"], 3)

    def test_licensed_source_and_opt_out(self):
        from meme_generator.features.ingest import download, run_openmoji

        with patch("meme_generator.features.ingest.subprocess.run") as transport:
            with self.assertRaises(ValueError):
                download("http://127.0.0.1/private", None)
            transport.assert_not_called()
        with patch("meme_generator.features.ingest.download", return_value=self.photo) as fetch:
            first = run_openmoji(limit=1)
            second = run_openmoji(limit=1)
        fetch.assert_not_called()
        self.assertEqual(first["status"], "withdrawn-by-owner")
        self.assertEqual(first["published"], 0)
        self.assertEqual(second["published"], 0)
        identifier = self.create(self.upload()).json()["job_id"]
        self.finish()
        self.client.put("/recommend/preferences", json={"enabled": False})
        self.client.post(
            f"/recommend/jobs/{identifier}/selections",
            json={"event_id": "opt-out-event", "slots": [0]},
        )
        db = connect()
        self.assertEqual(db.execute("SELECT COUNT(*) FROM events").fetchone()[0], 0)
        self.assertEqual(
            db.execute(
                "SELECT selection FROM jobs WHERE id=?", (identifier,)
            ).fetchone()[0],
            "[]",
        )
        db.close()

    def test_reviewed_seed_restore_is_idempotent(self):
        from meme_generator.features.seed import restore

        before = len(catalog.rows())
        self.assertEqual(restore(), 1)
        self.assertEqual(len(catalog.rows()), before + 1)
        self.assertEqual(restore(), 0)

    def test_lease_recovery(self):
        self.create(self.upload())
        worker.claim()
        db = connect()
        with db:
            db.execute("UPDATE jobs SET lease=0")
        db.close()
        self.assertIsNotNone(worker.claim())
        db = connect()
        with db:
            db.execute("UPDATE jobs SET lease=0")
        db.close()
        self.assertIsNone(worker.claim())
        self.assertEqual(self.client.get("/recommend/quota").json()["remaining"], 3)


if __name__ == "__main__":
    unittest.main()
