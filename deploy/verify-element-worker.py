"""Real recommendation API/worker acceptance with an isolated synthetic account."""
import hashlib,json,secrets,time,uuid,shutil
from io import BytesIO
from pathlib import Path
import httpx
from PIL import Image,ImageDraw
from meme_generator import account
from meme_generator.features.store import connect,root

user='elements_check_'+uuid.uuid4().hex;token=secrets.token_urlsafe(32)
db=account.connection()
with db:
    db.execute('INSERT INTO users(id,openid,name) VALUES(?,?,?)',(user,user,'Template fixture'))
    db.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),user,int(time.time())+600))
db.close();report={'identity':'isolated synthetic account','status':'failed'}
try:
    with httpx.Client(base_url='http://127.0.0.1:3001',headers={'Authorization':'Bearer '+token},timeout=75) as client:
        image=Image.new('RGB',(240,280),'#fff5df');draw=ImageDraw.Draw(image)
        draw.ellipse((30,20,210,260),fill='#dd9867');draw.ellipse((65,95,83,115),fill='black');draw.ellipse((155,95,173,115),fill='black');draw.arc((70,125,170,210),0,180,fill='black',width=5)
        raw=BytesIO();image.save(raw,'PNG')
        response=client.post('/recommend/assets',files={'file':('fixture.png',raw.getvalue(),'image/png')});response.raise_for_status();asset=response.json()['asset_id']
        response=client.post('/recommend/jobs',json={'asset_id':asset,'idempotency_key':uuid.uuid4().hex});response.raise_for_status();job_id=response.json()['job_id']
        deadline=time.time()+180
        while time.time()<deadline:
            response=client.get('/recommend/jobs/'+job_id);response.raise_for_status();job=response.json()
            if job['status'] not in ('queued','running'):break
            time.sleep(1)
        assert job['status']=='completed' and len(job['results'])==9,job
        cases=[];db=connect()
        for result in job['results']:
            metadata=json.loads(db.execute('SELECT metadata FROM templates WHERE key=?',(result['key'],)).fetchone()[0])
            assert metadata.get('conversion')!='reaction-story-v1'
            response=client.get(result['preview_url'].split('?')[0]);response.raise_for_status()
            with Image.open(BytesIO(response.content)) as im:im.verify()
            cases.append({'key':result['key'],'conversion':metadata.get('conversion','bundled'),'version':result.get('version'),'preview_mime':response.headers['content-type']})
        db.close()
        assert any(r['conversion']=='element-replacement-v1' for r in cases)
        report.update(status='passed',count=9,cases=cases)
finally:
    db=connect();assets=[dict(r) for r in db.execute('SELECT * FROM assets WHERE user_id=?',(user,))]
    busy=db.execute("SELECT count(*) FROM jobs WHERE user_id=? AND status IN ('queued','running')",(user,)).fetchone()[0]
    if not busy:
        with db:
            for name in ['results','job_variations','quotas','cost_ledger']:
                db.execute(f'DELETE FROM {name} WHERE job_id IN (SELECT id FROM jobs WHERE user_id=?)',(user,))
            for name in ['jobs','assets','events','preferences','feedback_history','generation_admissions']:
                db.execute(f'DELETE FROM {name} WHERE user_id=?',(user,))
        shutil.rmtree(root()/'private'/user,ignore_errors=True)
        for asset in assets:(root()/'history_thumbs'/(asset['id']+'.jpg')).unlink(missing_ok=True)
        accounts=account.connection()
        with accounts:
            for name in ['sessions','favorites','history']:accounts.execute(f'DELETE FROM {name} WHERE user_id=?',(user,))
            accounts.execute('DELETE FROM users WHERE id=?',(user,))
        accounts.close();report['fixture_cleanup']='completed'
    else:report['fixture_cleanup']='in-flight work retained for TTL cleanup'
    db.close()
    Path('/tmp/gensticker-elements-worker-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False),flush=True)
