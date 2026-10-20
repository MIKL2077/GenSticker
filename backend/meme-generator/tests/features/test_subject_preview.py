import asyncio
import base64
import importlib
import unittest
from io import BytesIO
from unittest.mock import patch
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

api = importlib.import_module('meme_generator.app')


class SubjectPreviewTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(api.app)
        api.subject_cache.items.clear()
        api.subject_cache.bytes = 0
        image = Image.new('RGBA', (100, 100))
        ImageDraw.Draw(image).ellipse((20, 10, 80, 90), fill='red')
        buf = BytesIO()
        image.save(buf, 'PNG')
        self.encoded = base64.b64encode(buf.getvalue()).decode()

    def tearDown(self):
        self.client.close()
        api.subject_cache.items.clear()
        api.subject_cache.bytes = 0

    def test_private_transparent_preview_and_visitor_isolation(self):
        with patch('meme_generator.features.vision.warmup') as model:
            for visitor in ['preview-user-12345678', 'preview-user-12345678', 'preview-user-87654321']:
                response = self.client.post('/images/subject', json={'image': self.encoded}, headers={'X-Gensticker-Visitor': visitor})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers['cache-control'], 'private, no-store')
                self.assertEqual(response.headers['content-type'], 'image/png')
                image = Image.open(BytesIO(response.content))
                self.assertEqual(image.mode, 'RGBA')
                self.assertLess(image.width, 100)
                self.assertLess(image.getextrema()[3][0], 255)
            model.assert_not_called()
        self.assertEqual(len(api.subject_cache.items), 2)

    def test_url_delivery_download_stays_private_and_expires(self):
        from meme_generator.features import editor
        visitor={'X-Gensticker-Visitor':'foreground-owner-123456'}
        response=self.client.post('/images/subject',json={'image':self.encoded,'delivery':'url'},headers=visitor)
        self.assertEqual(response.status_code,200,response.text)
        path=response.json()['image_url']
        image=self.client.get(path,headers=visitor)
        self.assertEqual(image.status_code,200)
        self.assertEqual(image.headers['cache-control'],'private, no-store')
        self.assertEqual(self.client.get(path,headers={'X-Gensticker-Visitor':'foreground-stranger-1234'}).status_code,404)
        with patch.object(editor.time,'time',return_value=10**12):
            self.assertEqual(self.client.get(path,headers=visitor).status_code,404)
        editor._foreground.clear()

    def test_cached_subject_is_available_when_generation_slots_are_busy(self):
        visitor={'X-Gensticker-Visitor':'cached-preview-12345678'}
        first=self.client.post('/images/subject',json={'image':self.encoded},headers=visitor)
        self.assertEqual(first.status_code,200)
        self.assertEqual(first.headers['x-gensticker-cache'],'miss')
        with patch.object(api,'generation_slots',asyncio.Semaphore(0)):
            second=self.client.post('/images/subject',json={'image':self.encoded},headers=visitor)
        self.assertEqual(second.status_code,200)
        self.assertEqual(second.headers['x-gensticker-cache'],'hit')
        self.assertEqual(second.content,first.content)

    def test_parallel_identical_inputs_share_one_inference(self):
        import threading,time
        from concurrent.futures import ThreadPoolExecutor
        calls=[];barrier=threading.Barrier(2)
        def extract(raw):
            calls.append(raw);time.sleep(.04);return b'foreground'
        def prepare():
            barrier.wait();return api.prepare_inputs([b'same-photo'],'same-owner')
        with patch('meme_generator.features.subjects.extract_subject',side_effect=extract):
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures=[pool.submit(prepare) for _ in range(2)]
                self.assertEqual([f.result() for f in futures],[[b'foreground'],[b'foreground']])
        self.assertEqual(len(calls),1)

    def test_invalid_images_and_busy_preview_do_not_render(self):
        for value in ['???', base64.b64encode(b'not an image').decode()]:
            self.assertEqual(self.client.post('/images/subject', json={'image': value}).status_code, 422)
        too_big = base64.b64encode(b'a' * (8 * 1024 * 1024 + 1)).decode()
        self.assertEqual(self.client.post('/images/subject', json={'image': too_big}).status_code, 413)
        with patch.object(api, 'generation_slots', asyncio.Semaphore(0)):
            response = self.client.post('/images/subject', json={'image': self.encoded})
            self.assertEqual(response.status_code, 503)
        self.assertFalse(api.subject_cache.items)


if __name__ == '__main__':
    unittest.main()
