import hashlib,os,tempfile,time,unittest
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from meme_generator.features import live_import,livegif
from meme_generator.account import current_user

class LiveImportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.env=patch.dict(os.environ,{'GENSTICKER_STATE_DIR':self.temp.name});self.env.start();self.owner='alice'
        app=FastAPI();app.include_router(live_import.router);app.dependency_overrides[current_user]=lambda:{'id':self.owner};self.client=TestClient(app)
    def tearDown(self):self.client.close();self.env.stop();self.temp.cleanup()
    def pair(self):
        response=self.client.post('/studio/live/imports');self.assertEqual(response.status_code,201,response.text);return response.json()
    def test_capability_one_use_private_and_expires(self):
        pair=self.pair();self.assertEqual(len(pair['token']),64);self.assertEqual(pair['id'],hashlib.sha256(pair['token'].encode()).hexdigest())
        self.assertEqual(self.client.get('/studio/live/imports/'+pair['id']).json()['status'],'waiting')
        db=live_import.db_open();self.assertNotIn(pair['token'],str([dict(r) for r in db.execute('SELECT * FROM live_imports')]));db.close()
        self.owner='bob';self.assertEqual(self.client.get('/studio/live/imports/'+pair['id']).status_code,404);self.assertEqual(self.client.get('/studio/live/imports/'+pair['id']+'/media').status_code,404)
        self.assertEqual(self.client.post('/studio/live/imports/receive',content=b'fake').status_code,401)
        asset={'asset_id':'a'*32,'duration':3,'width':480,'height':640}
        with patch.object(livegif,'prepare',return_value=asset) as prepare:
            sent=self.client.post('/studio/live/imports/receive',content=b'motion',headers={'X-Live-Import':pair['token']});self.assertEqual(sent.status_code,201,sent.text);prepare.assert_called_once_with(b'motion','alice')
            self.assertEqual(self.client.post('/studio/live/imports/receive',content=b'motion',headers={'X-Live-Import':pair['token']}).status_code,409)
        self.owner='alice'
        with patch.object(livegif,'own',return_value=asset):self.assertEqual(self.client.get('/studio/live/imports/'+pair['id']).json()['asset']['asset_id'],asset['asset_id'])
        db=live_import.db_open()
        with db:db.execute('UPDATE live_imports SET created=?',(time.time()-601,))
        db.close();self.assertEqual(self.client.get('/studio/live/imports/'+pair['id']).status_code,410)
    def test_size_invalid_media_and_creation_budget(self):
        pair=self.pair();headers={'X-Live-Import':pair['token']}
        self.assertEqual(self.client.post('/studio/live/imports/receive',content=b'x'*(8*1024*1024+1),headers=headers).status_code,413)
        self.assertEqual(self.client.get('/studio/live/imports/'+pair['id']).json()['status'],'waiting')
        from fastapi import HTTPException
        with patch.object(livegif,'prepare',side_effect=HTTPException(422,'invalid media')):self.assertEqual(self.client.post('/studio/live/imports/receive',content=b'static',headers=headers).status_code,422)
        self.assertEqual(self.client.get('/studio/live/imports/'+pair['id']).json()['status'],'waiting')
        for _ in range(3):self.pair()
        self.assertEqual(self.client.post('/studio/live/imports').status_code,429)
        self.owner='bob';self.pair()
