#!/usr/bin/env python3
"""Apply only the requested A/B delta. Keep exact row/file backups for rollback."""
import hashlib,json,os,shutil,sqlite3,subprocess,time,urllib.request,sys
from pathlib import Path

PACKAGE=Path(__file__).resolve().parent
DB=Path('/var/lib/gensticker/features/features.sqlite3')


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None

def command(*args,**kwargs):
    try:return subprocess.run(args,check=True,capture_output=True,text=True,**kwargs).stdout.strip()
    except subprocess.CalledProcessError as exc:
        print((exc.stderr or '')[-6000:],file=sys.stderr)
        raise

def jobs():
    db=sqlite3.connect('file:'+str(DB)+'?mode=ro',uri=True)
    try:
        count=db.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0]
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='studio_jobs'").fetchone():count+=db.execute("SELECT count(*) FROM studio_jobs WHERE status IN ('queued','running')").fetchone()[0]
        return count
    finally:db.close()


def main():
    manifest=json.loads((PACKAGE/'manifest.json').read_text());release=Path('/opt/gensticker-current').resolve();runtime=release/'meme-generator'
    if manifest['format']!='gensticker-expression-deploy-v1' or str(release)!=manifest['release']:raise ValueError('release changed')
    for name,info in manifest['files'].items():
        if Path(name).is_absolute() or '..' in Path(name).parts:raise ValueError('invalid runtime path')
        if sha(runtime/name)!=info['old_sha256'] or sha(PACKAGE/'runtime'/name)!=info['sha256']:raise ValueError('runtime changed: '+name)
    if sha(PACKAGE/'selfie_multiclass_256x256.tflite')!=manifest['model_sha256']:raise ValueError('model checksum mismatch')
    driver=manifest.get('driver_model')
    if driver:
        if (driver['name']!='ganimation-emotionnet-v1.onnx'
                or driver['sha256']!='e4ceefd1c354a1e13a1d46e322108aeb5024d846ee7536468d19aca3f51b6f46'
                or (PACKAGE/driver['name']).stat().st_size>36_000_000
                or sha(PACKAGE/driver['name'])!=driver['sha256']):raise ValueError('unreviewed expression model')
        existing=DB.parent/'models'/driver['name']
        if existing.exists() and sha(existing)!=driver['sha256']:raise ValueError('existing expression model differs')
        for name in ['api-venv','worker-venv']:
            command(str(release/name/'bin/python'),'-c','import onnxruntime;print(onnxruntime.__version__)')
    live=sqlite3.connect('file:'+str(DB)+'?mode=ro',uri=True);live.row_factory=sqlite3.Row
    try:
        untouched={row['key']:dict(row) for row in live.execute('SELECT key,version,fingerprint,metadata,spec,status FROM templates') if row['key'] not in manifest['updates']}
        for key,expected in manifest['updates'].items():
            row=live.execute('SELECT * FROM templates WHERE key=?',(key,)).fetchone()
            if not row or row['status']!='published' or row['version']!=expected['base_version'] or row['fingerprint']!=expected['base_fingerprint']:raise ValueError('template changed: '+key)
    finally:live.close()
    # A local authoring cache is not proof that a dependency exists on this host.
    artwork=DB.parent/'template_assets'
    for path in (PACKAGE/'runtime/meme_generator/features/expression_batches').glob('*.json'):
        batch=json.loads(path.read_text())
        for item in batch['templates']:
            spec=item['spec'] or {};refs=set()
            for frame in [spec]+spec.get('frames',[]):
                refs.update(frame[k] for k in ['asset','reference_asset','animation_asset'] if frame.get(k))
                for layer in frame.get('layers',[]):
                    if layer.get('type')=='asset':refs.add(layer['value'])
                    refs.update(layer[k] for k in ['mask_asset','original_asset'] if layer.get(k))
                    if recipe:=layer.get('expression'):
                        refs.update(recipe[k] for k in ['reference_asset','base_asset','mask_asset'])
                        refs.update(c['mask_asset'] for c in (recipe.get('controls') or {}).get('components',[]))
            if recipe:=item['metadata'].get('expression_policy',{}).get('recipe'):
                refs.update(recipe[k] for k in ['reference_asset','base_asset','mask_asset'])
                refs.update(c['mask_asset'] for c in (recipe.get('controls') or {}).get('components',[]))
            for digest in refs:
                if digest not in batch['assets'] and not any((artwork/(digest+suffix)).is_file() for suffix in ['.png','.gif']):
                    raise ValueError('missing artwork before deployment: '+item['key']+' / '+digest)
    if jobs():raise RuntimeError('defer: active user jobs')
    backup=Path('/var/backups')/('gensticker-expression-ab-'+str(int(time.time())));backup.mkdir(mode=0o700)
    live=sqlite3.connect(DB);saved=sqlite3.connect(backup/'features.sqlite3')
    try:live.backup(saved)
    finally:saved.close();live.close()
    for name in manifest['files']:
        path=runtime/name
        if path.exists():
            old=backup/'runtime'/name;old.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,old)
    model=DB.parent/'models/selfie_multiclass_256x256.tflite';model.parent.mkdir(exist_ok=True)
    if model.exists() and sha(model)!=manifest['model_sha256']:raise ValueError('existing segmentation model differs')
    stopped=False;changed=[]
    try:
        command('systemctl','stop','gensticker');stopped=True
        for _ in range(30):
            if not jobs():break
            time.sleep(1)
        else:raise RuntimeError('worker still owns a user job')
        command('systemctl','stop','gensticker-worker')
        for name in manifest['files']:
            target=runtime/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(PACKAGE/'runtime'/name,target);target.chmod(0o644);changed.append(name)
        if not model.exists():
            temporary=model.with_suffix('.tmp');shutil.copy2(PACKAGE/'selfie_multiclass_256x256.tflite',temporary);temporary.chmod(0o644);temporary.replace(model)
        if driver and not (DB.parent/'models'/driver['name']).exists():
            target=DB.parent/'models'/driver['name'];temporary=target.with_suffix('.tmp')
            shutil.copy2(PACKAGE/driver['name'],temporary);temporary.chmod(0o644);temporary.replace(target)
        environment={**os.environ,'GENSTICKER_STATE_DIR':'/var/lib/gensticker','PYTHONPATH':str(runtime),'GENSTICKER_BOOTSTRAP_SEEDS':'0'}
        count=command(str(release/'api-venv/bin/python'),'-c','from meme_generator.features.expression_library import restore;print("UPDATED",restore())',env=environment,cwd=runtime,timeout=120)
        # Validate as the real service user before opening requests again.
        verify = '''from pathlib import Path
from meme_generator.features.store import connect,root
from meme_generator.features.storage import asset_refs
c=connect();count=0
for row in c.execute("SELECT spec,metadata FROM templates WHERE status='published'"):
 for digest in asset_refs(row['spec'])|asset_refs(row['metadata']):
  path=next((root()/'template_assets'/(digest+suffix) for suffix in ['.png','.gif'] if (root()/'template_assets'/(digest+suffix)).is_file()))
  with path.open('rb') as f:f.read(8)
  count+=1
for filename in ['face_landmarker-v1.task','selfie_multiclass_256x256.tflite']:
 with (root()/'models'/filename).open('rb') as f:f.read(8)
print('READABLE',count)
'''
        command('runuser','-u','gensticker','--',str(release/'api-venv/bin/python'),'-c',verify,env=environment,cwd=runtime,timeout=60)
        if driver:
            for name in ['api-venv','worker-venv']:
                command('runuser','-u','gensticker','--',str(release/name/'bin/python'),'-c',
                        'from meme_generator.features.expression_driver import warmup;assert warmup();print("CPU_DRIVER_READY")',
                        env=environment,cwd=runtime,timeout=45)
        command('systemctl','start','gensticker-worker');command('systemctl','start','gensticker')
        for attempt in range(60):
            try:
                with urllib.request.urlopen('http://127.0.0.1:3001/healthz',timeout=2) as response:health=json.load(response)
                if health['status']=='ok' and health['templates']>=958:break
            except Exception:time.sleep(1)
        else:raise RuntimeError('health check failed')
        live=sqlite3.connect(DB);live.row_factory=sqlite3.Row
        try:
            counts={'A':0,'B':0}
            for key,expected in manifest['updates'].items():
                row=live.execute('SELECT * FROM templates WHERE key=?',(key,)).fetchone();policy=json.loads(row['metadata']).get('expression_policy',{})
                if row['version']!=expected['version'] or policy.get('mode')!=expected['mode']:raise RuntimeError('updated policy/version mismatch: '+key)
                if expected.get('driver') and (policy.get('driver')!=expected['driver'] or policy.get('visual_status')!=expected['visual_status']):raise RuntimeError('reviewed driver mismatch: '+key)
                counts[policy['mode']]+=1
            for key,expected in untouched.items():
                actual=live.execute('SELECT key,version,fingerprint,metadata,spec,status FROM templates WHERE key=?',(key,)).fetchone()
                if not actual or dict(actual)!=expected:raise RuntimeError('unrelated template changed: '+key)
        finally:live.close()
        result={'status':'passed','backup':str(backup),'templates':health['templates'],'updated':len(manifest['updates']),'modes':counts,'untouched_templates_verified':len(untouched),'services':{name:command('systemctl','is-active',name) for name in ['gensticker','gensticker-worker']},'restore':count.splitlines()[-1]}
        (PACKAGE/'deployment-result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
    except Exception:
        if stopped:command('systemctl','stop','gensticker')
        command('systemctl','stop','gensticker-worker')
        for name in changed:
            path=runtime/name;old=backup/'runtime'/name
            if old.exists():shutil.copy2(old,path)
            else:path.unlink(missing_ok=True)
        saved=sqlite3.connect(backup/'features.sqlite3');saved.row_factory=sqlite3.Row;live=sqlite3.connect(DB);live.row_factory=sqlite3.Row
        try:
            with live:
                for key,expected in manifest['updates'].items():
                    current=live.execute('SELECT * FROM templates WHERE key=?',(key,)).fetchone();old=saved.execute('SELECT * FROM templates WHERE key=?',(key,)).fetchone()
                    if current and old and current['version']==expected['version'] and json.loads(current['metadata']).get('expression_policy',{}).get('method')=='cpu-expression-ab-v1':
                        fields=['version','fingerprint','metadata','spec','status']
                        live.execute('UPDATE templates SET '+','.join(n+'=?' for n in fields)+' WHERE key=?',[old[n] for n in fields]+[key])
                        live.execute('DELETE FROM template_versions WHERE template_id=? AND version=? AND fingerprint=?',(current['id'],current['version'],current['fingerprint']))
        finally:saved.close();live.close()
        if stopped:command('systemctl','start','gensticker-worker');command('systemctl','start','gensticker')
        raise

if __name__=='__main__':main()
