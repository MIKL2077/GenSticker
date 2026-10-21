import json,os,tempfile,time,unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from PIL import Image,ImageDraw,ImageSequence
from fastapi import FastAPI
from fastapi.testclient import TestClient
from meme_generator.account import current_user
from meme_generator.features import recommend,vision,worker,catalog,portrait,subjects
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
    def test_visitors_can_detect_without_creating_private_assets(self):
        self.client.app.dependency_overrides.clear()
        with patch.object(portrait,'candidate_boxes',return_value=[{'id':'0','kind':'person','box':[.1,.1,.5,.6]}]):
            response=self.client.post('/recommend/subjects/detect',headers={'X-Gensticker-Visitor':'visitor-fixture-20261021'},files={'file':('photo.jpg',self.photo)})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.headers['cache-control'],'private, no-store')
        self.assertEqual(response.json()['candidates'][0]['kind'],'person')
        db=connect();self.assertEqual(db.execute('SELECT count(*) FROM assets').fetchone()[0],0);db.close()
    def test_covered_face_uses_real_foreground_regions_and_no_fabricated_person(self):
        cutout=Image.new('RGBA',(240,320))
        ImageDraw.Draw(cutout).rectangle((60,80,180,280),fill='red')
        with patch.object(portrait,'detect_heads',return_value=[]),patch.object(subjects,'warm_subject_model',return_value=True),patch.object(vision,'extract',return_value=cutout):
            boxes=portrait.candidate_boxes(Image.new('RGB',(480,640)))
        self.assertEqual(len(boxes),1);self.assertEqual(boxes[0]['kind'],'subject')
        x,y,w,h=boxes[0]['box'];self.assertLess(x,.25);self.assertGreater(x+w,.75)
        self.assertLess(y,.25);self.assertGreater(y+h,.875)
        with patch.object(portrait,'detect_heads',return_value=[]),patch.object(subjects,'warm_subject_model',return_value=True),patch.object(vision,'extract',return_value=Image.new('RGBA',(240,320),'red')):
            self.assertEqual(portrait.candidate_boxes(Image.new('RGB',(480,640))),[],'uncertain whole-frame masks must not invent candidates')
    def test_foreground_fallback_is_bounded_and_busy_never_queues(self):
        self.assertTrue(portrait._foreground_slot.acquire(False))
        try:
            with patch.object(subjects,'warm_subject_model',side_effect=AssertionError('busy inference must not run')):
                self.assertEqual(portrait.foreground_candidates(Image.new('RGB',(240,320))),[])
        finally:portrait._foreground_slot.release()
    def test_default_detection_never_runs_segmentation_but_explicit_search_can(self):
        with patch.object(portrait,'detect_heads',return_value=[]),patch.object(vision,'extract',side_effect=AssertionError('fast face detection must not segment')):
            response=self.client.post('/recommend/subjects/detect',files={'file':('photo.jpg',self.photo)})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json(),{'candidates':[],'method':'server-fast-heads'})
        with patch.object(portrait,'detect_heads',return_value=[]),patch.object(portrait,'foreground_candidates',return_value=[{'id':'subject-0','kind':'subject','box':[.1,.1,.5,.5]}]) as foreground:
            response=self.client.post('/recommend/subjects/detect',files={'file':('photo.jpg',self.photo)},data={'fast':'false'})
        self.assertEqual(response.status_code,200);self.assertEqual(response.json()['candidates'][0]['kind'],'subject');foreground.assert_called_once()
    def test_editor_cutout_is_reused_without_second_inference(self):
        image=Image.new('RGBA',(120,160));ImageDraw.Draw(image).rectangle((20,10,100,150),fill='red')
        path=Path(self.temp.name)/'selected.png';image.save(path)
        with patch.object(vision,'extract',side_effect=AssertionError('an editor mask must not be inferred again')):
            output,analysis=vision.process(path,subject_selected=True)
        self.assertEqual(analysis['method'],'selected-alpha');self.assertTrue(analysis['cutout']);self.assertEqual(output.size,(81,141))
    def test_detection_can_prepare_one_mask_without_another_photo_upload(self):
        boxes=[{'id':'0','kind':'person','box':[.1,.1,.5,.6]}]
        with patch.object(portrait,'candidate_boxes',return_value=boxes),patch.object(subjects,'extract_subject_mask',return_value=b'bounded-mask') as mask:
            response=self.client.post('/recommend/subjects/detect',files={'file':('photo.jpg',self.photo)},data={'with_mask':'true'})
        self.assertEqual(response.status_code,200);self.assertEqual(response.json()['preview']['box'],boxes[0]['box']);mask.assert_called_once()
        with patch.object(portrait,'candidate_boxes',return_value=boxes),patch.object(subjects,'extract_subject_mask',side_effect=RuntimeError('not available')):
            response=self.client.post('/recommend/subjects/detect',files={'file':('photo.jpg',self.photo)},data={'with_mask':'true'})
        self.assertEqual(response.status_code,200);self.assertEqual(response.json()['candidates'],boxes);self.assertNotIn('preview',response.json())
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
