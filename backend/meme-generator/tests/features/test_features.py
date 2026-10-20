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
        self.limits = patch.multiple(recommend, USER_LIMIT=3, GLOBAL_LIMIT=100)
        self.limits.start()
        self.addCleanup(self.limits.stop)
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
                "processor_version": worker.PROCESSOR_VERSION,
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

    def test_source_metadata_stays_in_details_without_changing_generated_canvas(self):
        import json
        source = 'https://example.test/' + 'long-source-path/' * 30
        metadata = {'name':'Source fixture','tags':[], 'min_images':1,'max_images':1,
                    'origin':'chinesebqb','author':'Source author','license':'unverified','source_url':source}
        spec = {'width':120,'height':80,'layers':[{'type':'subject','box':[0,0,120,80]}]}
        row = catalog.publish('auto_source_footer_fixture', metadata, spec)
        catalog.refresh()
        from meme_generator.manager import get_meme
        manual = get_meme(row['key'])(images=[self.photo],texts=[])
        with Image.open(manual) as image:
            self.assertEqual(image.size,(120,80))
        self.assertEqual(json.loads(next(r for r in catalog.rows() if r['key']==row['key'])['metadata']).get('source_url'),source)
        asset = self.upload()
        identifier = self.create(asset,'source-footer-regression').json()['job_id']
        with patch.object(worker,'candidates',return_value=[row]):
            self.finish()
        result = self.client.get('/recommend/jobs/'+identifier).json()
        self.assertEqual(result['status'],'completed',result)
        item = result['results'][0]
        self.assertEqual(item['attribution']['source_url'],source)
        for field in ('image_url','preview_url'):
            response = self.client.get(item[field])
            self.assertEqual(response.status_code,200)
            with Image.open(BytesIO(response.content)) as image:
                self.assertEqual(image.size,(120,80))

    def test_history_source_preview_is_private_survives_day_one_and_is_cleaned_with_job(self):
        from meme_generator.features.store import root
        asset=self.upload();response=self.create(asset,'history-preview-check');self.assertEqual(response.status_code,202,response.text)
        identifier=response.json()['job_id'];self.finish()
        history=self.client.get('/recommend/jobs').json();url=history[0]['source_preview_url']
        self.assertEqual(self.client.get(url).status_code,200)
        self.owner='stranger';self.assertEqual(self.client.get(url).status_code,404);self.owner='a'
        db=connect()
        with db:db.execute('UPDATE assets SET created=0')
        db.close();worker.maintenance()
        self.assertEqual(self.client.get(url).status_code,200,'seven-day thumbnail survives 24-hour original cleanup')
        db=connect()
        with db:db.execute('UPDATE jobs SET created=0')
        db.close();worker.maintenance()
        self.assertEqual(self.client.get(url).status_code,404)
        self.assertFalse((root()/'history_thumbs'/(asset+'.jpg')).exists())

    def test_unlimited_preserves_queue_and_ownership(self):
        with patch.multiple(recommend, USER_LIMIT=0, GLOBAL_LIMIT=0):
            asset = self.upload()
            for index in range(5):
                response = self.create(asset, f"unlimited-{index}")
                self.assertEqual(response.status_code, 202, response.text)
                if index == 0:
                    self.assertEqual(self.create(asset, "parallel-task").status_code, 409)
                self.finish()
            quota = self.client.get("/recommend/quota").json()
            self.assertTrue(quota["unlimited"])
            self.assertIsNone(quota["remaining"])
            self.assertFalse(quota["paid_ai_enabled"])

    def test_optional_budgets_are_independent_and_queue_stays_bounded(self):
        asset = self.upload()
        with patch.multiple(recommend, USER_LIMIT=0, GLOBAL_LIMIT=1):
            self.assertEqual(self.create(asset, "global-budget").status_code, 202)
            self.finish()
            self.assertEqual(self.create(asset, "global-exhausted").status_code, 429)
        with patch.multiple(recommend, USER_LIMIT=1, GLOBAL_LIMIT=0):
            self.assertEqual(self.create(asset, "personal-exhausted").status_code, 429)
        with patch.multiple(recommend, USER_LIMIT=0, GLOBAL_LIMIT=0):
            import time
            db = connect()
            with db:
                for index in range(10):
                    db.execute("INSERT INTO jobs(id,user_id,idempotency,asset_id,day,status,created,updated) VALUES(?,?,?,?,?,?,?,?)", (f"busy-{index}", f"other-{index}", f"queue-{index}", asset, recommend.day(), "queued", time.time(), time.time()))
            db.close()
            self.assertEqual(self.create(asset, "queue-is-full").status_code, 503)

    def test_reroll_uses_other_templates_and_cached_analysis(self):
        with patch.multiple(recommend, USER_LIMIT=0, GLOBAL_LIMIT=0):
            asset = self.upload()
            first = self.create(asset).json()["job_id"]
            self.finish()
            first_keys = {r["key"] for r in self.client.get(f"/recommend/jobs/{first}").json()["results"]}
            payload = {"previous_job_id": first, "idempotency_key": "reroll-second"}
            self.owner = "b"
            self.assertEqual(self.client.post("/recommend/jobs", json=payload).status_code, 404)
            self.owner = "a"
            second = self.client.post("/recommend/jobs", json=payload)
            self.assertEqual(second.status_code, 202, second.text)
            identifier = second.json()["job_id"]
            self.assertEqual(self.client.post("/recommend/jobs", json=payload).json()["job_id"], identifier)
            job = worker.claim()
            with patch.object(worker, "process", side_effect=AssertionError("analysis should be cached")):
                worker.run_job(job)
            result = self.client.get(f"/recommend/jobs/{identifier}").json()
            self.assertEqual(result["status"], "completed", result)
            second_keys = {r["key"] for r in result["results"]}
            self.assertTrue(second_keys)
            self.assertTrue(first_keys.isdisjoint(second_keys), (first_keys, second_keys))
            self.assertEqual(self.client.get(f"/recommend/jobs/{first}").status_code, 200)
            payload["previous_job_id"] = identifier
            self.assertEqual(self.client.post("/recommend/jobs", json=payload).status_code, 409)
            payload["idempotency_key"] = "reroll-third"
            third = self.client.post("/recommend/jobs", json=payload).json()["job_id"]
            self.finish()
            third_keys = {r["key"] for r in self.client.get(f"/recommend/jobs/{third}").json()["results"]}
            self.assertTrue(third_keys)
            self.assertTrue(second_keys.isdisjoint(third_keys))
            self.assertEqual(self.client.delete(f"/recommend/jobs/{first}").status_code, 204)
            db = connect()
            self.assertTrue(db.execute("SELECT 1 FROM assets WHERE id=?", (asset,)).fetchone())
            with db:
                db.execute("UPDATE assets SET created=0 WHERE id=?", (asset,))
            db.close()
            self.assertEqual(self.client.post("/recommend/jobs", json={"previous_job_id": third, "idempotency_key": "expired-photo"}).status_code, 404)

    def test_repeated_new_jobs_rotate_full_batches_and_replace_failed_templates(self):
        with patch.multiple(recommend, USER_LIMIT=0, GLOBAL_LIMIT=0):
            asset=self.upload();batches=[]
            for index in range(4):
                response=self.create(asset,f'fresh-batch-{index}')
                self.assertEqual(response.status_code,202,response.text)
                identifier=self.finish()
                result=self.client.get(f'/recommend/jobs/{identifier}').json()
                keys={r['key'] for r in result['results']}
                self.assertEqual(len(keys),9,result)
                if batches:self.assertTrue(keys.isdisjoint(batches[-1]),(keys,batches[-1]))
                batches.append(keys)
            self.assertGreaterEqual(len(set.union(*batches[:3])),24)
            # At least nine successful alternatives survive several broken renderers.
            job_id=self.create(asset,'failed-template-replacements').json()['job_id']
            job=worker.claim();ordered=worker.candidates(job,{'expression':'general','confidence':0})
            broken={r['key'] for r in ordered[:4]}
            real=worker.get_meme
            def get_meme(key):
                if key in broken:raise ValueError('broken template fixture')
                return real(key)
            with patch.object(worker,'get_meme',side_effect=get_meme):worker.run_job(job)
            result=self.client.get(f'/recommend/jobs/{job_id}').json()
            self.assertEqual(len(result['results']),9,result)
            self.assertTrue(broken.isdisjoint({r['key'] for r in result['results']}))

    def test_rolling_guard_survives_deletion_and_retries_and_recovers(self):
        import time
        with patch.multiple(recommend, USER_LIMIT=0, GLOBAL_LIMIT=0):
            asset=self.upload()
            first=self.create(asset,'guard-idempotent').json()['job_id'];self.finish()
            db=connect();stamp=time.time()
            with db:
                for i in range(7):db.execute('INSERT INTO generation_admissions VALUES(?,?,?)',(f'guard-{i}',self.owner,stamp))
            db.close()
            self.assertEqual(self.create(asset,'guard-idempotent').json()['job_id'],first)
            # Deleting a completed job does not refund the rolling abuse budget.
            self.assertEqual(self.client.delete('/recommend/jobs/'+first).status_code,204)
            asset=self.upload()
            limited=self.create(asset,'guard-blocked')
            self.assertEqual(limited.status_code,429,limited.text);self.assertGreater(int(limited.headers['retry-after']),0)
            db=connect()
            with db:db.execute('UPDATE generation_admissions SET created=?',(stamp-61,))
            db.close();self.assertEqual(self.create(asset,'guard-recovered').status_code,202)
            self.finish()
            db=connect()
            with db:
                db.execute('DELETE FROM generation_admissions')
                for i in range(80):db.execute('INSERT INTO generation_admissions VALUES(?,?,?)',(f'hour-{i}',self.owner,stamp-120))
            db.close();self.assertEqual(self.create(asset,'hour-blocked').status_code,429)

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
        self.assertEqual(restore(include_batches=False), 1)
        self.assertEqual(len(catalog.rows()), before + 1)
        self.assertEqual(restore(include_batches=False), 0)

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
