"""Apply a checksum-guarded reviewed-template release on the existing host.

The release directory contains release.json and the changed backend files.
Only the named application services are stopped. Rollback withdraws only keys
introduced by this release; it never restores an old database over user data.
"""
import argparse,hashlib,json,os,grp,sqlite3,subprocess,tempfile,time,urllib.request
from pathlib import Path


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--release',required=True);parser.add_argument('--runtime',required=True);parser.add_argument('--state',required=True);args=parser.parse_args()
    release=Path(args.release).resolve();runtime=Path(args.runtime).resolve();state=Path(args.state).resolve();manifest=json.loads((release/'release.json').read_text());old={};new={};keys={}
    assert len(manifest)<=100
    for name,checksums in manifest.items():
        relative=Path(name);assert not relative.is_absolute() and '..' not in relative.parts and relative.parts[0]=='meme_generator'
        target=runtime/relative;source=release/relative;assert not target.is_symlink() and target.resolve().is_relative_to(runtime) and not source.is_symlink() and source.resolve().is_relative_to(release)
        before=target.read_bytes() if target.is_file() else None
        assert (hashlib.sha256(before).hexdigest() if before is not None else None)==checksums['before'],'runtime changed: '+name
        data=source.read_bytes();assert hashlib.sha256(data).hexdigest()==checksums['after'],'release changed: '+name
        if relative.suffix=='.py':compile(data,name,'exec')
        else:
            assert relative.parent.as_posix()=='meme_generator/features/template_batches' and relative.name.startswith('20261021-reactions-')
            batch=json.loads(data)
            for item in batch['templates']:
                assert item['key'].startswith('auto_story_') and item['metadata']['conversion']=='reaction-story-v1'
                keys[item['key']]=item['metadata']['original_hash']
        old[name]=before;new[name]=data
    assert len(keys)==649
    database=state/'features/features.sqlite3'
    def active():
        with sqlite3.connect('file:'+str(database)+'?mode=ro',uri=True) as db:
            return db.execute("SELECT (SELECT count(*) FROM jobs WHERE status IN ('queued','running'))+(SELECT count(*) FROM studio_jobs WHERE status IN ('queued','running'))").fetchone()[0]
    assert active()==0,'active user work; defer deployment'
    with sqlite3.connect('file:'+str(database)+'?mode=ro',uri=True) as db:
        for key in keys:assert not db.execute('SELECT 1 FROM templates WHERE key=?',(key,)).fetchone(),'key already exists: '+key
    backup=Path('/var/backups')/('gensticker-reactions-'+str(int(time.time())));backup.mkdir(mode=0o700)
    for name,data in old.items():
        if data is None:continue
        p=backup/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data);p.chmod(0o600)
    (backup/'release.json').write_text(json.dumps(manifest,indent=2));(backup/'introduced-keys.json').write_text(json.dumps(keys))
    gid=grp.getgrnam('gensticker').gr_gid
    def write(name,data):
        p=runtime/name
        if data is None:
            p.unlink(missing_ok=True);return
        with tempfile.NamedTemporaryFile(dir=p.parent,prefix='.reviewed-release-',delete=False) as file:
            file.write(data);os.fchown(file.fileno(),0,gid);os.fchmod(file.fileno(),0o644);temporary=file.name
        os.replace(temporary,p)
    def api_health():
        for _ in range(90):
            try:
                with urllib.request.urlopen('http://127.0.0.1:3001/healthz',timeout=2) as response:
                    if response.status==200:return
            except Exception:pass
            time.sleep(1)
        raise RuntimeError('API health timeout')
    subprocess.run(['systemctl','stop','gensticker','gensticker-worker'],check=True)
    try:
        assert active()==0,'new work arrived before stop; deployment deferred'
        with sqlite3.connect(database) as db,sqlite3.connect(backup/'features.sqlite3') as snapshot:db.backup(snapshot)
        (backup/'features.sqlite3').chmod(0o600)
        for name,data in new.items():write(name,data)
        subprocess.run(['systemctl','start','gensticker'],check=True);api_health()
        subprocess.run(['systemctl','start','gensticker-worker'],check=True)
        with urllib.request.urlopen('http://127.0.0.1:3001/memes/categories',timeout=20) as response:catalog=json.load(response)
        assert len(catalog['all'])==1000,'catalog total differs'
        assert sum(card.get('animated',False) for card in catalog['cards'])==437,'motion count differs'
        for service in ['gensticker','gensticker-worker']:subprocess.run(['systemctl','is-active','--quiet',service],check=True)
        for url in ['http://127.0.0.1:3003/','http://127.0.0.1:18789/healthz']:
            with urllib.request.urlopen(url,timeout=5) as response:assert response.status==200
        print(json.dumps({'status':'passed','backup':str(backup),'introduced':len(keys),'total':len(catalog['all']),'animated':sum(c.get('animated',False) for c in catalog['cards']),'categories':{k:len(catalog[k]) for k in ['image_only','mixed','text_only']},'other_services_healthy':True,'checksums':{n:v['after'] for n,v in manifest.items()}}),flush=True)
    except BaseException:
        subprocess.run(['systemctl','stop','gensticker','gensticker-worker'],check=False)
        with sqlite3.connect(database) as db:
            for key,digest in keys.items():
                row=db.execute('SELECT metadata FROM templates WHERE key=?',(key,)).fetchone()
                if row and json.loads(row[0]).get('original_hash')==digest:db.execute("UPDATE templates SET status='withdrawn' WHERE key=?",(key,))
        for name,data in old.items():write(name,data)
        subprocess.run(['systemctl','start','gensticker','gensticker-worker'],check=True)
        print(json.dumps({'status':'rolled back','backup':str(backup),'user_database_not_replaced':True}),flush=True);raise


if __name__=='__main__':main()
