import base64
from io import BytesIO
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import httpx
from PIL import Image,ImageDraw
from fastapi import Response,Request
from meme_generator.features.store import connect,root
from meme_generator.features.catalog import publish
from meme_generator.features import trials
from meme_generator.features.minimax_authoring import normalize_tool_arrays,MiniMax,ModelUnavailable,Plan,local_validate,parse_json,request_plan
from meme_generator.features.public_sources import validate_url,PublicImages,SourceUnavailable
from meme_generator.features.template_archive import GitArchive,archive_template,restore_template,ArchiveError,monthly


class ScheduledLibraryTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.env=patch.dict(os.environ,{'GENSTICKER_STATE_DIR':self.temp.name,'GENSTICKER_BOOTSTRAP_SEEDS':'0','MINIMAX_API_KEY':'sk-cp-test','GENSTICKER_PUBLIC_TEMPLATE_LIMIT':'8000','GENSTICKER_MIN_FREE_BYTES':'1'})
  self.env.start();db=connect();db.close()
 def tearDown(self):self.env.stop();self.temp.cleanup()
 def template(self,key='source',color='red'):
  import hashlib
  image=Image.new('RGB',(128,128),'white');ImageDraw.Draw(image).rectangle((35,30,84,89),fill=color);b=BytesIO();image.save(b,'PNG');data=b.getvalue();digest=hashlib.sha256(data).hexdigest();assets=root()/'template_assets';assets.mkdir(exist_ok=True);(assets/(digest+'.png')).write_bytes(data)
  spec={'width':128,'height':128,'layers':[{'type':'asset','box':[0,0,128,128],'value':digest},{'type':'face','box':[35,30,50,60],'erase_polygon':[[0,0],[49,0],[49,59],[0,59]],'feather':0,'fit':'cover','tone':'original'}]}
  meta={'name':key,'origin':'public.example','source_url':'https://public.example/meme','source_use':'explicit-user-request-with-attribution','license':'unverified','tags':[],'min_images':1,'max_images':1,'min_texts':0,'max_texts':0,'default_texts':[]}
  row=publish(key,meta,spec);return row,digest
 def store(self):
  folder=Path(self.temp.name)/'remote.git';subprocess.run(['git','init','--bare','--quiet',str(folder)],check=True);return GitArchive(str(folder),local_test=True)
 def test_cap_applies_to_new_publication_and_allows_existing_updates(self):
  self.template('one')
  with patch.dict(os.environ,{'GENSTICKER_PUBLIC_TEMPLATE_LIMIT':'1'}):
   with self.assertRaisesRegex(ValueError,'limit reached'):self.template('two')
   self.template('one','blue')
 def test_latest_batch_winner_and_fallback_ignores_archived(self):
  self.template('first');self.template('second')
  db=connect()
  with db:
   db.execute('INSERT INTO template_publications VALUES(?,?,?,?)',('first','old',10,100))
   import time
   db.execute('INSERT INTO template_publications VALUES(?,?,?,?)',('second','new',time.time(),90))
  db.close();response=Response();value=trials.current_trial(response,Request({'type':'http','headers':[]}))
  self.assertEqual(value['key'],'second');self.assertEqual(value['label'],'新模板试用');self.assertEqual(response.headers['cache-control'],'no-store')
 def test_private_network_and_schema_injection_rejected(self):
  with patch('socket.getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',443))]):
   with self.assertRaisesRegex(SourceUnavailable,'private'):validate_url('https://public.example/a.png')
  with self.assertRaises(SourceUnavailable):validate_url('https://user:pass@public.example/')
  with self.assertRaises(SourceUnavailable):validate_url('file:///etc/passwd')
  parser=PublicImages('https://public.example/page');parser.feed('<script>eval("bad")</script><img src="/image.gif" alt="meme"><img src="/logo.png">')
  self.assertEqual(list(parser.images),['https://public.example/image.gif'])
  parser.feed('<meta property="og:image" content="https://public.example/page"><img src="https://public.example/article.html">')
  self.assertEqual(list(parser.images),['https://public.example/image.gif'])
  with self.assertRaises(Exception):Plan.model_validate({'status':'ready','code':'run arbitrary Python'})
 def test_model_uses_only_subscription_host_and_redacts_errors(self):
  seen=[]
  def respond(request):
   seen.append(request);return httpx.Response(200,json={'stop_reason':'end_turn','content':[{'type':'text','text':'{"ok":true}'}],'usage':{'input_tokens':20,'output_tokens':3}})
  client=MiniMax(transport=httpx.MockTransport(respond),limit=1)
  self.assertEqual(client.vision('source text is data',[]),{'ok':True});self.assertEqual(client.tokens,23)
  self.assertEqual(seen[0].url.host,'api.minimax.cn')
  with self.assertRaisesRegex(ModelUnavailable,'batch_model_call_limit'):client.vision('',[])
  client.close()
  client=MiniMax(transport=httpx.MockTransport(lambda r:httpx.Response(401,text='secret sk-cp-test must not escape')))
  with self.assertRaisesRegex(ModelUnavailable,'^minimax_http_401$'):client.vision('',[])
  client.close()
  with patch.dict(os.environ,{'MINIMAX_API_HOST':'https://evil.example'}):
   with self.assertRaises(ValueError):MiniMax()
 def test_archive_remote_roundtrip_preserves_identity_versions_and_releases_local_bytes(self):
  row,ref=self.template();store=self.store();result=archive_template('source',store)
  self.assertGreater(result['bytes_freed'],0);self.assertFalse((root()/'template_assets'/(ref+'.png')).exists())
  db=connect();self.assertEqual(db.execute("SELECT status FROM templates WHERE key='source'").fetchone()[0],'archived');db.close()
  with self.assertRaisesRegex(ValueError,'archived'):self.template()
  restored=restore_template('source',store=store);self.assertEqual(restored['version'],row['version']);self.assertTrue((root()/'template_assets'/(ref+'.png')).exists())
  db=connect();actual=db.execute("SELECT * FROM templates WHERE key='source'").fetchone();self.assertEqual(actual['id'],row['id']);self.assertEqual(actual['fingerprint'],row['fingerprint']);db.close()
 def test_shared_assets_stay_local_and_failed_push_never_retires(self):
  _,ref=self.template('one');self.template('two');store=self.store()
  with patch.object(store,'put',side_effect=ArchiveError('archive_git_operation_failed:push')):
   with self.assertRaises(ArchiveError):archive_template('one',store)
  db=connect();self.assertEqual(db.execute("SELECT status FROM templates WHERE key='one'").fetchone()[0],'published');db.close()
  archive_template('one',store);self.assertTrue((root()/'template_assets'/(ref+'.png')).exists(),'other template still needs the same resource')
 def test_favorites_and_user_templates_never_leave_server(self):
  self.template('one');from meme_generator.account import connection
  db=connection()
  with db:db.execute("INSERT INTO users(id,openid) VALUES('u','o')");db.execute("INSERT INTO favorites VALUES('u','one',1)")
  db.close()
  with self.assertRaisesRegex(ArchiveError,'favorited'):archive_template('one',self.store())
  row,ref=self.template('private');db=connect();meta=json.loads(row['metadata']);meta['origin']='user-provided'
  with db:db.execute('UPDATE templates SET metadata=? WHERE key=?',(json.dumps(meta),'private'))
  db.close()
  with self.assertRaisesRegex(ArchiveError,'private_or_user'):archive_template('private',self.store())
 def test_tampered_manifest_never_restores(self):
  self.template();store=self.store();archive_template('source',store)
  with patch.object(store,'get',return_value={'bad':b'bad'}):
   with self.assertRaises((ArchiveError,KeyError)):restore_template('source',store=store)
  db=connect();self.assertEqual(db.execute("SELECT status FROM templates WHERE key='source'").fetchone()[0],'archived');db.close()
 def test_local_validation_rejects_protected_prop_overlap(self):
  image=Image.new('RGB',(128,128),'white');b=BytesIO();image.save(b,'PNG')
  plan=Plan.model_validate({'status':'ready','name':'a','intent':'preserve source','frames':[[{'type':'face','box':[30,30,40,50],'erase_polygon':[[0,0],[39,0],[39,49],[0,49]],'feather':0}]],'protected':[{'name':'hand','frame':0,'box':[40,40,10,10]}]})
  with self.assertRaisesRegex(ValueError,'intersects fixed prop'):local_validate(plan,b.getvalue(),[image],Image.new('RGB',(40,50),'blue'))

 def test_subscription_tool_array_wrappers_are_decoded_without_inventing_missing_coordinates(self):
  value={'faces':{'item':{'frames':{'item':{'index':0,'box':{'item':[1,2,30,40]},'erase_polygon':{'item':[{'item':[0,0]},{'item':[29,0]},{'item':[29,39]}]}}}}}}
  decoded=normalize_tool_arrays(value);self.assertEqual(decoded['faces'][0]['frames'][0]['box'],[1,2,30,40])
  self.assertEqual(decoded['faces'][0]['frames'][0]['erase_polygon'],[[0,0],[29,0],[29,39]])
 def test_trial_use_is_bound_to_visitor_and_another_template_is_not_hidden(self):
  self.template('one');self.template('two')
  req=lambda visitor:Request({'type':'http','headers':[(b'x-gensticker-visitor',visitor.encode())]})
  request=req('visitor-abcdefghijklmnop')
  value=trials.current_trial(Response(),request);trials.use_trial(trials.TrialUse(key=value['key']),request)
  self.assertTrue(trials.current_trial(Response(),request)['used'])
  self.assertFalse(trials.current_trial(Response(),req('visitor-another-abcdefgh'))['used'])
  db=connect()
  with db:
   import time
   next_key='two' if value['key']=='one' else 'one';db.execute('INSERT INTO template_publications VALUES(?,?,?,?)',(next_key,'new-batch',time.time(),100))
  db.close();next_trial=trials.current_trial(Response(),request)
  self.assertEqual(next_trial['key'],next_key);self.assertFalse(next_trial['used'])
 def test_failed_authoring_reports_zero_and_does_not_publish_fillers(self):
  from meme_generator.features.scheduled_authoring import run
  class Client:
   calls=0;tokens=0;model='test'
  image=Image.new('RGB',(128,128),'white');buf=BytesIO();image.save(buf,'PNG')
  candidates=[{'source_url':'https://public.example/'+str(i),'image_url':'https://public.example/'+str(i)+'.png','name':'source'} for i in range(3)]
  with patch('meme_generator.features.scheduled_authoring.fetch_candidate',return_value=buf.getvalue()),patch('meme_generator.features.scheduled_authoring.author',side_effect=ValueError('old face remains')):
   report=run(client=Client(),candidates=candidates,target=3,force=True)
  self.assertEqual(report['published'],0);self.assertEqual(report['status'],'attention')
  db=connect();self.assertEqual(db.execute('SELECT count(*) FROM templates').fetchone()[0],0);db.close()

 def test_observed_absolute_polygon_is_translated_exactly_and_bad_geometry_rejected(self):
  class Client:
   def vision(self,*a,**kw):return {'status':'ready','name':'face','intent':'preserve original scene','faces':[{'frames':[{'index':0,'box':[40,50,30,40],'erase_polygon':self.polygon}]}],'captions':[],'fixed_texts':[],'protected':[]}
  client=Client();client.polygon=[[40,50],[69,50],[69,89],[40,89]]
  with patch('meme_generator.features.minimax_authoring.local_proposals',return_value=[{'frame':0,'faces':[],'ocr_captions':[]}]):
   plan,_=request_plan(client,[Image.new('RGB',(128,128),'white')],[100],'face')
   self.assertEqual(plan.frames[0][0].erase_polygon,[(0,0),(29,0),(29,39),(0,39)])
   client.polygon=[[40,50],[200,50],[69,89]]
   with self.assertRaisesRegex(ValueError,'polygon must be local'):request_plan(client,[Image.new('RGB',(128,128),'white')],[100],'face')

 def test_unspecified_proposal_does_not_select_an_unrelated_haar_face(self):
  class Client:
   def vision(self,*a,**kw):return {'status':'ready','name':'face','intent':'preserve original scene','faces':[{'frames':[{'index':0,'box':[80,70,30,40]}]}],'captions':[],'fixed_texts':[],'protected':[]}
  measured=[{'frame':0,'faces':[{'kind':'person','inner_face_box':[10,10,40,40]}],'ocr_captions':[]}]
  with patch('meme_generator.features.minimax_authoring.local_proposals',return_value=measured):plan,_=request_plan(Client(),[Image.new('RGB',(128,128),'white')],[100],'face')
  self.assertEqual(plan.frames[0][0].box,(80,70,30,40))

 def test_fixed_source_contract_rejects_face_to_prop_caption_downgrade(self):
  class Client:
   def vision(self,*a,**kw):return {'status':'ready','name':'tea','intent':'change the cup label','faces':[],'captions':[{'text':'茶','frames':[{'index':0,'box':[80,90,20,20]}]}],'fixed_texts':[],'protected':[]}
  contract={'image_slots':1,'captions':[],'fixed_texts':['茶'],'intent':'replace original face, preserve cup'}
  with patch('meme_generator.features.minimax_authoring.local_proposals',return_value=[{'frame':0,'faces':[],'ocr_captions':[]}]):
   with self.assertRaisesRegex(ValueError,'cannot drop face replacement'):request_plan(Client(),[Image.new('RGB',(128,128),'white')],[100],'tea',contract=contract)

 def test_many_fixed_regions_compile_to_an_exact_bounded_mask_asset(self):
  class Client:
   def vision(self,*a,**kw):return {'status':'ready','name':'face','intent':'keep each fixed source detail','faces':[{'frames':[{'index':0,'box':[10,10,100,100]}]}],'captions':[],'fixed_texts':[],'protected':[{'frame':0,'name':'detail '+str(i),'box':[15+i*7,55,2,2]} for i in range(12)]}
  image=Image.new('RGB',(128,128),'white');out=BytesIO();image.save(out,'PNG')
  with patch('meme_generator.features.minimax_authoring.local_proposals',return_value=[{'frame':0,'faces':[],'ocr_captions':[]}]):plan,_=request_plan(Client(),[image],[100],'face')
  layer=plan.frames[0][0];self.assertTrue(layer.mask_asset);self.assertFalse(layer.protect_polygons)
  spec,assets,*_=local_validate(plan,out.getvalue(),[image],Image.new('RGB',(100,100),'blue'))
  self.assertIn(layer.mask_asset,assets)
  mask=Image.open(BytesIO(assets[layer.mask_asset]));self.assertEqual(mask.getpixel((5,45)),0);self.assertEqual(mask.getpixel((50,60)),255)

 def test_known_sources_do_not_spend_model_attempts_or_reintroduce_archived_art(self):
  from meme_generator.features.scheduled_authoring import run
  from meme_generator.features.quality import perceptual_hash
  import hashlib
  image=Image.new('RGB',(128,128),'white');out=BytesIO();image.save(out,'PNG');known=out.getvalue()
  row,_=self.template('old');meta=json.loads(row['metadata']);meta.update(original_hash=hashlib.sha256(known).hexdigest(),perceptual_hash=perceptual_hash(image));publish('old',meta,json.loads(row['spec']))
  fresh=image.copy();draw=ImageDraw.Draw(fresh)
  for i in range(0,128,8):draw.line((i,0,0,127-i),fill='black',width=4)
  out=BytesIO();fresh.save(out,'PNG');new=out.getvalue()
  candidates=[{'source_url':'https://public.example/same-page','image_url':'https://public.example/'+str(i)+'.png','name':'source'} for i in range(4)]
  class Client: calls=0;tokens=0
  with patch('meme_generator.features.scheduled_authoring.fetch_candidate',side_effect=[known,known,known,new]),patch('meme_generator.features.scheduled_authoring.author',side_effect=ValueError('pending')) as generate:
   report=run(client=Client(),candidates=candidates,force=True,target=3,max_attempts=1)
  self.assertEqual(report['scanned'],4);self.assertEqual(report['attempted'],1);self.assertEqual(generate.call_count,1);self.assertEqual(sum(r['status']=='duplicate' for r in report['results']),3)

 def test_retired_seed_does_not_undo_archived_state_and_legacy_state_is_repairable(self):
  self.template('one');store=self.store();archive_template('one',store)
  from meme_generator.features.seed import restore
  def text(path,*a,**kw):return json.dumps({'retired_keys':['one']} if path.name=='template_policy.json' else {'templates':[],'assets':{}})
  with patch('pathlib.Path.read_text',autospec=True,side_effect=text):restore(include_batches=False)
  db=connect();self.assertEqual(db.execute("SELECT status FROM templates WHERE key='one'").fetchone()[0],'archived')
  with db:db.execute("UPDATE templates SET status='withdrawn' WHERE key='one'")
  db.close();self.assertEqual(restore_template('one',store=store)['status'],'published')

 def test_public_blob_fallback_verifies_the_exact_immutable_github_object(self):
  from meme_generator.features.public_sources import fetch_candidate
  import hashlib
  raw=b'public image bytes';sha=hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
  response=json.dumps({'encoding':'base64','size':len(raw),'content':base64.b64encode(raw).decode()}).encode()
  item={'origin':'chinesebqb','source_blob_sha':sha,'image_url':'https://raw.githubusercontent.com/public-source'}
  with patch('meme_generator.features.public_sources.fetch_public',return_value=response):self.assertEqual(fetch_candidate(item),raw)
  with patch('meme_generator.features.public_sources.fetch_public',return_value=response):
   with self.assertRaisesRegex(SourceUnavailable,'hash_mismatch'):fetch_candidate({**item,'source_blob_sha':'a'*40})

 def test_failed_download_accounts_actual_bytes_instead_of_full_reservation(self):
  from meme_generator.features.public_sources import fetch_public
  failure=subprocess.CalledProcessError(28,['curl'],output=b'\n000')
  with patch('meme_generator.features.public_sources.validate_url',return_value=('public.example','93.184.216.34')),patch('meme_generator.features.public_sources.subprocess.run',side_effect=failure):
   with self.assertRaises(SourceUnavailable):fetch_public('https://public.example/image.png',1024)
  db=connect();self.assertEqual(db.execute('SELECT sum(bytes) FROM budgets').fetchone()[0],0);db.close()

 def test_separate_vlm_blocks_primary_model_false_positive_and_checks_every_frame(self):
  from meme_generator.features.minimax_authoring import cross_validate
  class Client:
   calls=0
   def cross_review(self,*a):self.calls+=1;return {'passed':self.calls<2,'old_face_fully_removed':self.calls<2,'caption_complete':True,'props_preserved':True,'reason':'original mouth remains'}
  client=Client();boards=[('frame 0',Image.new('RGB',(128,128))),('frame 1',Image.new('RGB',(128,128)))]
  with self.assertRaisesRegex(ValueError,'frame 1'):cross_validate(client,boards,{'image_slots':1,'captions':[]})
  self.assertEqual(client.calls,2)

 def test_unknown_emoji_geometry_cannot_be_approved_by_model_scores(self):
  from meme_generator.features.minimax_authoring import verify_face_geometry
  from meme_generator.features.declarative import Layer
  frames=[Image.new('RGB',(128,128),'white')];plans=[[Layer(type='face',box=[40,40,30,30])]]
  self.assertFalse(verify_face_geometry(plans,frames,[{'faces':[]}])['verified'])
  measured=[{'faces':[{'kind':'person','inner_face_box':[30,20,70,90],'feature_points':[[45,40],[80,40],[60,60],[45,85],[80,85]],'confidence':.99}]}]
  self.assertFalse(verify_face_geometry(plans,frames,measured)['verified'],'small mouth-only overlays must not pass')
  complete=[[Layer(type='face',box=[30,20,70,90])]]
  self.assertTrue(verify_face_geometry(complete,frames,measured)['verified'])

 def test_general_page_recommendations_cannot_inherit_the_main_meme_title(self):
  from meme_generator.features.public_sources import page_candidates
  html=b'<title>panda meme</title><meta property="og:image" content="https://public.example/panda.jpg"><img src="https://public.example/unrelated-portrait.jpg">'
  with patch('meme_generator.features.public_sources.fetch_public',return_value=html):rows=page_candidates('https://public.example/meme')
  self.assertEqual([r['image_url'] for r in rows],['https://public.example/panda.jpg'])

 def test_quality_hold_preserves_collection_without_model_calls_or_publication(self):
  from meme_generator.features.scheduled_authoring import run
  item={'image_url':'https://public.example/meme.jpg','source_url':'https://public.example/meme','name':'source'}
  def network_fetch(client):
   import sys
   subprocess.run([sys.executable,'-c','import fcntl,sys\nwith open(sys.argv[1],"a") as f: fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)',str(root()/'storage.lock')],check=True,capture_output=True,timeout=5)
   return [item],[]
  with patch.dict(os.environ,{'GENSTICKER_MINIMAX_ENABLED':'0'}),patch('meme_generator.features.scheduled_authoring.discover',side_effect=network_fetch),patch('meme_generator.features.scheduled_authoring.MiniMax',side_effect=AssertionError('must not call a model')):
   report=run()
  self.assertEqual(report['status'],'held-for-quality');self.assertEqual(report['new_candidate_metadata'],1);self.assertEqual(report['published'],0)
  db=connect();self.assertEqual(db.execute('SELECT status FROM candidates').fetchone()[0],'authoring-pending');self.assertEqual(db.execute('SELECT count(*) FROM templates').fetchone()[0],0);db.close()

 def test_publication_and_batch_membership_commit_together(self):
  row,_=self.template('one');spec=json.loads(row['spec']);meta=json.loads(row['metadata']);meta['name']='updated'
  publish('one',meta,spec,publication={'batch_id':'batch','score':94})
  db=connect();membership=db.execute("SELECT batch_id,score FROM template_publications WHERE key='one'").fetchone();self.assertEqual(tuple(membership),('batch',94))
  db.execute("CREATE TRIGGER reject_membership BEFORE INSERT ON template_publications BEGIN SELECT RAISE(ABORT, 'test failure'); END");db.commit();db.close()
  meta['name']='must roll back'
  with self.assertRaises(Exception):publish('two',meta,spec,publication={'batch_id':'batch','score':95})
  db=connect();self.assertFalse(db.execute("SELECT 1 FROM templates WHERE key='two'").fetchone());db.close()

 def test_monthly_report_keeps_verified_progress_when_network_failure_resumes(self):
  self.template('one','red');self.template('two','blue');db=connect()
  with db:db.execute("UPDATE templates SET status='withdrawn'")
  db.close();store=self.store();original=store.put;calls=0
  def first_only(*args,**kwargs):
   nonlocal calls
   calls+=1
   if calls>1:raise ArchiveError('archive_git_operation_failed:push')
   return original(*args,**kwargs)
  with patch.object(store,'put',side_effect=first_only):initial=monthly(store=store)
  self.assertEqual(initial['status'],'attention');self.assertEqual(len(initial['archived']),1)
  completed=monthly(store=store);self.assertEqual(completed['status'],'completed');self.assertEqual(len(completed['archived']),2);self.assertEqual(completed['remaining'],0);self.assertEqual(completed['before']['withdrawn'],2)


if __name__=='__main__':unittest.main()
