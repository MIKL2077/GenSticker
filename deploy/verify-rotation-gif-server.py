"""Run on the existing host: isolated fixture account, real worker, no publication."""
import hashlib,json,secrets,time,uuid
from io import BytesIO
from pathlib import Path
import httpx
from PIL import Image,ImageDraw
from meme_generator import account
from meme_generator.features import studio,livegif
from meme_generator.features.store import connect,root

out=Path('/tmp/gensticker-rotation-gif-verification');out.mkdir(exist_ok=True)
user='rotation_check_'+uuid.uuid4().hex;token=secrets.token_urlsafe(32)
db=account.connection()
with db:
 db.execute('INSERT INTO users(id,openid,name) VALUES(?,?,?)',(user,user,'独立验收账号'))
 db.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),user,int(time.time())+900))
db.close()
report={'identity':'isolated synthetic account; no real user impersonation','checks':[]}
def mark(name,**data):
 report['checks'].append({'name':name,**data});print(json.dumps(report['checks'][-1],ensure_ascii=False),flush=True)
def wait(client,path):
 deadline=time.time()+120
 while time.time()<deadline:
  r=client.get(path);r.raise_for_status();job=r.json()
  if job['status'] not in ('queued','running'):return job
  time.sleep(.5)
 raise TimeoutError('worker timeout')
def request(client,method,path,**kwargs):
 r=client.request(method,path,**kwargs);r.raise_for_status();return r
try:
 with httpx.Client(base_url='http://127.0.0.1:3000/gensticker/api',headers={'Authorization':'Bearer '+token},timeout=65) as client:
  image=Image.new('RGB',(360,480),'#fff5df');draw=ImageDraw.Draw(image);draw.ellipse((60,70,300,420),fill='#dd9867');draw.ellipse((100,180,125,210),fill='#253f45');draw.ellipse((220,180,245,210),fill='#253f45');draw.arc((110,230,240,330),0,180,fill='#253f45',width=6)
  buf=BytesIO();image.save(buf,'PNG')
  asset=request(client,'POST','/recommend/assets',files={'file':('fixture.png',buf.getvalue(),'image/png')}).json()['asset_id']
  batches=[];parent=None
  for index in range(4):
   payload={'idempotency_key':'verify-'+uuid.uuid4().hex}
   if parent and index!=3:payload['previous_job_id']=parent
   else:payload['asset_id']=asset
   r=request(client,'POST','/recommend/jobs',json=payload).json();assert request(client,'POST','/recommend/jobs',json=payload).json()['job_id']==r['job_id']
   job=wait(client,'/recommend/jobs/'+r['job_id']);assert job['status']=='completed',job
   keys={r['key'] for r in job['results']};assert len(keys)==9,job
   if batches:assert keys.isdisjoint(batches[-1]),(keys,batches[-1])
   batches.append(keys);parent=r['job_id'];mark('real nine-image batch',batch=index+1,keys=sorted(keys),previous_overlap=0)
  mark('variety across first three batches',unique_templates=len(set.union(*batches[:3])))
  frames=[]
  for i in range(20):
   frame=Image.new('RGB',(160,120),'#3d705c');ImageDraw.Draw(frame).ellipse((i*5,20,i*5+30,90),fill='#ffcf75');frames.append(frame)
  buf=BytesIO();frames[0].save(buf,'GIF',save_all=True,append_images=frames[1:],duration=100,loop=0);raw=buf.getvalue()
  params={'idempotency_key':'verify-local-'+uuid.uuid4().hex}
  job=request(client,'POST','/studio/live/results',files={'file':('local.gif',raw,'image/gif')},data=params).json()
  assert request(client,'POST','/studio/live/results',files={'file':('local.gif',raw,'image/gif')},data=params).json()['id']==job['id']
  result=wait(client,'/studio/jobs/'+job['id']);assert result['status']=='completed',result
  response=request(client,'GET',result['result_url']);assert response.content==raw
  assert request(client,'GET','/studio/unread').json()['count']==0
  assert httpx.get('http://127.0.0.1:3001'+result['result_url']).status_code==401
  mark('local GIF sync is byte-identical, private, idempotent and already viewed',bytes=len(raw),frames=len(frames))
  # Populate only the fixture identity's rolling ledger; leave all real users unchanged.
  db=connect()
  with db:
   used=db.execute('SELECT count(*) FROM generation_admissions WHERE user_id=?',(user,)).fetchone()[0]
   for i in range(8-used):db.execute('INSERT INTO generation_admissions VALUES(?,?,?)',(uuid.uuid4().hex,user,time.time()))
  db.close()
  limited=client.post('/recommend/jobs',json={'asset_id':asset,'idempotency_key':'verify-limited-'+uuid.uuid4().hex})
  assert limited.status_code==429,limited.text;assert int(limited.headers['retry-after'])>0
  mark('real API rolling abuse guard',status=limited.status_code,retry_after=int(limited.headers['retry-after']))
  report['status']='passed'
except Exception as error:
 report['status']='failed';report['error']=str(error);raise
finally:
 db=connect();jobs=[dict(r) for r in db.execute('SELECT * FROM jobs WHERE user_id=?',(user,))];assets=[dict(r) for r in db.execute('SELECT * FROM assets WHERE user_id=?',(user,))]
 with db:
  for name in ('results','job_variations','quotas','cost_ledger'):
   db.execute(f'DELETE FROM {name} WHERE job_id IN (SELECT id FROM jobs WHERE user_id=?)',(user,))
  for name in ('jobs','assets','events','preferences','feedback_history','generation_admissions'):
   if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone():db.execute(f'DELETE FROM {name} WHERE user_id=?',(user,))
 db.close()
 import shutil
 shutil.rmtree(root()/'private'/user,ignore_errors=True)
 for asset in assets:(root()/'history_thumbs'/(asset['id']+'.jpg')).unlink(missing_ok=True)
 db=studio.init();jobs=[dict(r) for r in db.execute('SELECT * FROM studio_jobs WHERE user_id=?',(user,))]
 with db:
  db.execute('DELETE FROM studio_views WHERE user_id=?',(user,));db.execute('DELETE FROM studio_jobs WHERE user_id=?',(user,))
 db.close()
 for job in jobs:
  (root()/'studio_results'/job['id']).unlink(missing_ok=True);(root()/'studio_replays'/(job['id']+'.json')).unlink(missing_ok=True)
 for path in livegif.directory().glob('*.json'):
  if json.loads(path.read_text()).get('user_id')==user:
   for suffix in ('.json','.jpg','.media'):(path.with_suffix(suffix)).unlink(missing_ok=True)
 db=account.connection()
 with db:db.execute('DELETE FROM sessions WHERE user_id=?',(user,));db.execute('DELETE FROM users WHERE id=?',(user,))
 db.close();report['fixture_cleaned']=True;(out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
