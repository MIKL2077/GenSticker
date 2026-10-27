from io import BytesIO
import unittest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from meme_generator.features.share import router,COVERS


class ShareTests(unittest.TestCase):
    def setUp(self):
        app=FastAPI();app.include_router(router);self.client=TestClient(app)

    def tearDown(self):self.client.close()

    def test_all_public_covers_load_without_auth_and_are_valid_chat_size(self):
        self.assertEqual(len(COVERS),4)
        for name in COVERS:
            response=self.client.get('/share/'+name)
            self.assertEqual(response.status_code,200,name)
            self.assertEqual(response.headers['content-type'],'image/jpeg')
            self.assertEqual(response.headers['cache-control'],'public, max-age=31536000, immutable')
            self.assertEqual(response.headers['x-content-type-options'],'nosniff')
            self.assertNotIn('set-cookie',response.headers)
            self.assertLess(len(response.content),200*1024)
            with Image.open(BytesIO(response.content)) as image:
                self.assertEqual(image.format,'JPEG');self.assertEqual(image.size,(600,480))

    def test_unknown_names_and_arbitrary_files_are_not_served(self):
        for name in ['cover-v999.jpg','README.md','app.py','%2e%2e%2fapp.py']:
            self.assertEqual(self.client.get('/share/'+name).status_code,404,name)
