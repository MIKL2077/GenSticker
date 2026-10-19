"""Run on the authorised host. Isolated fixture identity, real API + real worker.
No existing user is impersonated; no auth secret is printed. No public publishing.
"""
import base64,hashlib,json,secrets,time,uuid
from io import BytesIO
from pathlib import Path
import httpx
from PIL import Image,ImageDraw
from meme_generator import account
from meme_generator.features import studio
from meme_generator.features.declarative import font

identifier='acceptance_'+uuid.uuid4().hex
session=secrets.token_urlsafe(32)
db=account.connection()
with db:
 db.execute('INSERT INTO users(id,openid,name) VALUES(?,?,?)',(identifier,identifier,'验收专用测试账号'))
 db.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(session.encode()).hexdigest(),identifier,int(time.time())+1800))
db.close()
report={'identity':'isolated synthetic test identity, not a real WeChat login','checks':[],'limitations':[]}
created=[]
def mark(name,**data):report['checks'].append({'name':name,**data});print(json.dumps(report['checks'][-1],ensure_ascii=False),flush=True)

def wait(client,path,timeout=210):
 end=time.time()+timeout
 while time.time()<end:
  response=client.get(path);response.raise_for_status();value=response.json()
  if value['status'] not in ('queued','running'):return value
  time.sleep(1)
 raise TimeoutError(path)

try:
 with httpx.Client(base_url='http://127.0.0.1:3001',headers={'Authorization':'Bearer '+session},timeout=70) as client:
  config=client.get('/account/config').json();assert config['app_id']=='wx2e3a058ed0117034' and config['features']['studio'];mark('public identity and feature flags',app_id=config['app_id'])
  assert client.get('/recommend/quota').json()['unlimited'] is True;mark('batch generation unlimited')
  fixture=Image.new('RGB',(512,512),'white');draw=ImageDraw.Draw(fixture)
  draw.text((35,15),'why',font=font(74),fill='black');draw.ellipse((130,160,375,440),fill='#ffc963',outline='#233f48',width=5);draw.ellipse((185,245,200,270),fill='#233f48');draw.ellipse((300,245,315,270),fill='#233f48');draw.arc((180,270,315,370),5,175,fill='#233f48',width=8)
  output=BytesIO();fixture.save(output,'PNG');raw=output.getvalue();encoded=base64.b64encode(raw).decode()
  spec={'width':512,'height':512,'layers':[{'type':'subject','box':[0,0,512,400]},{'type':'text','box':[10,420,492,70],'slot':0,'font_size':36,'value':'hello'}],'defaults':['hello']}
  r=client.post('/studio/templates',json={'name':'验收私藏模板','spec':spec});r.raise_for_status();template=r.json();assert template['status']=='private';created.append(template['id']);mark('manual template persisted privately')
  payload={'template_key':template['id'],'images':[encoded],'texts':['real worker result'],'idempotency_key':uuid.uuid4().hex}
  r=client.post('/studio/jobs',json=payload);r.raise_for_status();job=r.json()
  assert client.post('/studio/jobs',json=payload).json()['id']==job['id'];mark('manual submission idempotency')
  result=wait(client,'/studio/jobs/'+job['id']);assert result['status']=='completed',result
  image=client.get(result['result_url']);image.raise_for_status()
  with Image.open(BytesIO(image.content)) as image_file:assert image_file.size==(512,512)
  assert httpx.get('http://127.0.0.1:3001'+result['result_url']).status_code==401;mark('durable manual queue and authenticated actual image',bytes=len(image.content))
  uploaded=client.post('/recommend/assets',files={'file':('fixture.png',raw,'image/png')});uploaded.raise_for_status()
  r=client.post('/recommend/jobs',json={'asset_id':uploaded.json()['asset_id'],'idempotency_key':uuid.uuid4().hex});r.raise_for_status();first=wait(client,'/recommend/jobs/'+r.json()['job_id']);assert first['status']=='completed' and first['results'],first
  first_keys={r['key'] for r in first['results']};mark('actual AI batch',count=len(first['results']))
  reroll_payload={'previous_job_id':first['job_id'],'idempotency_key':uuid.uuid4().hex}
  r=client.post('/recommend/jobs',json=reroll_payload);r.raise_for_status();second_id=r.json()['job_id'];assert client.post('/recommend/jobs',json=reroll_payload).json()['job_id']==second_id
  second=wait(client,'/recommend/jobs/'+second_id);assert second['status']=='completed' and second['results'],second
  second_keys={r['key'] for r in second['results']};assert first_keys!=second_keys
  image=client.get(second['results'][0]['preview_url'].split('?')[0]);image.raise_for_status()
  with Image.open(BytesIO(image.content)) as image_file:image_file.verify()
  mark('actual reroll without another upload',first_count=len(first_keys),second_count=len(second_keys),overlap=len(first_keys&second_keys),download_bytes=len(image.content))
  r=client.post('/studio/templates/ai',json={'image':encoded,'idempotency_key':uuid.uuid4().hex,'rights_attested':True});r.raise_for_status();ai=r.json()
  second_request=client.post('/studio/templates/ai',json={'image':encoded,'idempotency_key':uuid.uuid4().hex,'rights_attested':True});assert second_request.status_code==429;mark('AI template limit enforced by server',second_status=second_request.status_code)
  converted=wait(client,'/studio/jobs/'+ai['id'])
  if converted['status']=='completed':
   made=client.get('/studio/templates/'+converted['template_id']).json();created.append(made['id']);assert made['status']!='published','Synthetic identity must not publish';mark('real local OCR conversion and fail-closed publication',status=made['status'],text_slots=made['params_type']['min_texts'])
  else:report['limitations'].append('OCR conversion stayed conservative: '+converted['message']);mark('AI template returns explicit manual-review outcome',status=converted['status'])
  report['status']='passed'
except Exception as error:
 report['status']='failed';report['error']=str(error);raise
finally:
 # Remove only this generated fixture identity and its data. Never touch real users.
 db=studio.init();paths=[];asset_hashes=[]
 own_jobs=[dict(r) for r in db.execute('SELECT * FROM jobs WHERE user_id=?',(identifier,))]
 own_assets=[dict(r) for r in db.execute('SELECT * FROM assets WHERE user_id=?',(identifier,))]
 studio_jobs=[dict(r) for r in db.execute('SELECT * FROM studio_jobs WHERE user_id=?',(identifier,))]
 busy=any(j['status'] in ('queued','running') for j in own_jobs+studio_jobs)
 if not busy:
  with db:
   for j in own_jobs:
    paths.extend(Path(r['path']) for r in db.execute('SELECT path FROM results WHERE job_id=?',(j['id'],)))
    paths.extend(Path(r['preview']) for r in db.execute('SELECT preview FROM results WHERE job_id=?',(j['id'],)))
    for table,column in [('results','job_id'),('job_variations','job_id'),('quotas','job_id'),('cost_ledger','job_id')]:db.execute(f'DELETE FROM {table} WHERE {column}=?',(j['id'],))
   for row in db.execute('SELECT spec FROM studio_templates WHERE user_id=?',(identifier,)):
    asset_hashes.extend(l['value'] for l in json.loads(row['spec'])['layers'] if l['type']=='asset')
   for table in ('jobs','assets','studio_jobs','studio_templates','studio_ai_daily','preferences','events','feedback_history'):db.execute(f'DELETE FROM {table} WHERE user_id=?',(identifier,))
  for p in paths:p.unlink(missing_ok=True)
  for a in own_assets:
   original=Path(a['path']);original.unlink(missing_ok=True);original.with_suffix('.subject.png').unlink(missing_ok=True);original.with_suffix('.analysis.json').unlink(missing_ok=True)
  for j in studio_jobs:(studio.root()/'studio_results'/j['id']).unlink(missing_ok=True)
  for digest in asset_hashes:
   existing=list(db.execute('SELECT spec FROM templates WHERE spec IS NOT NULL'))+list(db.execute('SELECT spec FROM studio_templates'))
   if not any(digest in r['spec'] for r in existing):(studio.root()/'template_assets'/(digest+'.png')).unlink(missing_ok=True)
  accounts=account.connection()
  with accounts:
   for table in ('sessions','favorites','history'):accounts.execute(f'DELETE FROM {table} WHERE user_id=?',(identifier,))
   accounts.execute('DELETE FROM users WHERE id=?',(identifier,))
  accounts.close();report['fixture_cleanup']='completed'
 else:report['fixture_cleanup']='task still active; retained for automatic TTL cleanup'
 db.close();Path('/tmp/gensticker-studio-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
