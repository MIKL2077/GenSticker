import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from meme_generator import account


class Provider:
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass
    async def get(self, url, params):
        class Result:
            def raise_for_status(self): pass
            def json(self): return {'openid': params['js_code'], 'session_key': 'must-not-leak'}
        return Result()


class AccountTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.environment = patch.dict(os.environ, {'GENSTICKER_STATE_DIR': self.directory.name, 'WX_APPID': 'test', 'WX_APP_SECRET': 'test'})
        self.environment.start()
        self.provider = patch.object(account.httpx, 'AsyncClient', side_effect=lambda **kwargs: Provider())
        self.provider.start()
        app = FastAPI()
        app.include_router(account.router)
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.provider.stop()
        self.environment.stop()
        self.directory.cleanup()

    def login(self, code):
        result = self.client.post('/auth/wechat', json={'code': code})
        self.assertEqual(result.status_code, 200)
        self.assertNotIn('openid', result.text)
        self.assertNotIn('must-not-leak', result.text)
        return {'Authorization': 'Bearer ' + result.json()['access_token']}

    def test_profile_validation_and_isolation(self):
        import base64
        from io import BytesIO
        from PIL import Image
        a, b = self.login('a'), self.login('b')
        output = BytesIO()
        Image.new('RGB', (512, 512), 'red').save(output, 'PNG')
        result = self.client.put('/account/profile', headers=a, json={'name': '小红', 'avatar': base64.b64encode(output.getvalue()).decode()})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()['name'], '小红')
        image = Image.open(BytesIO(base64.b64decode(result.json()['avatar'])))
        self.assertEqual(image.size, (128, 128))
        self.assertEqual(self.client.get('/auth/me', headers=b).json()['name'], '微信用户')
        self.assertEqual(self.client.put('/account/profile', headers=a, json={'name': ' ', 'avatar': 'abc'}).status_code, 422)
        self.assertEqual(self.client.put('/account/profile', headers=a, json={'name': '小红', 'avatar': 'abc'}).status_code, 422)
        self.assertEqual(self.client.get('/auth/me', headers=a).json()['name'], '小红')

    def test_missing_config_and_auth(self):
        self.assertEqual(self.client.get('/account/library').status_code, 401)
        with patch.dict(os.environ, {'WX_APP_SECRET': ''}):
            self.assertFalse(self.client.get('/account/config').json()['login_enabled'])
            self.assertEqual(self.client.post('/auth/wechat', json={'code': 'x'}).status_code, 503)

    def test_user_isolation_idempotence_and_merge(self):
        a, b = self.login('a'), self.login('b')
        for _ in range(2):
            self.assertEqual(self.client.put('/account/favorites/petpet', headers=a).status_code, 200)
            self.assertEqual(self.client.put('/account/history/petpet', headers=a).status_code, 200)
        own = self.client.get('/account/library', headers=a).json()
        self.assertEqual(own['favorite_keys'], ['petpet'])
        self.assertEqual(len(own['history']), 1)
        self.assertEqual(self.client.get('/account/library', headers=b).json(), {'favorite_keys': [], 'history': []})
        merged = self.client.post('/account/library/merge', headers=a, json={'favorite_keys': ['petpet', 'missing'], 'history': [{'key': '5000choyen', 'visited_at': 999999999999999}]}).json()
        self.assertLessEqual(merged['history'][0]['visited_at'], account.now_ms())
        self.assertEqual(self.client.delete('/account/favorites/petpet', headers=b).status_code, 204)
        self.assertEqual(self.client.get('/account/library', headers=a).json()['favorite_keys'], ['petpet'])
        self.assertEqual(self.client.put('/account/favorites/missing', headers=a).status_code, 404)

    def test_expiry_and_revocation(self):
        a, b = self.login('a'), self.login('b')
        self.assertEqual(self.client.delete('/auth/session', headers=a).status_code, 204)
        self.assertEqual(self.client.get('/auth/me', headers=a).status_code, 401)
        self.assertEqual(self.client.get('/auth/me', headers=b).status_code, 200)
        db = account.connection()
        with db: db.execute('UPDATE sessions SET expires=0')
        db.close()
        self.assertEqual(self.client.get('/auth/me', headers=b).status_code, 401)

    def test_limits_and_clear(self):
        a = self.login('a')
        keys = account.get_meme_keys()[:101]
        for key in keys[:100]:
            self.assertEqual(self.client.put('/account/favorites/' + key, headers=a).status_code, 200)
        self.assertEqual(self.client.put('/account/favorites/' + keys[100], headers=a).status_code, 409)
        for key in keys:
            self.client.put('/account/history/' + key, headers=a)
        self.assertEqual(len(self.client.get('/account/library', headers=a).json()['history']), 100)
        self.assertEqual(self.client.delete('/account/history', headers=a).status_code, 204)
        self.assertEqual(self.client.get('/account/library', headers=a).json()['history'], [])


if __name__ == '__main__': unittest.main()
