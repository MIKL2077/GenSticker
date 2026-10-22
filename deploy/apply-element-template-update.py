"""Checksum-guarded replacement release; rollback restores only affected templates.

No user/account/job tables are replaced. Keep the old code and template rows
under /var/backups; require an idle application before stopping its two units.
"""
import argparse
import grp
import hashlib
import json
import os
import shutil
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import time
import urllib.request


def main():
    parser=argparse.ArgumentParser()
    for option in ['release','runtime','state']:parser.add_argument('--'+option,required=True)
    args=parser.parse_args();release=Path(args.release).resolve();runtime=Path(args.runtime).resolve()
    manifest=json.loads((release/'release.json').read_text());old={};new={};keys=set()
    assert 0<len(manifest['files'])<120
    for name,checksums in manifest['files'].items():
        relative=Path(name)
        assert not relative.is_absolute() and '..' not in relative.parts and relative.parts[0]=='meme_generator'
        target=runtime/relative;source=release/relative
        assert not target.is_symlink() and target.resolve().is_relative_to(runtime)
        before=target.read_bytes() if target.is_file() else None
        assert (hashlib.sha256(before).hexdigest() if before is not None else None)==checksums['before'],'runtime changed: '+name
        data=source.read_bytes() if checksums['after'] is not None else None
        assert (hashlib.sha256(data).hexdigest() if data is not None else None)==checksums['after'],'release changed: '+name
        if relative.suffix=='.py':
            assert data is not None;compile(data,name,'exec')
        else:
            assert relative.parent.as_posix()=='meme_generator/features/template_batches'
            assert relative.name.startswith(('20261021-reactions-','20261022-elements-'))
            if data:
                batch=json.loads(data)
                for item in batch['templates']:
                    assert item['metadata']['conversion']=='element-replacement-v1' and item['version']==2
                    keys.add(item['key'])
                keys.update(item['key'] for item in batch.get('withdrawals',[]))
        old[name]=before;new[name]=data
    assert len(keys)==manifest['affected']
    database=Path(args.state).resolve()/'features/features.sqlite3'
    def active():
        with sqlite3.connect('file:'+str(database)+'?mode=ro',uri=True) as db:
            return db.execute("SELECT (SELECT count(*) FROM jobs WHERE status IN ('queued','running'))+(SELECT count(*) FROM studio_jobs WHERE status IN ('queued','running'))").fetchone()[0]
    assert active()==0,'active user work; defer deployment'
    with sqlite3.connect('file:'+str(database)+'?mode=ro',uri=True) as db:
        for key,digest in manifest['identities'].items():
            row=db.execute('SELECT version,metadata FROM templates WHERE key=?',(key,)).fetchone()
            assert row and row[0]==1,'template was independently updated: '+key
            metadata=json.loads(row[1])
            assert metadata.get('conversion')=='reaction-story-v1' and metadata.get('original_hash')==digest,'source changed: '+key
    backup=Path('/var/backups')/('gensticker-elements-'+str(int(time.time())));backup.mkdir(mode=0o700)
    for name,data in old.items():
        if data is None:continue
        path=backup/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data);path.chmod(0o600)
    (backup/'release.json').write_text(json.dumps(manifest,indent=2))
    gid=grp.getgrnam('gensticker').gr_gid
    def write(name,data):
        path=runtime/name
        if data is None:path.unlink(missing_ok=True);return
        with tempfile.NamedTemporaryFile(dir=path.parent,prefix='.elements-',delete=False) as output:
            output.write(data);os.fchown(output.fileno(),0,gid);os.fchmod(output.fileno(),0o644);temporary=output.name
        os.replace(temporary,path)
    def wait_health():
        for _ in range(90):
            try:
                with urllib.request.urlopen('http://127.0.0.1:3001/healthz',timeout=2) as response:
                    if response.status==200:return
            except Exception:pass
            time.sleep(1)
        raise RuntimeError('API startup timeout')
    rows=[];versions=[]
    subprocess.run(['systemctl','stop','gensticker','gensticker-worker'],check=True)
    try:
        assert active()==0,'new work arrived; deployment deferred'
        with sqlite3.connect(database) as db,sqlite3.connect(backup/'features.sqlite3') as snapshot:
            db.backup(snapshot)
            db.row_factory=sqlite3.Row
            rows=[dict(row) for row in db.execute('SELECT * FROM templates') if row['key'] in keys]
            ids={row['id'] for row in rows}
            versions=[dict(row) for row in db.execute('SELECT * FROM template_versions') if row['template_id'] in ids]
        (backup/'features.sqlite3').chmod(0o600)
        shutil.copytree(database.parent/'template_assets',backup/'template_assets',copy_function=shutil.copy2)
        (backup/'template-rows.json').write_text(json.dumps({'keys':sorted(keys),'rows':rows,'versions':versions}))
        for name,data in new.items():write(name,data)
        subprocess.run(['systemctl','start','gensticker'],check=True);wait_health()
        subprocess.run(['systemctl','start','gensticker-worker'],check=True)
        with urllib.request.urlopen('http://127.0.0.1:3001/memes/categories',timeout=30) as response:catalog=json.load(response)
        assert len(catalog['all'])==manifest['expected_total'],'catalog total differs'
        with sqlite3.connect(database) as db:
            published=[json.loads(row[0]) for row in db.execute("SELECT metadata FROM templates WHERE status='published'")]
            assert sum(m.get('conversion')=='element-replacement-v1' for m in published)==manifest['published']
            assert not any(m.get('conversion')=='reaction-story-v1' for m in published)
        for service in ['gensticker','gensticker-worker']:subprocess.run(['systemctl','is-active','--quiet',service],check=True)
        for url in ['http://127.0.0.1:3003/','http://127.0.0.1:18789/healthz']:
            with urllib.request.urlopen(url,timeout=5) as response:assert response.status==200
        print(json.dumps({'status':'passed','backup':str(backup),'replaced':manifest['published'],'withdrawn':manifest['affected']-manifest['published'],
                          'total':len(catalog['all']),'animated':sum(c.get('animated',False) for c in catalog['cards']),
                          'categories':{k:len(catalog[k]) for k in ['image_only','mixed','text_only']},'other_services_healthy':True}),flush=True)
    except BaseException:
        subprocess.run(['systemctl','stop','gensticker','gensticker-worker'],check=False)
        if rows:
            with sqlite3.connect(database) as db:
                for key in keys:
                    row=db.execute('SELECT id FROM templates WHERE key=?',(key,)).fetchone()
                    if row:db.execute('DELETE FROM template_versions WHERE template_id=?',(row[0],))
                    db.execute('DELETE FROM templates WHERE key=?',(key,))
                for table,records in [('templates',rows),('template_versions',versions)]:
                    for record in records:
                        fields=','.join(record);placeholders=','.join('?' for _ in record)
                        db.execute(f'INSERT INTO {table}({fields}) VALUES({placeholders})',tuple(record.values()))
        for name,data in old.items():write(name,data)
        if (backup/'template_assets').exists():
            shutil.copytree(backup/'template_assets',database.parent/'template_assets',dirs_exist_ok=True,copy_function=shutil.copy2)
        subprocess.run(['systemctl','start','gensticker','gensticker-worker'],check=True)
        print(json.dumps({'status':'rolled back','backup':str(backup),'user_database_not_replaced':True}),flush=True)
        raise


if __name__=='__main__':main()
