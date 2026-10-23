"""Six-hour, resumable bounded authoring jobs. Below-minimum runs are attention,
not fake success; an 8000-template catalog is never exceeded by retrying a run.
"""
from contextlib import contextmanager
from datetime import datetime,timezone,timedelta
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import time
import uuid
from PIL import Image
from .store import connect,root
from .storage import exclusive,state_usage,limit
from .minimax_authoring import MiniMax,ModelUnavailable,author,normalize
from .public_sources import discover,fetch_candidate,SourceUnavailable


@contextmanager
def staging(directory):
    old=os.environ.get('GENSTICKER_STATE_DIR')
    os.environ['GENSTICKER_STATE_DIR']=str(directory)
    try:yield
    finally:
        if old is None:os.environ.pop('GENSTICKER_STATE_DIR',None)
        else:os.environ['GENSTICKER_STATE_DIR']=old


@contextmanager
def public_write_guard(incoming,files=0):
    with exclusive():
        total,count=state_usage()
        if total+incoming>limit('STATE_MAX_BYTES',12*1024**3) or count+files>limit('STATE_MAX_FILES',100000):raise ValueError('public_storage_budget_reached')
        if shutil.disk_usage(root()).free-incoming<limit('MIN_FREE_BYTES',10*1024**3):raise ValueError('public_storage_low_disk')
        db=connect()
        try:
            if db.execute("SELECT count(*) FROM templates WHERE status='published'").fetchone()[0]>=min(8000,limit('PUBLIC_TEMPLATE_LIMIT',8000)):raise ValueError('public_template_limit_reached')
        finally:db.close()
        # Stage products, download cache and final materialized assets share this limit.
        yield


def publish_product(product,batch_id):
    from .catalog import publish
    from .element_templates import validate_elements
    validate_elements(product['spec'],product['metadata'])
    if product['metadata'].get('max_images',0) and product['metadata'].get('quality',{}).get('local_geometry',{}).get('verified') is not True:raise ValueError('independently measured source face geometry required for automatic publication')
    verification=product['metadata'].get('quality',{}).get('cross_visual_review',{})
    reviews=verification.get('reviews',[])
    if verification.get('analyzed_frames')!=len(product['spec'].get('frames',[])) or len(reviews)!=verification.get('analyzed_frames') or not reviews or not all(all(review.get(field) is True for field in ['passed','old_face_fully_removed','caption_complete','props_preserved']) for review in reviews):raise ValueError('independent full-frame VLM review required before publication')
    assets=product['assets'];directory=root()/'template_assets'
    required={digest:data for digest,data in assets.items() if not (directory/(digest+('.gif' if data.startswith(b'GIF') else '.png'))).exists()}
    with public_write_guard(sum(map(len,required.values()))+256*1024,len(required)+1):
        db=connect()
        try:
            if db.execute('SELECT 1 FROM templates WHERE key=?',(product['key'],)).fetchone():raise ValueError('source_already_in_catalog')
            candidate=product['metadata'].get('perceptual_hash')
            for old in db.execute("SELECT metadata FROM templates"):
                previous=json.loads(old[0]).get('perceptual_hash')
                if candidate and previous and (int(candidate,16)^int(previous,16)).bit_count()<=4:raise ValueError('near_duplicate_source_visual')
        finally:db.close()
        directory.mkdir(exist_ok=True)
        for digest,data in required.items():
            if hashlib.sha256(data).hexdigest()!=digest:raise ValueError('asset content hash mismatch')
            path=directory/(digest+('.gif' if data.startswith(b'GIF') else '.png'))
            temporary=path.with_suffix(path.suffix+'.partial');temporary.write_bytes(data);os.replace(temporary,path)
        row=publish(product['key'],product['metadata'],product['spec'],publication={'batch_id':batch_id,'score':product['metadata']['quality']['score']})
        return row


def save_report(identifier,started,report,status):
    db=connect()
    try:
        with db:db.execute('INSERT INTO ingestion_runs VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET finished=excluded.finished,status=excluded.status,report=excluded.report',(identifier,started,time.time(),status,json.dumps(report,ensure_ascii=False)))
    finally:db.close()


def save_candidate(identifier,item,entry):
    db=connect()
    try:
        with db:db.execute('INSERT INTO candidates VALUES(?,?,?,?,?) ON CONFLICT(hash) DO UPDATE SET status=excluded.status,reason=excluded.reason,created=excluded.created',(identifier,item['source_url'],entry['status'],json.dumps(entry,ensure_ascii=False),time.time()))
    finally:db.close()


def trim_working_files():
    stamp=time.time()
    for abandoned in root().glob('authoring-stage-*'):
        if abandoned.is_dir() and not abandoned.is_symlink() and abandoned.stat().st_mtime<stamp-4*3600:shutil.rmtree(abandoned)
    for folder,max_age,max_bytes in [('authoring_sources',7*86400,128*1024**2),('authoring_evidence',14*86400,128*1024**2)]:
        directory=root()/folder
        if not directory.exists():continue
        files=sorted((p for p in directory.rglob('*') if p.is_file() and not p.is_symlink()),key=lambda p:p.stat().st_mtime)
        total=sum(p.stat().st_size for p in files)
        for path in files:
            size=path.stat().st_size
            if path.stat().st_mtime<stamp-max_age or total>max_bytes:path.unlink();total-=size
    db=connect()
    try:
        with db:
            db.execute("DELETE FROM ingestion_runs WHERE started<?",(stamp-90*86400,))
            db.execute('DELETE FROM template_trial_uses WHERE used<?',(stamp-90*86400,))
            db.execute("DELETE FROM candidates WHERE status NOT IN ('published','license-pending') AND created<?",(stamp-90*86400,))
    finally:db.close()


def run(*,client=None,candidates=None,force=False,target=None,max_attempts=None):
    if client is None and os.getenv('GENSTICKER_MINIMAX_ENABLED','0')!='1':
        # Preserve six-hour collection while the observed model quality is
        # awaiting independent acceptance. This mode never runs a model or
        # publishes anything, and reports the hold explicitly.
        started=time.time();identifier='discovery-'+str(int((started+8*3600)//21600));trim_working_files()
        with public_write_guard(1024**2,1):pass
        items,errors=discover(None)
        with public_write_guard(1024**2,1):
            db=connect();collected=0
            try:
                with db:
                    for item in items:
                        key=hashlib.sha256(item['image_url'].encode()).hexdigest()
                        collected+=db.execute('INSERT OR IGNORE INTO candidates VALUES(?,?,?,?,?)',(key,item['source_url'],'authoring-pending',json.dumps(item,ensure_ascii=False),time.time())).rowcount
            finally:db.close()
        report={'id':identifier,'status':'held-for-quality','published':0,'discovered':len(items),'new_candidate_metadata':collected,'source_errors':errors,'attention':'independent-quality-acceptance-required; collection-only, no automatic publication'}
        save_report(identifier,started,report,report['status']);return report
    started=time.time();identifier='sixhour-'+str(int((started+8*3600)//21600))
    if force:identifier+='-'+uuid.uuid4().hex[:8]
    base=root();lock=(base/'ingestion.lock').open('a')
    try:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return {'status':'already-running','published':0}
        db=connect()
        try:
            previous=db.execute('SELECT status,report FROM ingestion_runs WHERE id=?',(identifier,)).fetchone()
            if previous and previous['status']=='completed':return json.loads(previous['report'])
        finally:db.close()
        report={'id':identifier,'status':'running','target':min(10,max(3,target or int(os.getenv('GENSTICKER_INGEST_TARGET','5')))),'published':0,'discovered':0,'attempted':0,'scanned':0,'results':[],'source_errors':[]}
        if previous:
            report=json.loads(previous['report']);report['status']='running'
        db=connect()
        try:published_now=list(db.execute('SELECT p.key,p.score,t.metadata FROM template_publications p JOIN templates t ON t.key=p.key WHERE p.batch_id=?',(identifier,)))
        finally:db.close()
        report['published']=len(published_now)
        known={r.get('key') for r in report['results']}
        for value in published_now:
            if value['key'] not in known:report['results'].append({'key':value['key'],'name':json.loads(value['metadata'])['name'],'score':value['score'],'status':'published','recovered_after_interruption':True})
        save_report(identifier,started,report,'running');trim_working_files()
        owned=client is None
        try:
            client=client or MiniMax(limit=60)
            if candidates is None:candidates,report['source_errors']=discover(client)
            report['discovered']=len(candidates)
            cache=base/'authoring_sources';cache.mkdir(exist_ok=True)
            photo_path=Path(__file__).with_name('authoring')/'validation-cat.jpg'
            with Image.open(photo_path) as image:photo=image.convert('RGBA')
            budget=max_attempts or min(30,max(3,int(os.getenv('GENSTICKER_INGEST_ATTEMPTS','18'))))
            db=connect()
            try:known_visuals=[int(m['perceptual_hash'],16) for r in db.execute('SELECT metadata FROM templates') if (m:=json.loads(r[0])).get('perceptual_hash')]
            finally:db.close()
            for item in candidates:
                if report['published']>=report['target'] or report['attempted']>=budget or time.time()-started>2100:break
                candidate_id=hashlib.sha256(item['image_url'].encode()).hexdigest()
                db=connect()
                try:
                    prior=db.execute('SELECT status,created FROM candidates WHERE hash=?',(candidate_id,)).fetchone()
                    if prior and ((prior['status']=='published' and prior['created']>started-86400) or (prior['status'] in {'quality-pending','duplicate'} and prior['created']>started-7*86400) or (prior['status']=='source-unavailable' and prior['created']>started-1800)):continue
                finally:db.close()
                report['scanned']=report.get('scanned',0)+1;digest=candidate_id;entry={'source_url':item['source_url'],'image_url':item['image_url'],'status':'pending'}
                try:
                    with public_write_guard(64*1024**2,200):pass
                    source=cache/(digest+'.image')
                    raw=source.read_bytes() if source.exists() else fetch_candidate(item)
                    original=hashlib.sha256(raw).hexdigest()
                    db=connect()
                    try:exists=db.execute('SELECT 1 FROM templates WHERE key=? OR json_extract(metadata,\'$.original_hash\')=?',('auto_'+original[:24],original)).fetchone()
                    finally:db.close()
                    duplicate=bool(exists)
                    if not duplicate:
                        from .quality import perceptual_hash
                        _,normalized_frames,_=normalize(raw);visual=int(perceptual_hash(normalized_frames[0]),16)
                        duplicate=any((visual^old).bit_count()<=4 for old in known_visuals)
                    if duplicate:
                        entry['status']='duplicate';save_candidate(digest,item,entry);report['results'].append(entry);save_report(identifier,started,report,'running');continue
                    if not source.exists():
                        with public_write_guard(len(raw),1):source.write_bytes(raw)
                    with tempfile.TemporaryDirectory(prefix='authoring-stage-',dir=base) as temp:
                        report['attempted']+=1
                        with staging(temp):product=author(client,raw,item,photo)
                        publish_product(product,identifier)
                        evidence=base/'authoring_evidence'/product['key'];evidence.mkdir(parents=True,exist_ok=True)
                        for index,(label,board) in enumerate(product['boards']):board.save(evidence/(str(index)+'.jpg'),quality=85)
                        (evidence/'review.json').write_text(json.dumps({'key':product['key'],'quality':product['metadata']['quality'],'review':product['review'],'source_url':item['source_url']},ensure_ascii=False,indent=2))
                    report['published']+=1;entry.update(status='published',key=product['key'],name=product['metadata']['name'],score=product['metadata']['quality']['score'])
                    known_visuals.append(int(product['metadata']['perceptual_hash'],16))
                except ModelUnavailable as error:
                    report['model_error']=str(error);entry.update(status='model-unavailable',reason=str(error));report['results'].append(entry);break
                except SourceUnavailable as error:entry.update(status='source-unavailable',reason=str(error)[:200])
                except (ValueError,OSError,KeyError,TypeError) as error:
                    # Error messages never contain model HTTP headers/bodies or credentials.
                    reason=str(error)[:300] if isinstance(error,ValueError) else type(error).__name__
                    entry.update(status='quality-pending',reason=reason)
                save_candidate(digest,item,entry)
                report['results'].append(entry);save_report(identifier,started,report,'running')
            report.update(status='completed' if report['published']>=3 else 'attention',model_calls=client.calls,model_tokens=client.tokens,elapsed_seconds=round(time.time()-started,1))
            if report['published']<3:report['attention']='fewer-than-three-validated-new-templates'
        except (ValueError,OSError) as error:report.update(status='attention',reason=str(error)[:200])
        finally:
            if owned and client:client.close()
        save_report(identifier,started,report,report['status']);trim_working_files()
        return report
    finally:lock.close()


if __name__=='__main__':
    import argparse,signal
    def interrupted(signum,frame):raise InterruptedError('authoring_interrupted')
    signal.signal(signal.SIGTERM,interrupted)
    parser=argparse.ArgumentParser();parser.add_argument('--force',action='store_true');args=parser.parse_args()
    result=run(force=args.force);print(json.dumps(result,ensure_ascii=False),flush=True)
    raise SystemExit(0 if result['status'] in {'completed','already-running','held-for-quality'} else 1)
