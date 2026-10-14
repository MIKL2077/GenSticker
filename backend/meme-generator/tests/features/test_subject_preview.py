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

    def test_invalid_images_and_busy_preview_do_not_render(self):
        for value in ['???', base64.b64encode(b'not an image').decode()]:
            self.assertEqual(self.client.post('/images/subject', json={'image': value}).status_code, 422)
        too_big = base64.b64encode(b'a' * (4 * 1024 * 1024 + 1)).decode()
        self.assertEqual(self.client.post('/images/subject', json={'image': too_big}).status_code, 413)
        with patch.object(api, 'generation_slots', asyncio.Semaphore(0)):
            response = self.client.post('/images/subject', json={'image': self.encoded})
            self.assertEqual(response.status_code, 503)
        self.assertFalse(api.subject_cache.items)


if __name__ == '__main__':
    unittest.main()
