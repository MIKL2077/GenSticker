import os
import tempfile
import unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from meme_generator.features.catalog import publish
from meme_generator.features.client_render import router, receipt, verify_receipt
from meme_generator.features.popularity import router as stats_router


class ClientRenderTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ, {'GENSTICKER_STATE_DIR': self.directory.name})
        self.env.start()
        self.spec={'width':128,'height':128,'layers':[{'type':'subject','box':[0,0,128,128]}]}
        publish('auto_test', {'name':'sample'}, self.spec)
        app=FastAPI();app.include_router(router);app.include_router(stats_router)
        self.client=TestClient(app)

    def tearDown(self):
        self.env.stop();self.directory.cleanup()

    def test_ticket_identity_version_and_replay(self):
        headers={'X-Gensticker-Visitor':'test-visitor-123456789'}
        data=self.client.get('/memes/auto_test/client-template',headers=headers).json()
        self.assertTrue(data['supported'])
        body={'key':'auto_test','kind':'client_generate','receipt':data['receipt']}
        self.assertTrue(self.client.post('/templates/events',headers=headers,json=body).json()['recorded'])
        self.assertFalse(self.client.post('/templates/events',headers=headers,json=body).json()['recorded'])
        self.assertEqual(self.client.post('/templates/events',headers={'X-Gensticker-Visitor':'different-visitor-12345'},json=body).status_code,422)
        publish('auto_test',{'name':'new-version'},self.spec)
        self.assertEqual(self.client.post('/templates/events',headers=headers,json=body).status_code,422)
        self.assertEqual(self.client.get('/memes/petpet/client-template').json(),{'supported':False})
        self.assertEqual(self.client.get('/template-assets/'+('a'*64)+'.png').status_code,404)

    def test_expired_and_tampered_ticket(self):
        token=receipt('auto_test',1,'guest:one')
        with patch('meme_generator.features.client_render.time.time',return_value=9999999999):
            with self.assertRaises(Exception): verify_receipt(token,'auto_test','guest:one')
        with self.assertRaises(Exception): verify_receipt(token+'x','auto_test','guest:one')


if __name__=='__main__': unittest.main()
