import json,os,tempfile,time,unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from PIL import Image,ImageDraw,ImageSequence
from fastapi import FastAPI
from fastapi.testclient import TestClient
from meme_generator.account import current_user
from meme_generator.features import recommend,vision,worker,catalog,portrait
from meme_generator.features.store import connect
from meme_generator.features.animation import save_result_files

class SubjectAnimationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.env=patch.dict(os.environ,{'GENSTICKER_STATE_DIR':self.temp.name,'GENSTICKER_BOOTSTRAP_SEEDS':'0'});self.env.start();self.owner='fixture'
        app=FastAPI();app.include_router(recommend.router);app.dependency_overrides[current_user]=lambda:{'id':self.owner};self.client=TestClient(app)
        buffer=BytesIO();Image.new('RGB',(320,240),'red').save(buffer,'JPEG');self.photo=buffer.getvalue()
    def tearDown(self):self.client.close();self.env.stop();self.temp.cleanup();recommend._detect_recent.clear()
    def test_selected_asset_is_separate_and_worker_never_reselects_face(self):
        original=self.client.post('/recommend/assets',files={'file':('photo.jpg',self.photo)}).json()['asset_id']
        selected=self.client.post('/recommend/assets',files={'file':('photo.jpg',self.photo)},data={'subject_selected':'true'}).json()['asset_id'];self.assertNotEqual(original,selected)
        self.assertEqual(self.client.post('/recommend/assets',files={'file':('photo.jpg',self.photo)},data={'subject_selected':'true'}).json()['asset_id'],selected)
        db=connect();path=db.execute('SELECT path FROM assets WHERE id=?',(selected,)).fetchone()[0];db.close();self.assertTrue(Path(path).stem.endswith('.selected'))
        cutout=Image.new('RGBA',(320,240));draw=ImageDraw.Draw(cutout);draw.rectangle((40,30,80,200),fill='red');draw.rectangle((200,50,250,170),fill='blue')
        with patch.object(vision,'_session',object()),patch.object(vision,'extract',return_value=cutout),patch.object(portrait,'detect_heads',side_effect=AssertionError('must not select another face')):
            image,analysis=vision.process(path,subject_selected=True)
        self.assertEqual(analysis['framing'],'user-selection');self.assertTrue(analysis['subject_selected']);self.assertGreater(image.width,200)
    def test_candidates_are_bounded_and_detection_is_transient_rate_limited(self):
        with patch.object(portrait,'detect_heads',return_value=[('person',(0,0,60,70)),('person',(1,1,60,70)),('animal',(240,180,90,80))]):
            boxes=portrait.candidate_boxes(Image.new('RGB',(320,240)));self.assertEqual(len(boxes),2)
            for item in boxes:
                x,y,w,h=item['box'];self.assertGreater(w,0);self.assertLessEqual(x+w,1);self.assertLessEqual(y+h,1)
        with patch.object(portrait,'candidate_boxes',return_value=boxes):
            result=self.client.post('/recommend/subjects/detect',files={'file':('photo.jpg',self.photo)});self.assertEqual(result.status_code,200);self.assertEqual(len(result.json()['candidates']),2)
            db=connect();self.assertEqual(db.execute('SELECT COUNT(*) FROM assets').fetchone()[0],0);db.close()
            for _ in range(11):self.assertEqual(self.client.post('/recommend/subjects/detect',files={'file':('photo.jpg',self.photo)}).status_code,200)
            self.assertEqual(self.client.post('/recommend/subjects/detect',files={'file':('photo.jpg',self.photo)}).status_code,429)
    def test_gif_results_and_previews_preserve_dimensions_and_timing(self):
        frames=[Image.new('RGB',(100,80),color) for color in ('red','green','blue')];raw=BytesIO();frames[0].save(raw,'GIF',save_all=True,append_images=frames[1:],duration=[80,140,220],loop=0)
        path,preview=save_result_files(raw,Path(self.temp.name),0)
        self.assertEqual(path.read_bytes(),raw.getvalue())
        for target in (path,preview):
            with Image.open(target) as image:self.assertEqual(image.size,(100,80));self.assertEqual(image.n_frames,3);self.assertEqual(sum(frame.info['duration'] for frame in ImageSequence.Iterator(image)),440)
        # API picks the actual content type and retains account isolation.
        db=connect();now=time.time()
        with db:
            db.execute("INSERT INTO jobs(id,user_id,idempotency,asset_id,day,status,created,updated) VALUES(?,?,?,?,?,?,?,?)",('j','fixture','anim-fixture','asset','2026-10-19','completed',now,now))
            db.execute('INSERT INTO results VALUES(?,?,?,?,?,?,?,?)',('j',0,'template',1,'petpet','[]',str(path),str(preview)))
        db.close()
        result=self.client.get('/recommend/jobs/j/results/0?preview=true');self.assertEqual(result.headers['content-type'],'image/gif');self.assertEqual(Image.open(BytesIO(result.content)).n_frames,3)
        self.owner='other';self.assertEqual(self.client.get('/recommend/jobs/j/results/0').status_code,404)
