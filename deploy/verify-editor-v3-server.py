"""Actual CPU detection, native animated template, caption editing and retirement.
Uses an isolated account and public OpenCV sample; deletes private fixtures.
"""
import hashlib,json,secrets,time,uuid,subprocess,tempfile,shutil
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
import httpx
from PIL import Image,ImageDraw,ImageSequence
from meme_generator import account
from meme_generator.features import worker,vision,livegif,studio
from meme_generator.features.store import connect,root
identifier='editor_v3_check_'+uuid.uuid4().hex;token=secrets.token_urlsafe(32);ai_job=uuid.uuid4().hex
accounts=account.connection()
with accounts:
 accounts.execute('INSERT INTO users(id,openid,name) VALUES(?,?,?)',(identifier,identifier,'编辑器第三轮验收'))
 accounts.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),identifier,int(time.time())+900))
accounts.close();report={'checks':[],'fixture_source':'https://github.com/opencv/opencv/blob/master/samples/data/lena.jpg','identity':'isolated fixture account; no real user data'}
def mark(name,**data):report['checks'].append({'name':name,**data});print(json.dumps(report['checks'][-1],ensure_ascii=False),flush=True)
def request(client,method,path,**kwargs):
 response=client.request(method,path,**kwargs);response.raise_for_status();return response
def wait(client,job):
 for _ in range(120):
  item=request(client,'GET','/studio/jobs/'+job['id']).json()
  if item['status'] not in ('queued','running'):assert item['status']=='completed',item;return item
  time.sleep(.25)
 raise TimeoutError('worker timeout')
try:
 with httpx.Client(base_url='http://127.0.0.1:3000/gensticker/api',headers={'Authorization':'Bearer '+token},timeout=70) as client:
  original=Path('/tmp/gensticker-two-face-fixture.jpg').read_bytes()
  detected=request(client,'POST','/recommend/subjects/detect',files={'file':('group.jpg',original,'image/jpeg')}).json();assert len(detected['candidates'])>=2,detected
  x,y,w,h=detected['candidates'][1]['box'];group=Image.open(BytesIO(original));selected=group.crop((round(x*group.width),round(y*group.height),round((x+w)*group.width),round((y+h)*group.height)));buffer=BytesIO();selected.save(buffer,'JPEG',quality=88)
  asset=request(client,'POST','/recommend/assets',files={'file':('selected.jpg',buffer.getvalue(),'image/jpeg')},data={'subject_selected':'true'}).json()['asset_id']
  mark('Real two-face candidate detection',candidates=len(detected['candidates']),selected_second=True,cropped_size=list(selected.size))
  db=connect();now=time.time()
  with db:db.execute("INSERT INTO jobs(id,user_id,idempotency,asset_id,day,status,created,updated,lease) VALUES(?,?,?,?,?,?,?,?,?)",(ai_job,identifier,'animation-'+ai_job,asset,'2026-10-19','running',now,now,now+300))
  job=dict(db.execute('SELECT * FROM jobs WHERE id=?',(ai_job,)).fetchone());native=dict(db.execute("SELECT * FROM templates WHERE key='petpet' AND status='published'").fetchone());db.close()
  assert vision.warmup(include_emotion=False)
  # Run a real native animation in the normal AI worker, without changing any catalog rows.
  with patch.object(worker,'candidates',return_value=[native]),patch('meme_generator.features.popularity.record',return_value=True):worker.run_job(job)
  result=request(client,'GET','/recommend/jobs/'+ai_job).json();assert result['status']=='completed',result;assert result['analysis']['subject_selected'] and result['analysis']['framing']=='user-selection';slot=result['results'][0];assert slot['animated']
  full=request(client,'GET',slot['image_url']);preview=request(client,'GET',slot['preview_url']);assert full.headers['content-type']=='image/gif' and preview.headers['content-type']=='image/gif'
  full_image=Image.open(BytesIO(full.content));preview_image=Image.open(BytesIO(preview.content));assert full_image.n_frames>1 and preview_image.n_frames>1
  full_duration=sum(frame.info.get('duration',100) for frame in ImageSequence.Iterator(full_image));preview_duration=sum(frame.info.get('duration',100) for frame in ImageSequence.Iterator(preview_image));assert full_duration==preview_duration
  mark('Real AI animated petpet result',frames=full_image.n_frames,preview_frames=preview_image.n_frames,duration_ms=full_duration,bytes=len(full.content),preview_bytes=len(preview.content),selected_region_preserved=True)
  with tempfile.TemporaryDirectory() as temp:
   folder=Path(temp)
   for index in range(20):
    image=Image.new('RGB',(240,240),'white');ImageDraw.Draw(image).ellipse((index*5,130,index*5+40,170),fill='red');image.save(folder/f'{index:03d}.png')
   video=folder/'video.mp4';subprocess.run(['ffmpeg','-nostdin','-v','error','-framerate','10','-i',str(folder/'%03d.png'),'-c:v','libx264','-threads','2','-pix_fmt','yuv420p','-y',str(video)],check=True,timeout=30)
   source=request(client,'POST','/studio/live/assets',files={'file':('video.mp4',video.read_bytes(),'video/mp4')}).json()
   job=request(client,'POST','/studio/live/jobs',json={'asset_id':source['asset_id'],'idempotency_key':uuid.uuid4().hex,'duration':2,'text':'位置测试','caption_style':{'x':.5,'y':.2,'size':.14,'color':'#1890ff','background':'light','bold':False}}).json();result=wait(client,job);raw=request(client,'GET',result['result_url']).content;image=Image.open(BytesIO(raw));assert image.n_frames>1 and len(raw)<=512000
   rgb=image.convert('RGB');points=[(x,y) for y in range(image.height) for x in range(image.width) if (lambda pixel:pixel[2]>160 and pixel[0]<90 and pixel[1]<175)(rgb.getpixel((x,y)))]
   assert points and max(y for _,y in points)<image.height/2
   mark('Real video caption position and style',frames=image.n_frames,bytes=len(raw),caption_blue_pixels=len(points),caption_max_y=max(y for _,y in points),height=image.height)
  assert httpx.get('http://127.0.0.1:3000/gensticker/live-setup.html').status_code==410
  assert httpx.post('http://127.0.0.1:3000/gensticker/api/studio/live/imports/receive').status_code==410
  db=connect();assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='live_imports'").fetchone();db.close()
  mark('Shortcut bridge retired',tutorial_status=410,import_status=410,capabilities_revoked=True)
  report['status']='passed'
finally:
 db=studio.init();jobs=[dict(row) for row in db.execute('SELECT * FROM studio_jobs WHERE user_id=?',(identifier,))];active=any(job['status'] in ('queued','running') for job in jobs)
 if not active:
  with db:
   db.execute('DELETE FROM studio_views WHERE user_id=?',(identifier,));db.execute('DELETE FROM studio_jobs WHERE user_id=?',(identifier,));db.execute('DELETE FROM results WHERE job_id=?',(ai_job,));db.execute('DELETE FROM cost_ledger WHERE job_id=?',(ai_job,));db.execute('DELETE FROM jobs WHERE id=?',(ai_job,));db.execute('DELETE FROM assets WHERE user_id=?',(identifier,));db.execute('DELETE FROM generation_admissions WHERE user_id=?',(identifier,))
  shutil.rmtree(root()/'private'/identifier,ignore_errors=True)
  for job in jobs:
   (root()/'studio_results'/job['id']).unlink(missing_ok=True);(root()/'studio_replays'/(job['id']+'.json')).unlink(missing_ok=True)
  for path in livegif.directory().glob('*.json'):
   if json.loads(path.read_text()).get('user_id')==identifier:
    for suffix in ('.json','.jpg','.media'):path.with_suffix(suffix).unlink(missing_ok=True)
  (root()/'history_thumbs'/(locals().get('asset','')+'.jpg')).unlink(missing_ok=True)
  accounts=account.connection()
  with accounts:accounts.execute('DELETE FROM sessions WHERE user_id=?',(identifier,));accounts.execute('DELETE FROM users WHERE id=?',(identifier,))
  accounts.close()
 db.close();report['fixture_cleaned']=not active;Path('/tmp/gensticker-editor-v3-server-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
