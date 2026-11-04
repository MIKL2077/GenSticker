from io import BytesIO
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from meme_generator.account import current_user
from meme_generator.features import recommend, studio, result_collage as c
from meme_generator.features.store import connect, root


class ResultCollageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,GENSTICKER_STATE_DIR=self.temp.name);self.env.start()
        self.identifier='a'*32;self.who='alice'
        directory=root()/'private'/'alice'/self.identifier;directory.mkdir(parents=True)
        self.paths=[]
        for i,(colors,delays) in enumerate([(['red','blue'],[100,300]),(['lime','yellow'],[200,400]),(['magenta'],[100])]):
            frames=[Image.new('RGB',(40,20),color) for color in colors]
            path=directory/f'{i}.gif'
            frames[0].save(path,'GIF',save_all=True,append_images=frames[1:],duration=delays,loop=0)
            self.paths.append(path)
        db=connect()
        with db:
            db.execute('INSERT INTO jobs(id,user_id,idempotency,asset_id,day,status,created,updated) VALUES(?,?,?,?,?,?,?,?)',
                       (self.identifier,'alice','collage-test','photo','today','completed',time.time(),time.time()))
            for i,path in enumerate(self.paths):db.execute('INSERT INTO results VALUES(?,?,?,?,?,?,?,?)',(self.identifier,i,'template',1,'cat','[]',str(path),str(path)))
        db.close()
        app=FastAPI();app.include_router(recommend.router);app.include_router(studio.router)
        app.dependency_overrides[current_user]=lambda:{'id':self.who}
        self.client=TestClient(app);self.url='/recommend/jobs/'+self.identifier+'/collage'

    def tearDown(self):
        self.client.close();self.env.stop();self.temp.cleanup()

    def test_full_independent_loops_stills_and_selection_order(self):
        response=self.client.post(self.url,json={'slots':[0,1,2]})
        self.assertEqual(response.status_code,200,response.text[:100])
        self.assertEqual(response.headers['cache-control'],'private, no-store')
        self.assertLessEqual(len(response.content),c.MAX_BYTES)
        with Image.open(BytesIO(response.content)) as image:
            self.assertEqual(image.info['loop'],0);duration=0
            expected=[('red','lime'),('blue','lime'),('blue','yellow'),('red','yellow'),('blue','yellow')]
            self.assertEqual(image.n_frames,len(expected))
            from PIL import ImageColor
            for i,colors in enumerate(expected):
                image.seek(i);rgb=image.convert('RGB');duration+=image.info['duration']
                self.assertEqual(rgb.getpixel((92,92)),ImageColor.getrgb(colors[0]))
                self.assertEqual(rgb.getpixel((264,92)),ImageColor.getrgb(colors[1]))
                self.assertEqual(rgb.getpixel((92,264)),ImageColor.getrgb('magenta'))
                self.assertEqual(rgb.getpixel((92,20)),c.PAPER)
            self.assertEqual(duration,600)
        swapped=self.client.post(self.url,json={'slots':[1,0]})
        with Image.open(BytesIO(swapped.content)) as image:self.assertEqual(image.convert('RGB').getpixel((92,92)),(0,255,0))

    def test_foreign_expired_missing_and_arbitrary_paths_are_rejected(self):
        self.who='bob';self.assertEqual(self.client.post(self.url,json={'slots':[0]}).status_code,404)
        self.who='alice';self.assertEqual(self.client.post(self.url,json={'slots':[8]}).status_code,404)
        self.assertEqual(self.client.post(self.url,json={'slots':[0,0]}).status_code,422)
        self.assertEqual(self.client.post(self.url,json={'slots':[True]}).status_code,422)
        self.assertEqual(self.client.post(self.url,json={'slots':[0],'url':'https://example.com/photo'}).status_code,422)
        db=connect()
        with db:db.execute('UPDATE results SET path=? WHERE job_id=? AND slot=0',('/etc/passwd',self.identifier))
        db.close();self.assertEqual(self.client.post(self.url,json={'slots':[0]}).status_code,410)
        db=connect()
        with db:db.execute('UPDATE jobs SET created=? WHERE id=?',(time.time()-8*86400,self.identifier))
        db.close();self.assertEqual(self.client.post(self.url,json={'slots':[1]}).status_code,410)

    def test_corrupt_input_does_not_become_a_static_collage(self):
        self.paths[0].write_bytes(b'not an image')
        self.assertEqual(self.client.post(self.url,json={'slots':[0,1]}).status_code,422)

    def test_nine_tiles_remain_animated_and_retry_preserves_duration(self):
        raw=c.compose(self.paths*3)
        with Image.open(BytesIO(raw)) as image:
            self.assertGreater(image.n_frames,1);duration=0
            for i in range(image.n_frames):image.seek(i);duration+=image.info['duration']
            self.assertEqual(duration,600)
        # Exercise size retries with a tiny first budget and allow the next encode.
        original=Image.Image.save;calls=[]
        def save(image,fp,*args,**kwargs):
            result=original(image,fp,*args,**kwargs)
            if args and args[0]=='GIF':
                calls.append(1)
                if len(calls)==1:fp.write(b'x'*c.MAX_BYTES)
            return result
        with patch.object(Image.Image,'save',new=save):raw=c.compose(self.paths)
        self.assertGreater(len(calls),1)
        with Image.open(BytesIO(raw)) as image:
            duration=0
            for i in range(image.n_frames):image.seek(i);duration+=image.info['duration']
            self.assertEqual(duration,600)

    def test_serial_guard_is_released_on_encoder_failure(self):
        with patch.object(c,'compose',side_effect=ValueError('bad input')):
            with self.assertRaises(ValueError):c.compose_serial(self.paths)
        self.assertTrue(c.slots.acquire(False));c.slots.release()

    def test_combined_timelines_do_not_introduce_clamped_ten_ms_frames(self):
        for path,delays in zip(self.paths[:2],[[30,30],[40,40]]):
            Image.new('RGB',(40,20),'red').save(path,'GIF',save_all=True,append_images=[Image.new('RGB',(40,20),'blue')],duration=delays,loop=0)
        with Image.open(BytesIO(c.compose(self.paths[:2]))) as image:
            duration=0
            for i in range(image.n_frames):
                image.seek(i);self.assertGreaterEqual(image.info['duration'],20);duration+=image.info['duration']
            self.assertEqual(duration,80)


class StudioCollageTests(unittest.TestCase):
    tearDown=ResultCollageTests.tearDown

    def setUp(self):
        ResultCollageTests.setUp(self)
        self.ids=[format(i+1,'032x') for i in range(3)]
        directory=root()/'studio_results';directory.mkdir()
        db=studio.init()
        with db:
            for identifier,path in zip(self.ids,self.paths):
                (directory/identifier).write_bytes(path.read_bytes())
                db.execute("INSERT INTO studio_jobs(id,user_id,kind,idem,digest,payload,status,created,updated) VALUES(?,?,'manual',?,'digest','{}','completed',?,?)",(identifier,'alice',identifier,time.time(),time.time()))
        db.close();self.studio_url='/studio/jobs/collage'

    def test_queue_selection_order_and_animation(self):
        response=self.client.post(self.studio_url,json={'job_ids':[self.ids[1],self.ids[0],self.ids[2]]})
        self.assertEqual(response.status_code,200,response.text[:100])
        self.assertEqual(response.headers['cache-control'],'private, no-store')
        with Image.open(BytesIO(response.content)) as image:
            self.assertEqual(image.info['loop'],0);self.assertGreater(image.n_frames,1)
            self.assertEqual(image.convert('RGB').getpixel((92,92)),(0,255,0))
            duration=0
            for i in range(image.n_frames):image.seek(i);duration+=image.info['duration']
            self.assertEqual(duration,600)

    def test_queue_rejects_foreign_pending_expired_and_unsafe_ids(self):
        payload={'job_ids':self.ids[:2]}
        self.who='bob';self.assertEqual(self.client.post(self.studio_url,json=payload).status_code,404)
        self.who='alice'
        for ids in [[self.ids[0]],[self.ids[0]]*2,['../etc/passwd',self.ids[0]],self.ids*4,[True,self.ids[0]]]:
            self.assertEqual(self.client.post(self.studio_url,json={'job_ids':ids}).status_code,422)
        self.assertEqual(self.client.post(self.studio_url,json={**payload,'url':'https://example.test'}).status_code,422)
        db=studio.init()
        with db:db.execute("UPDATE studio_jobs SET status='running' WHERE id=?",(self.ids[0],))
        db.close();self.assertEqual(self.client.post(self.studio_url,json=payload).status_code,409)
        db=studio.init()
        with db:db.execute("UPDATE studio_jobs SET status='completed',created=? WHERE id=?",(time.time()-8*86400,self.ids[0]))
        db.close();self.assertEqual(self.client.post(self.studio_url,json=payload).status_code,410)

    def test_queue_missing_symlink_corrupt_and_deleted_during_composition(self):
        payload={'job_ids':self.ids[:2]};path=root()/'studio_results'/self.ids[0]
        path.unlink();self.assertEqual(self.client.post(self.studio_url,json=payload).status_code,410)
        path.symlink_to(self.paths[0]);self.assertEqual(self.client.post(self.studio_url,json=payload).status_code,410)
        path.unlink();path.write_bytes(b'bad');self.assertEqual(self.client.post(self.studio_url,json=payload).status_code,422)
        path.write_bytes(self.paths[0].read_bytes())
        original=c.compose_serial
        def delete_during_compose(paths):
            raw=original(paths);db=studio.init()
            with db:db.execute('DELETE FROM studio_jobs WHERE id=?',(self.ids[0],))
            db.close();return raw
        with patch.object(c,'compose_serial',side_effect=delete_during_compose):
            self.assertEqual(self.client.post(self.studio_url,json=payload).status_code,404)

    def test_queue_requires_login(self):
        self.client.app.dependency_overrides.clear()
        self.assertEqual(self.client.post(self.studio_url,json={'job_ids':self.ids[:2]}).status_code,401)

    def test_queue_all_stills_and_shared_generation_rate_limit(self):
        for identifier in self.ids:
            Image.new('RGB',(20,40),'red').save(root()/'studio_results'/identifier,'PNG')
        response=self.client.post(self.studio_url,json={'job_ids':self.ids})
        self.assertEqual(response.status_code,200)
        with Image.open(BytesIO(response.content)) as image:self.assertEqual(image.n_frames,1)
        from meme_generator.features.recommend import admit_generation
        db=studio.init()
        with db:
            db.execute('BEGIN IMMEDIATE')
            for i in range(7):admit_generation(db,'alice','other-generation-'+str(i),time.time())
        db.close()
        self.assertEqual(self.client.post(self.studio_url,json={'job_ids':self.ids}).status_code,429)
