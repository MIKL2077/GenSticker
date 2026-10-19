"""Private synthetic bridge + preencoded GIF queue smoke test; no real user data."""
import hashlib,json,secrets,time,uuid,subprocess,tempfile
from io import BytesIO
from pathlib import Path
import httpx
from PIL import Image,ImageSequence
from meme_generator import account
from meme_generator.features import livegif,studio,live_import
from meme_generator.features.store import root
identifier='local_live_check_'+uuid.uuid4().hex;token=secrets.token_urlsafe(32)
db=account.connection()
with db:
 db.execute('INSERT INTO users(id,openid,name) VALUES(?,?,?)',(identifier,identifier,'Live 直连验收'))
 db.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),identifier,int(time.time())+900))
db.close();report={'checks':[],'identity':'isolated synthetic fixture; no real user data'}
def mark(name,**data):report['checks'].append({'name':name,**data});print(json.dumps(report['checks'][-1],ensure_ascii=False),flush=True)
def request(client,method,path,**kwargs):
 response=client.request(method,path,**kwargs);response.raise_for_status();return response
def wait(client,job):
 for _ in range(120):
  result=request(client,'GET','/studio/jobs/'+job['id']).json()
  if result['status'] not in ('queued','running'):assert result['status']=='completed',result;return result
  time.sleep(.25)
 raise TimeoutError('worker did not finish')
try:
 with tempfile.TemporaryDirectory() as temp,httpx.Client(base_url='http://127.0.0.1:3000/gensticker/api',headers={'Authorization':'Bearer '+token},timeout=70) as client:
  video=Path(temp)/'synthetic.mp4';subprocess.run(['ffmpeg','-nostdin','-v','error','-f','lavfi','-i','testsrc2=size=480x320:rate=10:duration=2','-c:v','libx264','-threads','2','-pix_fmt','yuv420p','-y',str(video)],check=True,timeout=30)
  pair=request(client,'POST','/studio/live/imports').json()
  assert request(client,'GET','/studio/live/imports/'+pair['id']).json()['status']=='waiting'
  sent=httpx.post(str(client.base_url).rstrip('/')+'/studio/live/imports/receive',content=video.read_bytes(),headers={'X-Live-Import':pair['token']},timeout=60);assert sent.status_code==201,sent.text
  again=httpx.post(str(client.base_url).rstrip('/')+'/studio/live/imports/receive',content=b'unused',headers={'X-Live-Import':pair['token']});assert again.status_code==409,again.text
  received=request(client,'GET','/studio/live/imports/'+pair['id']).json();asset=received['asset'];assert received['status']=='ready'
  downloaded=request(client,'GET','/studio/live/imports/'+pair['id']+'/media').content;assert downloaded==video.read_bytes()
  assert httpx.get(str(client.base_url).rstrip('/')+'/studio/live/imports/'+pair['id']+'/media').status_code==401
  mark('Live capability bridge',account_credential_sent_by_shortcut=False,one_use=True,authenticated_download=True,bytes=len(downloaded),duration=asset['duration'])
  job=request(client,'POST','/studio/live/jobs',json={'asset_id':asset['asset_id'],'idempotency_key':uuid.uuid4().hex,'start':0,'duration':2,'crop':[.1,.1,.8,.8],'rotation':90,'flip':True,'text':'Live 直连'}).json();result=wait(client,job)
  raw=request(client,'GET',result['result_url']).content;im=Image.open(BytesIO(raw));assert len(raw)<=512000 and im.n_frames>1
  mark('Imported Live edits finish in durable queue',frames=im.n_frames,bytes=len(raw),size=list(im.size))
  local_raw=Path('/tmp/gensticker-local-first-browser.gif').read_bytes();key=uuid.uuid4().hex
  job=request(client,'POST','/studio/live/results',files={'file':('local.gif',local_raw,'image/gif')},data={'idempotency_key':key}).json()
  again=request(client,'POST','/studio/live/results',files={'file':('local.gif',local_raw,'image/gif')},data={'idempotency_key':key}).json();assert again['id']==job['id']
  result=wait(client,job);assert request(client,'GET',result['result_url']).content==local_raw
  unread=request(client,'GET','/studio/unread').json()['count'];assert unread==2,unread
  request(client,'POST','/studio/jobs/'+job['id']+'/view');assert request(client,'GET','/studio/unread').json()['count']==1
  mark('Browser local GIF cloud sync',bytes=len(local_raw),idempotent=True,byte_identical=True,unread_until_viewed=True)
  guide=httpx.get('http://127.0.0.1:3000/gensticker/live-setup.html');assert guide.status_code==200 and 'X-Live-Import' in guide.text;mark('Setup guide hosted',content_type=guide.headers['content-type'])
  report['status']='passed'
finally:
 db=studio.init();jobs=[dict(r) for r in db.execute('SELECT * FROM studio_jobs WHERE user_id=?',(identifier,))];active=any(j['status'] in ('queued','running') for j in jobs)
 if not active:
  with db:
   db.execute('DELETE FROM studio_views WHERE user_id=?',(identifier,));db.execute('DELETE FROM studio_jobs WHERE user_id=?',(identifier,));db.execute('DELETE FROM live_imports WHERE user_id=?',(identifier,));db.execute('DELETE FROM generation_admissions WHERE user_id=?',(identifier,))
  for job in jobs:
   (root()/'studio_results'/job['id']).unlink(missing_ok=True);(root()/'studio_replays'/(job['id']+'.json')).unlink(missing_ok=True)
  for path in livegif.directory().glob('*.json'):
   if json.loads(path.read_text()).get('user_id')==identifier:
    for suffix in ('.json','.jpg','.media'):path.with_suffix(suffix).unlink(missing_ok=True)
  accounts=account.connection()
  with accounts:accounts.execute('DELETE FROM sessions WHERE user_id=?',(identifier,));accounts.execute('DELETE FROM users WHERE id=?',(identifier,))
  accounts.close()
 db.close();report['fixture_cleaned']=not active;Path('/tmp/gensticker-local-live-server-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
