import base64
from io import BytesIO
import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from meme_generator import account
from meme_generator.safe_images import open_image
from meme_generator.features import studio, lifecycle, storage, catalog


class RemediationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(
            os.environ,
            {"GENSTICKER_STATE_DIR": self.temp.name, "GENSTICKER_MIN_FREE_BYTES": "1"},
        )
        self.env.start()
        db = account.connection()
        with db:
            db.executemany(
                "INSERT INTO users(id,openid,name) VALUES(?,?,?)",
                [("alice", "a", "Alice"), ("bob", "b", "Bob")],
            )
        db.close()
        studio.init().close()
        app = FastAPI()
        app.include_router(studio.router)
        app.include_router(lifecycle.router)
        self.who = "alice"
        app.dependency_overrides[account.current_user] = lambda: {"id": self.who}
        self.client = TestClient(app)
        self.spec = {
            "width": 128,
            "height": 128,
            "layers": [
                {
                    "type": "text",
                    "box": [0, 0, 128, 128],
                    "value": "hello",
                    "font_size": 12,
                }
            ],
        }

    def tearDown(self):
        self.client.close()
        self.env.stop()
        self.temp.cleanup()
        catalog.refresh()

    def create(self, **kwargs):
        response = self.client.post(
            "/studio/templates", json={"name": "hello", "spec": self.spec, **kwargs}
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def photo(self):
        output = BytesIO()
        Image.new("RGB", (64, 64), "white").save(output, "PNG")
        return base64.b64encode(output.getvalue()).decode()

    def test_required_image_decoders_only_and_frame_limit(self):
        for fmt in ("PNG", "JPEG", "GIF", "WEBP"):
            out = BytesIO()
            Image.new("RGB", (40, 40)).save(out, fmt)
            with open_image(BytesIO(out.getvalue())) as result:
                self.assertEqual(result.size, (40, 40))
        from meme_generator.safe_images import open_input_image

        frames = [
            Image.new("RGB", (12, 12), (i % 256, (i * 7) % 256, 0)) for i in range(121)
        ]
        animated = BytesIO()
        frames[0].save(
            animated, "GIF", save_all=True, append_images=frames[1:], duration=20
        )
        with self.assertRaises(ValueError):
            open_input_image(BytesIO(animated.getvalue()))
        out = BytesIO()
        Image.new("RGB", (40, 40)).save(out, "TIFF")
        with self.assertRaises(OSError):
            open_image(BytesIO(out.getvalue()))
        self.assertEqual(
            self.client.post(
                "/studio/templates/ai",
                json={
                    "image": base64.b64encode(out.getvalue()).decode(),
                    "rights_attested": True,
                    "idempotency_key": "reject-tiff",
                },
            ).status_code,
            422,
        )

    def test_storage_budget_includes_legacy_and_preserves_reads(self):
        old = storage.root() / "private" / "alice"
        old.mkdir(parents=True)
        (old / "legacy.bin").write_bytes(b"x" * 4000)
        with patch.dict(os.environ, {"GENSTICKER_USER_STORAGE_BYTES": "3000"}):
            self.assertEqual(
                self.client.post(
                    "/studio/templates", json={"name": "new", "spec": self.spec}
                ).status_code,
                413,
            )
            self.assertEqual(
                self.client.get("/account/storage").json()["used_bytes"], 4000
            )
            self.assertEqual(self.client.get("/studio/templates").status_code, 200)
        with patch.dict(os.environ, {"GENSTICKER_MIN_FREE_BYTES": str(10**20)}):
            self.assertEqual(
                self.client.post(
                    "/studio/templates", json={"name": "new", "spec": self.spec}
                ).status_code,
                507,
            )

    def test_template_count_limit_and_other_owner(self):
        item = self.create()
        with patch.dict(os.environ, {"GENSTICKER_USER_TEMPLATE_LIMIT": "1"}):
            self.assertEqual(
                self.client.post(
                    "/studio/templates", json={"name": "next", "spec": self.spec}
                ).status_code,
                409,
            )
        self.who = "bob"
        self.assertEqual(
            self.client.delete("/studio/templates/" + item["id"]).status_code, 404
        )
        self.who = "alice"
        self.assertEqual(
            self.client.delete("/studio/templates/" + item["id"]).status_code, 204
        )
        self.assertEqual(self.client.get("/studio/templates").json(), [])

    def test_withdraw_unloads_catalog_in_same_process(self):
        item = self.create()
        with patch.object(studio, "moderate", return_value=("published", "pass")):
            studio.publish_owned(item["id"], {"id": "alice"})
        catalog.refresh()
        from meme_generator.manager import get_meme_keys

        self.assertIn(item["id"], get_meme_keys())
        self.assertEqual(
            self.client.post(
                "/studio/templates/" + item["id"] + "/withdraw"
            ).status_code,
            200,
        )
        self.assertNotIn(item["id"], get_meme_keys())
        self.assertEqual(
            self.client.get("/studio/templates/" + item["id"]).json()["status"],
            "private",
        )

    def test_failed_ai_refunds_success_quota_but_limits_attempts(self):
        for attempt in range(3):
            response = self.client.post(
                "/studio/templates/ai",
                json={
                    "image": self.photo(),
                    "rights_attested": True,
                    "idempotency_key": f"ai-attempt-{attempt}",
                },
            )
            self.assertEqual(response.status_code, 201, response.text)
            with patch(
                "meme_generator.features.quality.convert_caption",
                side_effect=ValueError("uncertain"),
            ):
                studio.work_one()
            self.assertEqual(self.client.get("/studio/quota").json()["remaining"], 1)
        self.assertEqual(
            self.client.post(
                "/studio/templates/ai",
                json={
                    "image": self.photo(),
                    "rights_attested": True,
                    "idempotency_key": "ai-attempt-next",
                },
            ).status_code,
            429,
        )

    def test_daily_ingress_cannot_be_reset_by_deleting_files(self):
        with patch.dict(os.environ, {"GENSTICKER_DAILY_UPLOAD_BYTES": "100"}):
            with storage.write_guard("alice", 10, ingress=90):
                pass
            with self.assertRaises(Exception) as error:
                with storage.write_guard("alice", 10, ingress=11):
                    pass
            self.assertEqual(error.exception.status_code, 429)

    def test_delete_account_is_explicit_cleans_only_owner_and_denies_late_writes(self):
        self.create()
        self.who = "bob"
        other = self.create()
        self.who = "alice"
        directory = storage.root() / "private" / "alice"
        directory.mkdir(parents=True)
        (directory / "old.png").write_bytes(b"data")
        self.assertEqual(
            self.client.request(
                "DELETE", "/account", json={"confirmation": "no"}
            ).status_code,
            422,
        )
        response = self.client.request(
            "DELETE", "/account", json={"confirmation": "注销账号"}
        )
        self.assertEqual(response.status_code, 204, response.text)
        self.assertFalse(directory.exists())
        db = account.connection()
        self.assertIsNone(db.execute("SELECT 1 FROM users WHERE id='alice'").fetchone())
        self.assertIsNotNone(
            db.execute("SELECT 1 FROM users WHERE id='bob'").fetchone()
        )
        db.close()
        self.assertEqual(
            self.client.post(
                "/studio/templates", json={"name": "late", "spec": self.spec}
            ).status_code,
            401,
        )
        self.who = "bob"
        self.assertEqual(
            self.client.get("/studio/templates/" + other["id"]).status_code, 200
        )

    def test_account_delete_refuses_active_tasks_and_video_ownership(self):
        studio.enqueue(
            "manual",
            {"template_key": "always", "images": []},
            "pending-task",
            {"id": "alice"},
        )
        self.assertEqual(
            self.client.request(
                "DELETE", "/account", json={"confirmation": "注销账号"}
            ).status_code,
            409,
        )
        from meme_generator.features.livegif import directory

        key = "a" * 32
        (directory() / (key + ".json")).write_text(
            json.dumps({"user_id": "bob", "created": time.time(), "duration": 3})
        )
        (directory() / (key + ".media")).write_bytes(b"video")
        self.assertEqual(
            self.client.delete("/studio/live/assets/" + key).status_code, 404
        )

    def test_orphans_keep_shared_and_version_references(self):
        root = storage.root() / "template_assets"
        root.mkdir()
        orphan = root / ("c" * 64 + ".png")
        orphan.write_bytes(b"old")
        os.utime(orphan, (0, 0))
        self.assertEqual(storage.collect_orphans(), 1)
        self.assertFalse(orphan.exists())

    def test_wechat_export_preserves_animation_duration_and_bounds(self):
        from meme_generator.features.export import adapt

        out = BytesIO()
        frames = [
            Image.new("RGB", (400, 260), color) for color in ("red", "green", "blue")
        ]
        frames[0].save(
            out,
            "GIF",
            save_all=True,
            append_images=frames[1:],
            duration=[100, 200, 300],
            loop=0,
        )
        raw, mime = adapt(out.getvalue())
        self.assertEqual(mime, "image/gif")
        self.assertLessEqual(len(raw), 500 * 1024)
        with Image.open(BytesIO(raw)) as result:
            self.assertLessEqual(max(result.size), 240)
            self.assertGreater(result.n_frames, 1)
            from PIL import ImageSequence

            self.assertEqual(
                sum(f.info["duration"] for f in ImageSequence.Iterator(result)), 600
            )

    def test_traffic_budget_blocks_new_work_but_keeps_reads(self):
        from meme_generator.features.traffic import TrafficBudget, record_bytes
        from fastapi import FastAPI

        app = FastAPI()
        app.add_middleware(TrafficBudget)

        @app.post("/images/subject")
        def new_work():
            return {"ok": True}

        @app.get("/existing-result")
        def existing():
            return {"ok": True}

        @app.get("/healthz")
        def health():
            return {"status": "ok"}

        @app.delete("/account")
        def deletion():
            return {"deleted": True}

        with patch.dict(os.environ, {"GENSTICKER_API_MONTHLY_BYTES": "100"}):
            record_bytes(86)
            with TestClient(app) as client:
                self.assertEqual(client.post("/images/subject").status_code, 503)
                self.assertEqual(client.get("/existing-result").status_code, 200)
                record_bytes(100)
                self.assertEqual(client.get("/existing-result").status_code, 503)
                self.assertEqual(client.get("/healthz").status_code, 200)
                self.assertEqual(client.delete("/account").status_code, 200)

    def test_low_confidence_ocr_is_private_until_saved_preview_and_explicit_review(
        self,
    ):
        from PIL import ImageDraw
        from meme_generator.features.declarative import font

        image = Image.new("RGB", (512, 512), "white")
        ImageDraw.Draw(image).text((24, 22), "why", font=font(32), fill="black")
        out = BytesIO()
        image.save(out, "PNG")
        response = self.client.post(
            "/studio/templates/ai",
            json={
                "image": base64.b64encode(out.getvalue()).decode(),
                "rights_attested": True,
                "idempotency_key": "draft-review-case",
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        recognized = [([[20, 18], [120, 18], [120, 64], [20, 64]], "why", 0.88)]
        with (
            patch("meme_generator.features.quality.recognize", return_value=recognized),
            patch.object(studio, "moderate") as moderation,
        ):
            studio.work_one()
            moderation.assert_not_called()
        job = self.client.get("/studio/jobs/" + response.json()["id"]).json()
        self.assertEqual(job["status"], "completed", job)
        item = self.client.get("/studio/templates/" + job["template_id"]).json()
        self.assertTrue(item["requires_review"])
        self.assertEqual(item["status"], "private")
        self.assertEqual(
            self.client.post(
                "/studio/templates/" + item["id"] + "/publish",
                json={"rights_attested": True},
            ).status_code,
            409,
        )
        route = "/studio/templates/" + item["id"] + "/captions"
        self.assertEqual(
            self.client.patch(
                route,
                json={"texts": ["new"], "confirmed": True, "rights_attested": True},
            ).status_code,
            409,
        )
        saved = self.client.patch(route, json={"texts": ["new"]})
        self.assertEqual(saved.status_code, 200, saved.text)
        digest = saved.json()["review_digest"]
        self.assertTrue(digest)
        self.assertEqual(
            self.client.patch(
                route,
                json={
                    "texts": ["changed"],
                    "confirmed": True,
                    "rights_attested": True,
                    "preview_digest": digest,
                },
            ).status_code,
            409,
        )
        confirmed = self.client.patch(
            route,
            json={
                "texts": ["new"],
                "confirmed": True,
                "rights_attested": True,
                "preview_digest": digest,
            },
        )
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        self.assertFalse(confirmed.json()["requires_review"])
        self.assertEqual(confirmed.json()["status"], "pending")
        db = studio.init()
        self.assertEqual(db.execute("SELECT count(*) FROM templates").fetchone()[0], 0)
        db.close()
        with patch.object(
            studio, "moderate", return_value=("pending", "not connected")
        ):
            studio.work_one()
        db = studio.init()
        self.assertEqual(db.execute("SELECT count(*) FROM templates").fetchone()[0], 0)
        db.close()

    def test_shared_private_artwork_survives_one_owner_deletion(self):
        spec = {
            **self.spec,
            "layers": [{"type": "asset", "box": [0, 0, 128, 128], "value": "0" * 64}],
        }
        first = self.create(spec=spec, background_image=self.photo())
        self.who = "bob"
        second = self.create(spec=spec, background_image=self.photo())
        self.who = "alice"
        digest = first["spec"]["layers"][0]["value"]
        path = storage.root() / "template_assets" / (digest + ".png")
        os.utime(path, (0, 0))
        self.assertEqual(
            self.client.delete("/studio/templates/" + first["id"]).status_code, 204
        )
        self.assertTrue(path.exists())
        self.who = "bob"
        self.assertEqual(self.client.get(second["preview_url"]).status_code, 200)
        self.assertEqual(
            self.client.delete("/studio/templates/" + second["id"]).status_code, 204
        )
        self.assertFalse(path.exists())

    def test_account_recreation_does_not_reset_daily_ingress_identity(self):
        with patch.dict(os.environ, {"GENSTICKER_DAILY_UPLOAD_BYTES": "100"}):
            with storage.write_guard("alice", 1, ingress=90):
                pass
            self.assertEqual(
                self.client.request(
                    "DELETE", "/account", json={"confirmation": "注销账号"}
                ).status_code,
                204,
            )
            db = account.connection()
            with db:
                db.execute(
                    "INSERT INTO users(id,openid,name) VALUES('new-alice','a','Alice')"
                )
            db.close()
            with self.assertRaises(Exception) as error:
                with storage.write_guard("new-alice", 1, ingress=11):
                    pass
            self.assertEqual(error.exception.status_code, 429)

    def test_heavy_admission_precedes_body_parsing_and_keeps_health_available(self):
        import asyncio
        import httpx
        from meme_generator.features.traffic import TrafficBudget

        async def exercise():
            app = FastAPI()
            app.add_middleware(TrafficBudget)
            release = asyncio.Event()
            started = asyncio.Event()
            count = 0

            @app.post("/images/subject")
            async def heavy():
                nonlocal count
                count += 1
                if count == 2:
                    started.set()
                await release.wait()
                return {"ok": True}

            @app.get("/healthz")
            async def health():
                return {"ok": True}

            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client:
                first = asyncio.create_task(client.post("/images/subject"))
                second = asyncio.create_task(client.post("/images/subject"))
                await asyncio.wait_for(started.wait(), 3)
                try:
                    rejected = await client.post(
                        "/images/subject", content=b"invalid body"
                    )
                    self.assertEqual(rejected.status_code, 503)
                    self.assertEqual((await client.get("/healthz")).status_code, 200)
                finally:
                    release.set()
                self.assertEqual(
                    [x.status_code for x in await asyncio.gather(first, second)],
                    [200, 200],
                )

        asyncio.run(exercise())

    def test_small_media_and_job_counts_are_bounded_independent_of_bytes(self):
        from meme_generator.features.livegif import directory

        key = "d" * 32
        (directory() / (key + ".json")).write_text(
            json.dumps({"user_id": "alice", "created": time.time(), "duration": 1})
        )
        (directory() / (key + ".media")).write_bytes(b"tiny")
        with patch.dict(os.environ, {"GENSTICKER_USER_MEDIA_LIMIT": "1"}):
            with self.assertRaises(Exception) as error:
                with storage.write_guard("alice", 1, media=True):
                    pass
            self.assertEqual(error.exception.status_code, 409)
        studio.enqueue(
            "manual",
            {"template_key": "always", "images": []},
            "count-bound-job",
            {"id": "alice"},
        )
        with patch.dict(os.environ, {"GENSTICKER_USER_JOB_LIMIT": "1"}):
            with self.assertRaises(Exception) as error:
                studio.enqueue(
                    "manual",
                    {"template_key": "always", "images": []},
                    "another-count-job",
                    {"id": "alice"},
                )
            self.assertEqual(error.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()
