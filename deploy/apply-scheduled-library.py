#!/usr/bin/env python3
"""Apply a hash-checked runtime delta; preserve state and unrelated host services.
New timers are enabled separately after actual visual and GitHub acceptance.
"""
from pathlib import Path
import hashlib,json,os,shutil,subprocess,time,urllib.request


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None

def command(*args):return subprocess.run(args,capture_output=True,text=True,check=True).stdout.strip()

def main():
    package=Path(__file__).parent;manifest=json.loads((package/'manifest.json').read_text());release=Path('/opt/gensticker-current').resolve()
    if str(release)!=manifest['release']:raise SystemExit('release changed since preparation')
    target=release/'meme-generator'
    for name,info in manifest['files'].items():
        if Path(name).is_absolute() or '..' in Path(name).parts:raise SystemExit('invalid runtime file')
        if sha(target/name)!=info['old_sha256'] or sha(package/'runtime'/name)!=info['sha256']:raise SystemExit('runtime changed: '+name)
    # Do not restart a worker while it owns a user's task.
    import sqlite3
    db=sqlite3.connect('file:/var/lib/gensticker/features/features.sqlite3?mode=ro',uri=True)
    count=db.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0]
    tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'studio_jobs' in tables:count+=db.execute("SELECT count(*) FROM studio_jobs WHERE status IN ('queued','running')").fetchone()[0]
    db.close()
    if count:raise SystemExit('defer deployment until current user jobs finish')
    backup=Path('/var/backups')/('gensticker-scheduled-library-'+str(int(time.time())));backup.mkdir(mode=0o700)
    # Preserve the template versions before bootstrap restores reviewed additions.
    source=sqlite3.connect('/var/lib/gensticker/features/features.sqlite3')
    destination=sqlite3.connect(backup/'features.sqlite3')
    try:source.backup(destination)
    finally:destination.close();source.close()
    wrapper=Path('/usr/local/sbin/gensticker-template-admin')
    if wrapper.exists():shutil.copy2(wrapper,backup/wrapper.name)
    changed=[]
    try:
        for name in manifest['files']:
            dst=target/name
            if dst.exists():
                old=backup/'runtime'/name;old.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(dst,old)
            dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(package/'runtime'/name,dst);changed.append(name)
        for name in ['gensticker-ingest.service','gensticker-archive.service','gensticker-archive.timer']:
            dst=Path('/etc/systemd/system')/name
            if dst.exists():shutil.copy2(dst,backup/name)
            shutil.copy2(package/name,dst)
        command('systemd-analyze','verify','/etc/systemd/system/gensticker-ingest.service','/etc/systemd/system/gensticker-archive.service','/etc/systemd/system/gensticker-archive.timer')
        shutil.copy2(package/'gensticker-template-admin',wrapper);wrapper.chmod(0o750)
        command('systemctl','daemon-reload');command('systemctl','restart','gensticker-worker');command('systemctl','restart','gensticker')
        for attempt in range(90):
            try:
                with urllib.request.urlopen('http://127.0.0.1:3001/healthz',timeout=3) as response:health=json.load(response)
                with urllib.request.urlopen('http://127.0.0.1:3001/templates/trial',timeout=3) as response:trial=json.load(response)
                if health['status']=='ok' and health['templates']>=manifest['minimum_templates'] and trial:break
            except Exception:time.sleep(1)
        else:raise RuntimeError('health/trial validation failed')
        print(json.dumps({'status':'passed','release':str(release),'backup':str(backup),'files':len(changed),'templates':health['templates'],'trial':trial,'timers_enabled':False},ensure_ascii=False))
    except Exception:
        for name in changed:
            dst=target/name;old=backup/'runtime'/name
            if old.exists():shutil.copy2(old,dst)
            else:dst.unlink(missing_ok=True)
        for name in ['gensticker-ingest.service','gensticker-archive.service','gensticker-archive.timer']:
            dst=Path('/etc/systemd/system')/name;old=backup/name
            if old.exists():shutil.copy2(old,dst)
            else:dst.unlink(missing_ok=True)
        if (backup/wrapper.name).exists():shutil.copy2(backup/wrapper.name,wrapper)
        else:wrapper.unlink(missing_ok=True)
        command('systemctl','daemon-reload');command('systemctl','restart','gensticker-worker');command('systemctl','restart','gensticker');raise


if __name__=='__main__':main()
