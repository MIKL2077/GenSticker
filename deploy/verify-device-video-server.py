"""Isolated end-to-end verification of device-safe GIF generation. No public publish."""
import hashlib,json,secrets,time,uuid,subprocess,tempfile,shutil
from io import BytesIO
from pathlib import Path
import httpx
from PIL import Image,ImageSequence
from meme_generator import account
from meme_generator.features import studio,livegif
from meme_generator.features.store import connect,root
from meme_generator.features.portrait import detectors

identifier='device_video_check_'+uuid.uuid4().hex;token=secrets.token_urlsafe(32)
db=account.connection()
with db:
 db.execute('INSERT INTO users(id,openid,name) VALUES(?,?,?)',(identifier,identifier,'独立视频验收账号'))
 db.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),identifier,int(time.time())+900))
db.close()
report={'checks':[],'identity':'isolated synthetic fixture, no real user data'}
out=Path('/tmp/gensticker-device-video-verification');out.mkdir(exist_ok=True)
def mark(name,**data):
 row={'name':name,**data};report['checks'].append(row);print(json.dumps(row,ensure_ascii=False),flush=True)
def request(client,method,path,**kwargs):
 r=client.request(method,path,**kwargs);r.raise_for_status();return r
def wait(client,path):
 deadline=time.time()+120
 while time.time()<deadline:
  job=request(client,'GET',path).json()
  if job['status'] not in ('queued','running'):return job
  time.sleep(.5)
 raise TimeoutError('worker timeout')
try:
 with tempfile.TemporaryDirectory() as temp,httpx.Client(base_url='http://127.0.0.1:3000/gensticker/api',headers={'Authorization':'Bearer '+token},timeout=70) as client:
  video=Path(temp)/'synthetic.mp4'
  subprocess.run(['ffmpeg','-nostdin','-v','error','-f','lavfi','-i','testsrc2=size=320x480:rate=15:duration=12','-c:v','libx264','-threads','2','-pix_fmt','yuv420p','-y',str(video)],check=True,timeout=30)
  hevc=Path(temp)/'synthetic-hevc.mp4'
  subprocess.run(['ffmpeg','-nostdin','-v','error','-i',str(video),'-t','3','-c:v','libx265','-x265-params','pools=1:frame-threads=1:log-level=error','-y',str(hevc)],check=True,timeout=30,stderr=subprocess.PIPE)
  buf=BytesIO();Image.new('RGB',(32,32),'red').save(buf,'JPEG');motion=buf.getvalue()+video.read_bytes()
  cases=[('long H264 selected interval',video.read_bytes(),'video.mp4',3,9),('HEVC phone codec',hevc.read_bytes(),'video.mov',0,3),('embedded Live motion automatic extraction',motion,'motion.jpg',2,3)]
  for name,raw,filename,start,duration in cases:
   started=time.monotonic();asset=request(client,'POST','/studio/live/assets',files={'file':(filename,raw,'application/octet-stream')}).json()
   payload={'asset_id':asset['asset_id'],'idempotency_key':uuid.uuid4().hex,'start':start,'duration':duration,'crop':[.1,.1,.45,.7],'rotation':90,'flip':True,'text':'动图验收'}
   job=request(client,'POST','/studio/live/jobs',json=payload).json()
   assert request(client,'POST','/studio/live/jobs',json=payload).json()['id']==job['id']
   assert any(item['id']==job['id'] for item in request(client,'GET','/studio/jobs').json())
   result=wait(client,'/studio/jobs/'+job['id']);assert result['status']=='completed',result
   output=request(client,'GET',result['result_url']).content;image=Image.open(BytesIO(output));frames=image.n_frames;total=sum(f.info.get('duration',0) for f in ImageSequence.Iterator(image))
   assert len(output)<=500*1024 and max(image.size)<=240 and frames>=2 and duration*1000-150<=total<=duration*1000+150
   mark(name,queued=True,frames=frames,duration_ms=total,bytes=len(output),size=list(image.size),elapsed_seconds=round(time.monotonic()-started,2))
  mark('portrait cascade models available',detectors=len(detectors()));assert len(detectors())>=2
  report['status']='passed'
except Exception as error:
 report['status']='failed';report['error']=str(error);raise
finally:
 db=studio.init();jobs=[dict(r) for r in db.execute('SELECT * FROM studio_jobs WHERE user_id=?',(identifier,))]
 active=any(j['status'] in ('queued','running') for j in jobs)
 if not active:
  with db:db.execute('DELETE FROM studio_views WHERE user_id=?',(identifier,));db.execute('DELETE FROM studio_jobs WHERE user_id=?',(identifier,))
  for job in jobs:
   (root()/'studio_results'/job['id']).unlink(missing_ok=True);(root()/'studio_replays'/(job['id']+'.json')).unlink(missing_ok=True)
  for path in livegif.directory().glob('*.json'):
   try:owned=json.loads(path.read_text()).get('user_id')==identifier
   except ValueError:continue
   if owned:
    for suffix in ('.json','.jpg','.media'):path.with_suffix(suffix).unlink(missing_ok=True)
  with db:
   if db.execute("SELECT 1 FROM sqlite_master WHERE name='generation_admissions'").fetchone():db.execute('DELETE FROM generation_admissions WHERE user_id=?',(identifier,))
  accounts=account.connection()
  with accounts:accounts.execute('DELETE FROM sessions WHERE user_id=?',(identifier,));accounts.execute('DELETE FROM users WHERE id=?',(identifier,))
  accounts.close()
 db.close();report['fixture_cleaned']=not active;(out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
