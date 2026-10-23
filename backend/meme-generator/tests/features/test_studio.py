import base64
from io import BytesIO
import json
import os
import tempfile
import time
import unittest
from unittest.mock import patch
from PIL import Image
from fastapi import FastAPI
from fastapi.testclient import TestClient
from meme_generator.features import studio
from meme_generator import account

class StudioTests(unittest.TestCase):
    def test_restore_edit_inputs_is_owned_private_and_expires(self):
        template=self.creation()
        job=self.client.post('/studio/jobs',json={'template_key':template['id'],'images':[self.image()],'texts':['保留这段文字'],'args':{},'idempotency_key':'edit-draft-owned'}).json()
        self.assertTrue(studio.work_one())
        url='/studio/jobs/'+job['id']+'/edit'
        response=self.client.get(url)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.headers['cache-control'],'private, no-store')
        value=response.json()
        self.assertEqual(value['kind'],'manual')
        self.assertEqual(value['draft']['template_key'],template['id'])
        self.assertEqual(value['draft']['texts'],['保留这段文字'])
        self.assertEqual(len(value['draft']['images']),1)
        self.app.dependency_overrides[account.current_user]=lambda:{'id':'bob'}
        self.assertEqual(self.client.get(url).status_code,404)
        self.app.dependency_overrides[account.current_user]=lambda:{'id':'alice'}
        (studio.root()/'studio_replays'/(job['id']+'.json')).unlink()
        self.assertEqual(self.client.get(url).status_code,410)

    def test_video_edit_source_checks_owner_and_retention(self):
        from meme_generator.features import livegif
        self.app.include_router(livegif.router)
        identifier='a'*32
        folder=livegif.directory();folder.mkdir(exist_ok=True,parents=True)
        (folder/(identifier+'.json')).write_text(json.dumps({'user_id':'alice','created':time.time(),'width':320,'height':240,'duration':4}))
        (folder/(identifier+'.media')).write_bytes(b'owned-video-sample')
        url='/studio/live/assets/'+identifier+'/source'
        response=self.client.get(url)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.content,b'owned-video-sample')
        self.assertEqual(response.headers['cache-control'],'private, no-store')
        self.app.dependency_overrides[account.current_user]=lambda:{'id':'bob'}
        self.assertEqual(self.client.get(url).status_code,404)
        self.app.dependency_overrides[account.current_user]=lambda:{'id':'alice'}
        (folder/(identifier+'.json')).write_text(json.dumps({'user_id':'alice','created':time.time()-8*86400}))
        self.assertEqual(self.client.get(url).status_code,404)

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.env=patch.dict(os.environ,{'GENSTICKER_STATE_DIR':self.temp.name});self.env.start()
        db=account.connection()
        with db:
            db.execute("INSERT INTO users(id,openid,name) VALUES('alice','fake-alice','造梗小王')")
            db.execute("INSERT INTO users(id,openid,name) VALUES('bob','fake-bob','另一个人')")
        db.close()
        app=FastAPI();app.include_router(studio.router);app.dependency_overrides[account.current_user]=lambda:{'id':'alice'};self.app=app;self.client=TestClient(app)
        self.spec={'width':512,'height':512,'layers':[{'type':'subject','box':[0,0,512,400]},{'type':'text','box':[10,420,492,70],'font_size':32,'slot':0,'value':'hello'}],'defaults':['hello']}
    def tearDown(self):self.client.close();self.env.stop();self.temp.cleanup()
    def creation(self,**kwargs):
        data={'name':'我的梗','spec':self.spec,**kwargs};r=self.client.post('/studio/templates',json=data);self.assertEqual(r.status_code,201,r.text);return r.json()
    def image(self):
        b=BytesIO();Image.new('RGB',(80,160),'red').save(b,'PNG');return base64.b64encode(b.getvalue()).decode()
    def test_private_template_never_enters_public_catalog_or_other_owner(self):
        item=self.creation();self.assertEqual(item['status'],'private')
        self.assertEqual(self.client.get(item['preview_url']).status_code,200)
        self.app.dependency_overrides[account.current_user]=lambda:{'id':'bob'}
        self.assertEqual(self.client.get('/studio/templates/'+item['id']).status_code,404)
        with self.assertRaises(Exception):studio.get_spec(item['id'],'bob')
        db=studio.connect();self.assertEqual(db.execute('SELECT count(*) FROM templates').fetchone()[0],0);db.close()
    def test_manual_job_idempotency_worker_ownership_and_expiry(self):
        item=self.creation();payload={'template_key':item['id'],'images':[self.image()],'texts':['hello'],'idempotency_key':'abcdefgh'}
        first=self.client.post('/studio/jobs',json=payload);self.assertEqual(first.status_code,201,first.text);identifier=first.json()['id']
        self.assertEqual(self.client.post('/studio/jobs',json=payload).json()['id'],identifier)
        self.assertEqual(self.client.post('/studio/jobs',json={**payload,'texts':['changed']}).status_code,409)
        self.assertTrue(studio.work_one());result=self.client.get('/studio/jobs/'+identifier).json();self.assertEqual(result['status'],'completed',result)
        image=self.client.get(result['result_url']);self.assertEqual(image.status_code,200)
        with Image.open(BytesIO(image.content)) as output:self.assertEqual(output.size,(512,512))
        self.app.dependency_overrides[account.current_user]=lambda:{'id':'bob'}
        self.assertEqual(self.client.get(result['result_url']).status_code,404)
        db=studio.init()
        with db:db.execute('UPDATE studio_jobs SET created=?',(time.time()-8*86400,))
        db.close();studio.cleanup();self.assertFalse((studio.root()/'studio_results'/identifier).exists())
    def test_queue_thumbnail_is_small_static_private_and_expires(self):
        item=self.creation();job=self.client.post('/studio/jobs',json={'template_key':item['id'],'images':[self.image()],'texts':['hello'],'idempotency_key':'queue-thumb-test'}).json()
        identifier=job['id'];self.assertTrue(studio.work_one())
        url='/studio/jobs/'+identifier+'/thumbnail';response=self.client.get(url)
        self.assertEqual(response.status_code,200);self.assertLess(len(response.content),20000)
        with Image.open(BytesIO(response.content)) as image:
            self.assertEqual(image.format,'JPEG');self.assertLessEqual(max(image.size),144)
        self.assertEqual(self.client.get(url).content,response.content)
        self.app.dependency_overrides[account.current_user]=lambda:{'id':'bob'}
        self.assertEqual(self.client.get(url).status_code,404,'cached thumbnail still checks ownership')
        self.app.dependency_overrides[account.current_user]=lambda:{'id':'alice'}
        self.assertEqual(self.client.delete('/studio/jobs/'+identifier).status_code,204)
        self.assertEqual(self.client.get(url).status_code,404,'cache cannot resurrect a deleted result')

    def test_ai_quota_atomic_daily_and_failed_identification_never_publishes(self):
        payload={'image':self.image(),'idempotency_key':'ai-first-job','rights_attested':True}
        r=self.client.post('/studio/templates/ai',json=payload);self.assertEqual(r.status_code,201,r.text)
        self.assertEqual(self.client.post('/studio/templates/ai',json=payload).json()['id'],r.json()['id'])
        self.assertEqual(self.client.post('/studio/templates/ai',json={**payload,'idempotency_key':'ai-second-job'}).status_code,429)
        with patch('meme_generator.features.quality.convert_caption',side_effect=ValueError('uncertain')):studio.work_one()
        self.assertEqual(self.client.get('/studio/jobs/'+r.json()['id']).json()['status'],'needs_manual')
        db=studio.init();self.assertEqual(db.execute('SELECT count(*) FROM templates').fetchone()[0],0);db.close()
    def test_ai_skill_pipeline_builds_actual_reusable_template_then_publishes(self):
        from PIL import ImageDraw
        from meme_generator.features.declarative import font
        output=BytesIO();image=Image.new('RGB',(512,512),'white');ImageDraw.Draw(image).text((24,22),'why',font=font(32),fill='black');image.save(output,'PNG')
        payload={'image':base64.b64encode(output.getvalue()).decode(),'idempotency_key':'actual-conversion','rights_attested':True}
        response=self.client.post('/studio/templates/ai',json=payload);self.assertEqual(response.status_code,201,response.text)
        # OCR recognition and external safety are isolated; image repair, quality
        # checks, bounded spec creation, rendering and publication are real here.
        recognized=[([[20,18],[120,18],[120,64],[20,64]],'why',.99)]
        with patch('meme_generator.features.quality.recognize',return_value=recognized),patch.object(studio,'moderate',return_value=('published','通过')):studio.work_one()
        job=self.client.get('/studio/jobs/'+response.json()['id']).json();self.assertEqual(job['status'],'completed',job)
        owned=self.client.get('/studio/templates/'+job['template_id']).json();self.assertEqual(owned['status'],'published');self.assertEqual(owned['params_type']['min_texts'],1)
        spec=owned['spec'];rendered=studio.render(spec,[],['new joke'])
        with Image.open(rendered) as result:self.assertEqual(result.size,(512,512))
        db=studio.init();metadata=json.loads(db.execute('SELECT metadata FROM templates').fetchone()[0]);db.close();self.assertEqual(metadata['conversion'],'caption-preserved-v2');self.assertIn('quality',metadata)

    def test_content_checks_require_both_text_and_image_pass(self):
        item=self.creation();row=studio.own_template(item['id'],{'id':'alice'});calls=[]
        class Reply:
            def __init__(self,data):self.data=data
            def json(self):return self.data
        class Provider:
            image_code=0
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def get(self,*args,**kwargs):return Reply({'access_token':'not-for-logs','expires_in':7200})
            def post(self,url,**kwargs):
                calls.append(url)
                if url.endswith('msg_sec_check'):return Reply({'errcode':0,'result':{'suggest':'pass'}})
                return Reply({'errcode':self.image_code})
        provider=Provider()
        with patch.dict(os.environ,{'WX_APPID':'configured','WX_APP_SECRET':'not-for-output'}),patch.dict(studio._token,{'value':'','expires':0}),patch.object(studio.httpx,'Client',return_value=provider):
            self.assertEqual(studio.moderate(row)[0],'published');self.assertTrue(any(u.endswith('msg_sec_check') for u in calls));self.assertTrue(any(u.endswith('img_sec_check') for u in calls))
            provider.image_code=87014;self.assertEqual(studio.moderate(row)[0],'rejected')
            provider.image_code=48001;self.assertEqual(studio.moderate(row)[0],'pending')

    def test_publish_requires_rights_and_workflow_records_stay_private(self):
        self.assertEqual(self.client.post('/studio/templates',json={'name':'claim','spec':self.spec,'publish':True}).status_code,422)
        item=self.creation(operations=[{'action':'private-operation'}])
        with patch.object(studio,'moderate',return_value=('published','通过')):studio.publish_owned(item['id'],{'id':'alice'})
        db=studio.init();public=json.loads(db.execute('SELECT metadata FROM templates').fetchone()[0]);db.close();self.assertNotIn('operations',public)
    def test_no_remote_or_existing_asset_reference_can_be_forged(self):
        spec={**self.spec,'layers':[{'type':'asset','box':[0,0,512,512],'value':'a'*64}]}
        self.assertEqual(self.client.post('/studio/templates',json={'name':'unsafe','spec':spec}).status_code,422)
        spec={**self.spec,'reference_asset':'b'*64}
        self.assertEqual(self.client.post('/studio/templates',json={'name':'unsafe','spec':spec}).status_code,422)
    def test_moderation_unavailable_never_publishes_and_success_does(self):
        item=self.creation();row=studio.own_template(item['id'],{'id':'alice'})
        with patch.dict(os.environ,{'WX_APPID':'','WX_APP_SECRET':''}):self.assertEqual(studio.moderate(row)[0],'pending')
        with patch.object(studio,'moderate',return_value=('pending','等待检查')):studio.publish_owned(item['id'],{'id':'alice'})
        db=studio.init();self.assertEqual(db.execute('SELECT count(*) FROM templates').fetchone()[0],0);db.close()
        with patch.object(studio,'moderate',return_value=('published','通过')):result=studio.publish_owned(item['id'],{'id':'alice'})
        self.assertEqual(result['status'],'published');db=studio.init();self.assertEqual(db.execute('SELECT count(*) FROM templates').fetchone()[0],1);db.close()
    def test_lease_recovery_and_sensitive_payload_erasure(self):
        item=self.creation();r=self.client.post('/studio/jobs',json={'template_key':item['id'],'images':[self.image()],'texts':['hello'],'idempotency_key':'recover-job'}).json();db=studio.init()
        with db:db.execute("UPDATE studio_jobs SET status='running',lease=?,attempts=1",(time.time()-1,))
        db.close();studio.work_one();db=studio.init();row=db.execute('SELECT * FROM studio_jobs WHERE id=?',(r['id'],)).fetchone();db.close();self.assertEqual(row['status'],'completed');self.assertEqual(row['payload'],'{}')

if __name__=='__main__':unittest.main()
