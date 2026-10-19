"""Real media rendering and state/ownership contracts for the October editor update."""
import base64
from io import BytesIO
import json
import os
import shutil
import tempfile
import time
import unittest
from unittest.mock import patch
from PIL import Image, ImageDraw
from fastapi import FastAPI
from fastapi.testclient import TestClient
from meme_generator import account
from meme_generator.features import studio, editor, livegif, recommend

class EditorLiveTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'GENSTICKER_STATE_DIR':self.directory.name,'GENSTICKER_BOOTSTRAP_SEEDS':'0'});self.env.start()
        db=account.connection()
        with db:
            for user in ('alice','bob'):db.execute('INSERT INTO users(id,openid,name) VALUES(?,?,?)',(user,'test-'+user,user))
        db.close()
        self.owner='alice';app=FastAPI()
        for router in (studio.router,editor.router,livegif.router,recommend.router):app.include_router(router)
        app.dependency_overrides[account.current_user]=lambda:{'id':self.owner}
        self.client=TestClient(app)
        self.identity=patch.object(editor,'identity',side_effect=lambda request:self.owner);self.identity.start()
        self.spec={'width':512,'height':512,'layers':[{'type':'subject','box':[96,40,240,320]}]}
    def tearDown(self):
        self.client.close();self.identity.stop();self.env.stop();self.directory.cleanup();editor._guides.clear();editor._foreground.clear()
    def template(self):
        response=self.client.post('/studio/templates',json={'name':'editor check','spec':self.spec})
        self.assertEqual(response.status_code,201,response.text);return response.json()['id']
    def test_private_guide_exact_window_and_auth_on_cache_hit(self):
        key=self.template();r=self.client.get('/images/templates/'+key+'/guide');self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(r.json()['windows'][0]['box'],[96,40,240,320]);self.assertFalse(r.json()['generic'])
        overlay=self.client.get(r.json()['overlay_url']);self.assertEqual(overlay.status_code,200)
        image=Image.open(BytesIO(overlay.content));self.assertEqual(image.getpixel((100,50))[3],0);self.assertEqual(image.getpixel((20,20))[3],255)
        self.owner='bob';self.assertEqual(self.client.get('/images/templates/'+key+'/guide').status_code,404)
        self.assertEqual(self.client.get(r.json()['overlay_url']).status_code,404)
    def test_unread_download_does_not_mark_read_view_does_and_regeneration_reuses_inputs(self):
        key=self.template();buf=BytesIO();Image.new('RGB',(64,80),'red').save(buf,'PNG')
        job=self.client.post('/studio/jobs',json={'template_key':key,'images':[base64.b64encode(buf.getvalue()).decode()],'idempotency_key':'unread-first'}).json()
        self.assertTrue(studio.work_one());path=f"/studio/jobs/{job['id']}"
        self.assertEqual(self.client.get('/studio/unread').json()['count'],1)
        self.assertEqual(self.client.get(path+'/image').status_code,200)
        self.assertEqual(self.client.get('/studio/unread').json()['count'],1)
        self.owner='bob';self.assertEqual(self.client.post(path+'/view').status_code,404)
        self.assertEqual(self.client.post(path+'/regenerate',json={'idempotency_key':'another-owner'}).status_code,404)
        self.owner='alice';self.assertEqual(self.client.post(path+'/view').status_code,204)
        self.assertEqual(self.client.get('/studio/unread').json()['count'],0)
        self.assertTrue(self.client.get('/studio/jobs').json()[0]['viewed'])
        again=self.client.post(path+'/regenerate',json={'idempotency_key':'rerender-once'})
        self.assertEqual(again.status_code,201,again.text)
        self.assertEqual(self.client.post(path+'/regenerate',json={'idempotency_key':'rerender-once'}).json()['id'],again.json()['id'])
        self.assertTrue(studio.work_one());self.assertEqual(self.client.get('/studio/unread').json()['count'],1)
        self.assertEqual(self.client.delete(path).status_code,204)
        self.assertFalse((studio.root()/'studio_replays'/(job['id']+'.json')).exists())
    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'requires FFmpeg')
    def test_actual_animated_gif_upload_rotate_crop_text_render_and_owner_expiry(self):
        frames=[]
        for offset in range(12):
            image=Image.new('RGB',(160,96),'#3a795f');ImageDraw.Draw(image).rectangle((offset*8,15,offset*8+25,65),fill='#ffce82');frames.append(image)
        buf=BytesIO();frames[0].save(buf,'GIF',save_all=True,append_images=frames[1:],duration=100,loop=0)
        uploaded=self.client.post('/studio/live/assets',files={'file':('live.gif',buf.getvalue(),'image/gif')})
        self.assertEqual(uploaded.status_code,201,uploaded.text);asset=uploaded.json()
        self.assertEqual(self.client.get(asset['poster_url']).status_code,200)
        job=self.client.post('/studio/live/jobs',json={'asset_id':asset['asset_id'],'idempotency_key':'live-end-to-end','duration':1,'crop':[0,0,.5,1],'rotation':90,'flip':True,'text':'hello'})
        self.assertEqual(job.status_code,201,job.text);self.assertTrue(studio.work_one())
        result=self.client.get('/studio/jobs/'+job.json()['id']).json();self.assertEqual(result['status'],'completed',result)
        output=self.client.get(result['result_url']);self.assertEqual(output.headers['content-type'],'image/gif')
        gif=Image.open(BytesIO(output.content));self.assertGreater(gif.n_frames,2);self.assertEqual(gif.size,(72,240));self.assertLessEqual(len(output.content),500*1024)
        self.owner='bob';self.assertEqual(self.client.get(asset['poster_url']).status_code,404);self.assertEqual(self.client.get(result['result_url']).status_code,404)
        self.owner='alice';meta=livegif.directory()/(asset['asset_id']+'.json');data=json.loads(meta.read_text());data['created']=time.time()-8*86400;meta.write_text(json.dumps(data));livegif.cleanup();self.assertFalse(meta.exists())
    def test_local_gif_sync_is_private_idempotent_and_skips_reencoding(self):
        frames=[Image.new('RGB',(100,80),color) for color in ('red','green','blue')]
        buf=BytesIO();frames[0].save(buf,'GIF',save_all=True,append_images=frames[1:],duration=100,loop=0);raw=buf.getvalue()
        response=self.client.post('/studio/live/results',files={'file':('local.gif',raw,'image/gif')},data={'idempotency_key':'local-sync-once'})
        self.assertEqual(response.status_code,201,response.text);job=response.json()
        again=self.client.post('/studio/live/results',files={'file':('local.gif',raw,'image/gif')},data={'idempotency_key':'local-sync-once'})
        self.assertEqual(again.json()['id'],job['id'])
        with patch.object(livegif,'run',side_effect=AssertionError('prepared GIF must not reencode')):self.assertTrue(studio.work_one())
        output=self.client.get('/studio/jobs/'+job['id']+'/image');self.assertEqual(output.content,raw)
        self.assertEqual(self.client.get('/studio/unread').json()['count'],0)
        self.owner='bob';self.assertEqual(self.client.get('/studio/jobs/'+job['id']+'/image').status_code,404)
        self.owner='alice'
        invalid=self.client.post('/studio/live/results',files={'file':('static.gif',raw[:10],'image/gif')},data={'idempotency_key':'local-invalid-file'})
        self.assertEqual(invalid.status_code,422)
        large=self.client.post('/studio/live/results',files={'file':('huge.gif',b'x'*(500*1024+1),'image/gif')},data={'idempotency_key':'local-too-large'})
        self.assertEqual(large.status_code,413)

    @unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'requires FFmpeg')
    def test_long_source_selects_middle_clip_and_finishes_in_queue(self):
        frames=[Image.new('RGB',(32,32),color) for color in ('red','green')]
        buf=BytesIO();frames[0].save(buf,'GIF',save_all=True,append_images=frames[1:],duration=5000,loop=0)
        response=self.client.post('/studio/live/assets',files={'file':('long.gif',buf.getvalue(),'image/gif')})
        self.assertEqual(response.status_code,201,response.text)
        job=self.client.post('/studio/live/jobs',json={'asset_id':response.json()['asset_id'],'idempotency_key':'middle-long-source','start':4,'duration':3,'crop':[.1,.1,.8,.8]}).json()
        self.assertTrue(studio.work_one())
        result=self.client.get('/studio/jobs/'+job['id']).json();self.assertEqual(result['status'],'completed',result)
        output=self.client.get(result['result_url']);self.assertLessEqual(len(output.content),500*1024)

    def test_complex_nine_second_scene_is_always_compressed_without_redo(self):
        import numpy as np
        random=np.random.default_rng(17)
        frames=[Image.fromarray(random.integers(0,256,(120,160,3),dtype=np.uint8)) for _ in range(90)]
        raw=livegif.fit_gif(frames);self.assertLessEqual(len(raw),500*1024)
        image=Image.open(BytesIO(raw));self.assertLessEqual(max(image.size),240)
        from PIL import ImageSequence
        self.assertEqual(sum(frame.info['duration'] for frame in ImageSequence.Iterator(image)),9000)

    def test_static_photo_and_invalid_crop_have_clear_errors(self):
        buf=BytesIO();Image.new('RGB',(32,32),'red').save(buf,'JPEG')
        response=self.client.post('/studio/live/assets',files={'file':('static.jpg',buf.getvalue(),'image/jpeg')})
        self.assertEqual(response.status_code,422);self.assertIn('存储为视频',response.json()['detail'])
        for crop in ([0,0,0,1],[0,0,2,1],[-.1,0,1,1]):
            self.assertEqual(self.client.post('/studio/live/jobs',json={'asset_id':'a'*32,'idempotency_key':'invalid-crop','crop':crop}).status_code,422)
