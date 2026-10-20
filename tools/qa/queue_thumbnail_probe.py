"""Bounded on-host queue acceptance; synthetic accounts only, never publishes."""
import argparse,base64,hashlib,json,secrets,shutil,time,uuid
from io import BytesIO
from pathlib import Path
import httpx
from PIL import Image,ImageSequence
from meme_generator import account
from meme_generator.features.lifecycle import Deletion,delete_account
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--allow-fixtures',action='store_true');p.add_argument('--output',required=True);a=p.parse_args()
if not a.allow_fixtures:raise SystemExit('Explicit fixture authorization required')
if shutil.disk_usage('/var/lib/gensticker').free<10*1024**3:raise SystemExit('Low disk: no fixtures submitted')
users=[];tokens=[];report={'status':'running','samples':[],'publishes':0}
def request(client,method,url,status=200,**kwargs):
 start=time.perf_counter();r=client.request(method,url,**kwargs);assert r.status_code==status,(url,r.status_code,r.text[:80]);return r,round((time.perf_counter()-start)*1000,3)
try:
 for _ in range(2):
  user='queue_qa_'+uuid.uuid4().hex;token=secrets.token_urlsafe(32);db=account.connection()
  with db:
   db.execute('INSERT INTO users(id,openid,name) VALUES(?,?,?)',(user,user,'Synthetic queue QA'));db.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),user,int(time.time())+1800))
  db.close();users.append(user);tokens.append(token)
 buf=BytesIO();Image.effect_noise((400,500),70).convert('RGB').save(buf,'PNG');encoded=base64.b64encode(buf.getvalue()).decode()
 with httpx.Client(base_url='http://127.0.0.1:3001',headers={'Authorization':'Bearer '+tokens[0]},timeout=30) as c,httpx.Client(base_url='http://127.0.0.1:3001',headers={'Authorization':'Bearer '+tokens[1]},timeout=15) as other:
  for key in ['always','petpet']:
   job,_=request(c,'POST','/studio/jobs',201,json={'template_key':key,'images':[encoded],'texts':[],'idempotency_key':uuid.uuid4().hex});identifier=job.json()['id'];deadline=time.time()+60
   while time.time()<deadline:
    state=request(c,'GET','/studio/jobs/'+identifier)[0].json()
    if state['status']=='completed':break
    assert state['status'] in ['queued','running'];time.sleep(.2)
   else:raise TimeoutError('worker queue')
   original,original_ms=request(c,'GET',state['result_url']);thumb,cold_ms=request(c,'GET','/studio/jobs/'+identifier+'/thumbnail');warm,warm_ms=request(c,'GET','/studio/jobs/'+identifier+'/thumbnail');assert thumb.content==warm.content
   with Image.open(BytesIO(thumb.content)) as im:assert im.format=='JPEG' and max(im.size)<=144 and getattr(im,'n_frames',1)==1
   with Image.open(BytesIO(original.content)) as im:frames=getattr(im,'n_frames',1)
   request(other,'GET','/studio/jobs/'+identifier+'/thumbnail',404)
   report['samples'].append({'template':key,'original_bytes':len(original.content),'original_frames':frames,'thumbnail_bytes':len(thumb.content),'original_ms':original_ms,'thumbnail_cold_ms':cold_ms,'thumbnail_warm_ms':warm_ms})
   request(c,'DELETE','/studio/jobs/'+identifier,204);request(c,'GET','/studio/jobs/'+identifier+'/thumbnail',404)
  _,ms=request(c,'GET','/studio/jobs');report['empty_metadata_ms']=ms
  report['ownership_and_deletion']='passed';report['status']='passed'
except Exception as e:report['status']='failed';report['error']=str(e);raise
finally:
 cleaned=True
 for user in users:
  try:delete_account(Deletion(confirmation='注销账号'),{'id':user})
  except Exception:cleaned=False
 report['fixture_cleaned']=cleaned;Path(a.output).write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
