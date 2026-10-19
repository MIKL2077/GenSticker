"""Real API/worker verification, isolated fixture account, no public posting."""
import base64,hashlib,json,secrets,time,uuid
from io import BytesIO
from pathlib import Path
import httpx
from PIL import Image,ImageDraw
from meme_generator import account
from meme_generator.features import studio,livegif

out=Path('/tmp/gensticker-editor-live-verification');out.mkdir(exist_ok=True)
identifier='editor_check_'+uuid.uuid4().hex;token=secrets.token_urlsafe(32)
db=account.connection()
with db:
 db.execute('INSERT INTO users(id,openid,name) VALUES(?,?,?)',(identifier,identifier,'独立功能验收账号'))
 db.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),identifier,int(time.time())+1800))
db.close()
report={'checks':[],'identity':'isolated synthetic identity; no WeChat login or public publication'}
created_live=[]
def check(name,**detail):report['checks'].append({'name':name,**detail});print(json.dumps(report['checks'][-1],ensure_ascii=False),flush=True)
def wait(client,path):
 end=time.time()+180
 while time.time()<end:
  response=client.get(path);response.raise_for_status();job=response.json()
  if job['status'] not in ('queued','running'):return job
  time.sleep(1)
 raise TimeoutError('worker timeout')
def request(client,method,path,**kwargs):
 response=client.request(method,path,**kwargs);response.raise_for_status();return response
try:
 with httpx.Client(base_url='http://127.0.0.1:3000/gensticker/api',headers={'Authorization':'Bearer '+token},timeout=70) as client:
  config=request(client,'GET','/account/config').json();assert config['features']['livegif'] and config['features']['template_editor'];check('Nginx and new feature flags')
  guide=request(client,'GET','/images/templates/always/guide').json();overlay=request(client,'GET',guide['overlay_url']);(out/'builtin-overlay.png').write_bytes(overlay.content);check('built-in differential template guide',windows=len(guide['windows']),generic=guide['generic'])
  image=Image.new('RGBA',(256,320));draw=ImageDraw.Draw(image);draw.ellipse((35,10,215,295),fill='#e5ab57');draw.ellipse((80,100,92,120),fill='#243e40');draw.ellipse((160,100,172,120),fill='#243e40')
  buf=BytesIO();image.save(buf,'PNG');raw=buf.getvalue();encoded=base64.b64encode(raw).decode()
  foreground=request(client,'POST','/images/subject',json={'image':encoded,'delivery':'url'}).json();result=request(client,'GET',foreground['image_url']);(out/'cutout.png').write_bytes(result.content)
  assert httpx.get('http://127.0.0.1:3001'+foreground['image_url']).status_code==404;check('temporary foreground URL download and ownership',bytes=len(result.content))
  opaque=Image.new('RGB',image.size,'white');opaque.paste(image,mask=image.getchannel('A'));buf=BytesIO();opaque.save(buf,'PNG')
  segmented=request(client,'POST','/images/subject',json={'image':base64.b64encode(buf.getvalue()).decode(),'delivery':'url'}).json();result=request(client,'GET',segmented['image_url']);alpha=Image.open(BytesIO(result.content)).getchannel('A');assert alpha.getextrema()[0]<255;(out/'segmentation.png').write_bytes(result.content);check('actual segmentation model on opaque test picture',alpha_min=alpha.getextrema()[0])
  spec={'width':512,'height':512,'layers':[{'type':'subject','box':[96,40,240,320]},{'type':'text','box':[12,400,488,90],'slot':0,'font_size':32,'value':'hello'}],'defaults':['hello']}
  template=request(client,'POST','/studio/templates',json={'name':'私有验收模板','spec':spec}).json()
  guide=request(client,'GET','/images/templates/'+template['id']+'/guide').json();assert guide['windows'][0]['box']==[96,40,240,320];check('exact private-template replacement window')
  job=request(client,'POST','/studio/jobs',json={'template_key':template['id'],'images':[encoded],'texts':['editor result'],'idempotency_key':uuid.uuid4().hex}).json()
  result=wait(client,'/studio/jobs/'+job['id']);assert result['status']=='completed',result
  assert request(client,'GET','/studio/unread').json()['count']==1
  image=request(client,'GET',result['result_url']);(out/'manual.png').write_bytes(image.content)
  assert request(client,'GET','/studio/unread').json()['count']==1
  request(client,'POST','/studio/jobs/'+job['id']+'/view');assert request(client,'GET','/studio/unread').json()['count']==0
  redo=request(client,'POST','/studio/jobs/'+job['id']+'/regenerate',json={'idempotency_key':uuid.uuid4().hex}).json();assert wait(client,'/studio/jobs/'+redo['id'])['status']=='completed';check('real manual worker, download remains unread, view clears count, replay generates')
  frames=[]
  for offset in range(16):
   frame=Image.new('RGB',(180,120),'#476e5b');ImageDraw.Draw(frame).ellipse((offset*7,24,offset*7+40,86),fill='#ffd17e');frames.append(frame)
  buf=BytesIO();frames[0].save(buf,'GIF',save_all=True,append_images=frames[1:],duration=100,loop=0)
  asset=request(client,'POST','/studio/live/assets',files={'file':('motion.gif',buf.getvalue(),'image/gif')}).json();created_live.append(asset['asset_id'])
  payload={'asset_id':asset['asset_id'],'idempotency_key':uuid.uuid4().hex,'start':.1,'duration':1,'rotation':90,'flip':True,'crop':[0,0,.5,1],'text':'Live GIF'}
  job=request(client,'POST','/studio/live/jobs',json=payload).json();assert request(client,'POST','/studio/live/jobs',json=payload).json()['id']==job['id']
  result=wait(client,'/studio/jobs/'+job['id']);assert result['status']=='completed',result
  gif=request(client,'GET',result['result_url']);(out/'live.gif').write_bytes(gif.content)
  with Image.open(BytesIO(gif.content)) as decoded:
   assert decoded.n_frames>=2;check('actual GIF worker with crop, rotation, mirror, caption and idempotency',frames=decoded.n_frames,size=list(decoded.size),bytes=len(gif.content));decoded.convert('RGB').save(out/'live-first-frame.jpg')
  buf=BytesIO();Image.new('RGB',(40,40),'red').save(buf,'JPEG');bad=client.post('/studio/live/assets',files={'file':('photo.jpg',buf.getvalue(),'image/jpeg')});assert bad.status_code==422 and '存储为视频' in bad.json()['detail'];check('static-only Live input gets an actionable error')
  report['status']='passed'
except Exception as error:
 report['status']='failed';report['error']=str(error);raise
finally:
 # Delete only this fixture account. Keep unrelated user state intact.
 db=studio.init()
 jobs=[dict(r) for r in db.execute('SELECT * FROM studio_jobs WHERE user_id=?',(identifier,))]
 if not any(j['status'] in ('queued','running') for j in jobs):
  with db:
   db.execute('DELETE FROM studio_views WHERE user_id=?',(identifier,));db.execute('DELETE FROM studio_jobs WHERE user_id=?',(identifier,));db.execute('DELETE FROM studio_templates WHERE user_id=?',(identifier,));db.execute('DELETE FROM studio_ai_daily WHERE user_id=?',(identifier,))
  for job in jobs:
   (studio.root()/'studio_results'/job['id']).unlink(missing_ok=True);(studio.root()/'studio_replays'/(job['id']+'.json')).unlink(missing_ok=True)
  for asset in created_live:
   for suffix in ('.media','.jpg','.json'):(livegif.directory()/(asset+suffix)).unlink(missing_ok=True)
  accounts=account.connection()
  with accounts:
   accounts.execute('DELETE FROM sessions WHERE user_id=?',(identifier,));accounts.execute('DELETE FROM users WHERE id=?',(identifier,))
  accounts.close();report['fixture_cleaned']=True
 else:report['fixture_cleaned']=False
 db.close();(out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
