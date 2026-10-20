"""Bounded production checks for lifecycle, exports and video quality.
Requires explicit --allow-fixtures. Creates synthetic accounts only, never publishes.
Run with the same private config/state as the API, as its service user.
"""
import argparse,base64,hashlib,json,os,secrets,shutil,subprocess,tempfile,time,uuid
from io import BytesIO
from pathlib import Path
import httpx
from PIL import Image,ImageSequence
from meme_generator import account
from meme_generator.features.lifecycle import Deletion,delete_account

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--allow-fixtures',action='store_true');p.add_argument('--output',required=True)
a=p.parse_args()
if not a.allow_fixtures:raise SystemExit('Explicit fixture authorization required')
if os.getloadavg()[0]>3.5 or shutil.disk_usage('/var/lib/gensticker').free<10*1024**3:raise SystemExit('Shared host resource guard')
users=[];tokens=[];report={'status':'running','checks':[],'videos':[],'publishes':0}
def check(name):report['checks'].append(name)
def request(c,method,url,status=200,**kwargs):
 r=c.request(method,url,**kwargs)
 assert r.status_code==status,(method,url,status,r.status_code,r.text[:100])
 return r
try:
 for _ in range(2):
  u='remediation_qa_'+uuid.uuid4().hex;t=secrets.token_urlsafe(32);db=account.connection()
  with db:
   db.execute('INSERT INTO users(id,openid,name) VALUES(?,?,?)',(u,u,'Synthetic remediation QA'))
   db.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(t.encode()).hexdigest(),u,int(time.time())+1800))
  db.close();users.append(u);tokens.append(t)
 with httpx.Client(base_url='http://127.0.0.1:3001',headers={'Authorization':'Bearer '+tokens[0]},timeout=40) as c,httpx.Client(base_url='http://127.0.0.1:3001',headers={'Authorization':'Bearer '+tokens[1]},timeout=20) as other:
  usage=request(c,'GET','/account/storage').json();assert usage['limit_bytes']==268435456 and usage['template_limit']==100;check('configured-storage-budget')
  frames=[Image.new('RGB',(480,360),color) for color in ['red','green','blue']];buf=BytesIO();frames[0].save(buf,'GIF',save_all=True,append_images=frames[1:],duration=[100,200,300],loop=0)
  exported=request(c,'POST','/images/wechat-export',json={'image':base64.b64encode(buf.getvalue()).decode()})
  with Image.open(BytesIO(exported.content)) as image:
   assert image.n_frames==3 and max(image.size)<=240 and len(exported.content)<=512000
   assert sum(f.info.get('duration',0) for f in ImageSequence.Iterator(image))==600
  check('wechat-export-preserves-duration-with-size-budget')
  request(c,'POST','/memes/petpet/generate',422,json={'images':[],'texts':[],'args':{'user_infos':[{'name':'X'}]*11}});check('generator-user-info-bound')
  spec={'width':256,'height':256,'layers':[{'type':'text','box':[10,10,230,60],'slot':0,'value':'QA'}],'defaults':['QA']}
  template=request(c,'POST','/studio/templates',201,json={'name':'Synthetic private QA','spec':spec}).json();key=template['id']
  request(other,'DELETE','/studio/templates/'+key,404)
  request(c,'POST','/studio/templates/'+key+'/withdraw');request(c,'DELETE','/studio/templates/'+key,204);request(c,'GET','/studio/templates/'+key,404);check('private-template-owner-delete-withdraw')
  request(c,'POST','/templates/reports',201,json={'key':'petpet','reason':'Synthetic remediation test; removed with test account','event_id':uuid.uuid4().hex});check('authenticated-report')
  with tempfile.TemporaryDirectory(prefix='gensticker-quality-') as temp:
   video=Path(temp)/'sample.mp4'
   subprocess.run(['ffmpeg','-nostdin','-v','error','-f','lavfi','-i','testsrc2=size=240x320:rate=12','-t','3','-c:v','libx264','-threads','1','-pix_fmt','yuv420p','-y',str(video)],check=True,timeout=20)
   asset=request(c,'POST','/studio/live/assets',201,files={'file':('qa.mp4',video.read_bytes(),'video/mp4')}).json()['asset_id']
   assert any(v['id']==asset for v in request(c,'GET','/studio/live/assets').json())
   request(other,'DELETE','/studio/live/assets/'+asset,404)
   for quality in ['smooth','clear']:
    start=time.perf_counter();job=request(c,'POST','/studio/live/jobs',201,json={'asset_id':asset,'idempotency_key':uuid.uuid4().hex,'start':0,'duration':3,'quality':quality}).json()
    deadline=time.time()+60
    while time.time()<deadline:
     result=request(c,'GET','/studio/jobs/'+job['id']).json()
     if result['status']=='completed':break
     assert result['status'] in ['queued','running'],result['status'];time.sleep(.3)
    else:raise TimeoutError('video quality worker')
    raw=request(c,'GET',result['result_url']).content
    with Image.open(BytesIO(raw)) as im:
     duration=sum(f.info.get('duration',0) for f in ImageSequence.Iterator(im))
     assert 2900<=duration<=3100 and max(im.size)<=240 and len(raw)<=512000
     report['videos'].append({'quality':quality,'seconds':round(time.perf_counter()-start,3),'frames':im.n_frames,'duration_ms':duration,'bytes':len(raw)})
   request(c,'DELETE','/studio/live/assets/'+asset,204);assert not request(c,'GET','/studio/live/assets').json();check('quality-modes-and-owner-video-delete')
  request(c,'DELETE','/account',204,json={'confirmation':'注销账号'});request(c,'GET','/auth/me',401);check('account-deletion-revokes-session')
 report['status']='passed'
except Exception as error:
 report['status']='failed';report['error']=str(error);raise
finally:
 cleaned=True
 for user in users:
  db=account.connection();exists=db.execute('SELECT 1 FROM users WHERE id=?',(user,)).fetchone();db.close()
  if exists:
   try:delete_account(Deletion(confirmation='注销账号'),{'id':user})
   except Exception:cleaned=False
 report['fixture_cleaned']=cleaned
 Path(a.output).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(report,ensure_ascii=False),flush=True)
