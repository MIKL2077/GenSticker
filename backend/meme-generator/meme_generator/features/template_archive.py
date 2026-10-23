"""Monthly public-template retirement into a dedicated GitHub branch.

Sparse bare Git transfers avoid retaining the archive on the application host.
Only verified remote objects permit local eviction. Private/user material never
enters an archive. Restore retains UUIDs, versions and original publication state.
"""
from contextlib import contextmanager
from datetime import datetime,timedelta,timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path,PurePosixPath
import re
import shutil
import subprocess
import tempfile
import time
from .store import connect,root
from .storage import asset_refs,exclusive


class ArchiveError(ValueError):pass


def digest(data):return hashlib.sha256(data).hexdigest()

def json_bytes(value):return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()


class GitArchive:
    def __init__(self,remote=None,*,local_test=False):
        self.remote=remote or os.getenv('GENSTICKER_ARCHIVE_REMOTE','')
        if not (local_test and self.remote.startswith('/')) and not re.fullmatch(r'git@github\.com:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\.git',self.remote):raise ArchiveError('archive_repository_not_configured')
        self.branch=os.getenv('GENSTICKER_ARCHIVE_BRANCH','template-archive')
        if not re.fullmatch(r'[A-Za-z0-9_.-]+',self.branch):raise ArchiveError('invalid_archive_branch')
        self.env={**os.environ,'GIT_TERMINAL_PROMPT':'0','GIT_AUTHOR_NAME':'GenSticker Archive','GIT_AUTHOR_EMAIL':'archive@gensticker.invalid','GIT_COMMITTER_NAME':'GenSticker Archive','GIT_COMMITTER_EMAIL':'archive@gensticker.invalid'}
        key=os.getenv('GENSTICKER_ARCHIVE_SSH_KEY','');known=os.getenv('GENSTICKER_ARCHIVE_KNOWN_HOSTS','')
        if key:
            import shlex
            self.env['GIT_SSH_COMMAND']='ssh -i '+shlex.quote(key)+' -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile='+shlex.quote(known)+' -o BatchMode=yes -o ConnectTimeout=15'

    def git(self,folder,*args,input=None,check=True):
        try:result=subprocess.run(['git','-C',str(folder),*args],input=input,capture_output=True,env=self.env,timeout=180)
        except subprocess.TimeoutExpired:raise ArchiveError('archive_git_timeout:'+args[0]) from None
        if check and result.returncode:raise ArchiveError('archive_git_operation_failed:'+args[0])
        return result.stdout

    @contextmanager
    def workspace(self,commit=''):
        with tempfile.TemporaryDirectory(prefix='archive-work-',dir=root()) as name:
            path=Path(name);self.git(path,'init','--bare','--quiet');self.git(path,'remote','add','origin',self.remote)
            head=self.git(path,'ls-remote','origin','refs/heads/'+self.branch).decode().strip()
            if head:
                self.git(path,'config','remote.origin.promisor','true');self.git(path,'config','remote.origin.partialclonefilter','blob:none')
                self.git(path,'fetch','--quiet','--filter=blob:none','--depth=1','origin',commit or 'refs/heads/'+self.branch)
                revision=self.git(path,'rev-parse','FETCH_HEAD').decode().strip()
            elif commit:raise ArchiveError('archive_commit_missing')
            else:revision=''
            yield path,revision

    @staticmethod
    def checked_path(name):
        path=PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or not path.parts or any(not re.fullmatch(r'[A-Za-z0-9_.-]+',part) for part in path.parts):raise ArchiveError('invalid_archive_path')
        return str(path)

    def put(self,files,message):
        # An index plus read-tree preserves older archive objects without checking
        # their binary contents out on the application disk.
        with self.workspace() as (folder,parent):
            index=folder/'archive.index';self.env['GIT_INDEX_FILE']=str(index)
            try:
                if parent:self.git(folder,'read-tree',parent)
                additions=[]
                for name,data in sorted(files.items()):
                    name=self.checked_path(name)
                    if len(data)>32*1024**2:raise ArchiveError('archive_object_too_large')
                    blob=self.git(folder,'hash-object','-w','--stdin',input=data).decode().strip()
                    additions.append(('100644 '+blob+'\t'+name+'\0').encode())
                self.git(folder,'update-index','-z','--index-info',input=b''.join(additions))
                # All old blobs are already on the remote. Checking every
                # promisor blob here would download the entire growing archive.
                tree=self.git(folder,'write-tree','--missing-ok').decode().strip();args=['commit-tree',tree]
                if parent:args+=['-p',parent]
                commit=self.git(folder,*args,input=(message+'\n').encode()).decode().strip()
                self.git(folder,'push','--quiet','origin',commit+':refs/heads/'+self.branch)
            finally:self.env.pop('GIT_INDEX_FILE',None)
        # A new independent fetch proves that GitHub, rather than only our local
        # object database, can serve every archived byte.
        with self.workspace(commit) as (folder,revision):
            restored_files=self.read_files(folder,revision,list(files))
            for name,data in files.items():
                restored=restored_files[name]
                if digest(restored)!=digest(data):raise ArchiveError('remote_archive_verification_failed')
        return commit

    def read_files(self,folder,revision,names):
        names=[self.checked_path(name) for name in names]
        if not names:return {}
        # Partial-clone lazy fetch otherwise creates one SSH connection per
        # artwork blob. Prefetch this template's exact objects in one request;
        # never fetch the archive's unrelated image contents.
        entries=self.git(folder,'ls-tree','-r','-z',revision,'--',*names).split(b'\0')
        objects=set()
        for entry in entries:
            if not entry:continue
            header,path=entry.split(b'\t',1);mode,kind,oid=header.split()
            if kind!=b'blob' or path.decode() not in names:raise ArchiveError('invalid_archive_object')
            objects.add(oid.decode())
        if len(entries)-1!=len(set(names)):raise ArchiveError('archive_object_missing')
        self.git(folder,'-c','fetch.negotiationAlgorithm=noop','fetch','--quiet','--no-tags','--filter=blob:none','origin',*sorted(objects))
        return {name:self.git(folder,'show',revision+':'+name) for name in names}

    def get(self,commit,names):
        if not re.fullmatch('[0-9a-f]{40}',commit):raise ArchiveError('invalid_archive_commit')
        with self.workspace(commit) as (folder,revision):return self.read_files(folder,revision,names)


def public_record(row):
    metadata=json.loads(row['metadata'])
    if metadata.get('origin') in {'user','user-provided','studio','private'} or metadata.get('creator') or metadata.get('user_id'):raise ArchiveError('private_or_user_template_excluded')
    if not row['spec']:raise ArchiveError('bundled_templates_retained_as_runtime_baseline')
    return metadata


def protected_keys(db):
    keys=set()
    # A template used by a queued job or any retained generated result stays local.
    if db.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0]:raise ArchiveError('active_recommendation_jobs_defer_archiving')
    keys.update(r[0] for r in db.execute('SELECT DISTINCT key FROM results'))
    tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'studio_jobs' in tables:
        for row in db.execute('SELECT payload FROM studio_jobs'):
            try:
                payload=json.loads(row[0]);key=payload.get('template_key') or payload.get('key')
                if key:keys.add(key)
            except ValueError:raise ArchiveError('job_references_require_review')
    from ..account import connection
    account_db=connection()
    try:keys.update(r[0] for r in account_db.execute('SELECT DISTINCT key FROM favorites'))
    finally:account_db.close()
    return keys


def archive_template(key,store=None):
    store=store or GitArchive();db=connect()
    try:
        row=db.execute('SELECT * FROM templates WHERE key=?',(key,)).fetchone()
        if not row or row['status'] not in {'published','withdrawn'}:raise ArchiveError('template_not_archivable')
        metadata=public_record(row)
        if key in protected_keys(db):raise ArchiveError('template_is_still_in_use_or_favorited')
        versions=[dict(v) for v in db.execute('SELECT * FROM template_versions WHERE template_id=? ORDER BY version',(row['id'],))]
        refs=set()
        for version in versions:
            if version['spec']:refs.update(asset_refs(version['spec']))
        refs.update(asset_refs(row['spec']))
        files={};assets={}
        for ref in refs:
            found=[p for suffix in ['.png','.gif'] if (p:=root()/'template_assets'/(ref+suffix)).is_file()]
            if not found:raise ArchiveError('archive_asset_missing')
            for path in found:
                data=path.read_bytes()
                if digest(data)!=ref:raise ArchiveError('archive_asset_hash_mismatch')
                name='assets/'+path.name;files[name]=data;assets[name]={'sha256':ref,'bytes':len(data)}
        manifest={'format':'gensticker-template-archive-v1','template':dict(row),'versions':versions,'assets':assets,'created':time.time()}
        name='templates/'+key+'/'+str(row['version'])+'-'+row['fingerprint'][:16]+'.json';data=json_bytes(manifest);files[name]=data
        archived_bytes=sum(len(value) for value in files.values())
        used=db.execute('SELECT coalesce(sum(bytes),0) FROM template_archives WHERE NOT (key=? AND version=?)',(key,row['version'])).fetchone()[0]
        if used+archived_bytes>int(os.getenv('GENSTICKER_ARCHIVE_MAX_BYTES',str(3*1024**3))):raise ArchiveError('github_archive_budget_reached')
    finally:db.close()
    commit=store.put(files,'Archive public template '+key+' version '+str(row['version']))
    with exclusive():
        db=connect()
        try:
            current=db.execute('SELECT * FROM templates WHERE key=?',(key,)).fetchone()
            if not current or current['fingerprint']!=row['fingerprint'] or current['version']!=row['version'] or current['status']!=row['status']:raise ArchiveError('template_changed_during_archive')
            if key in protected_keys(db):raise ArchiveError('template_became_active_during_archive')
            with db:
                db.execute('INSERT INTO template_archives VALUES(?,?,?,?,?,?,?,0) ON CONFLICT(key,version) DO UPDATE SET commit_id=excluded.commit_id,manifest_path=excluded.manifest_path,manifest_sha=excluded.manifest_sha,archived=excluded.archived,bytes=excluded.bytes,restored=0',(key,row['version'],commit,name,digest(data),time.time(),archived_bytes))
                db.execute("UPDATE templates SET status='archived',spec=NULL WHERE key=?",(key,))
                db.execute('UPDATE template_versions SET spec=NULL WHERE template_id=?',(row['id'],))
            retained=set()
            for table in ['templates','template_versions','studio_templates']:
                if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone():
                    for v in db.execute('SELECT spec FROM '+table+' WHERE spec IS NOT NULL'):retained.update(asset_refs(v[0]))
            freed=0
            for ref in refs-retained:
                for suffix in ['.png','.gif']:
                    path=root()/'template_assets'/(ref+suffix)
                    if path.is_file() and not path.is_symlink():freed+=path.stat().st_size;path.unlink()
        finally:db.close()
    return {'key':key,'status':'archived','commit':commit,'bytes_freed':freed,'archive_bytes':archived_bytes}


def repair_archive_states():
    """Recover only verified, non-restored archive records whose retired seed
    status was changed during startup; never touch live artwork or user rows."""
    with exclusive():
        db=connect()
        try:
            with db:
                result=db.execute("UPDATE templates SET status='archived' WHERE status='withdrawn' AND spec IS NULL AND EXISTS (SELECT 1 FROM template_archives a WHERE a.key=templates.key AND a.version=templates.version AND a.restored=0)")
            return result.rowcount
        finally:db.close()


def restore_template(key,version=None,store=None):
    repair_archive_states()
    store=store or GitArchive();db=connect()
    try:
        archive=db.execute('SELECT * FROM template_archives WHERE key=?'+(' AND version=?' if version else '')+' ORDER BY version DESC LIMIT 1',(key,version) if version else (key,)).fetchone()
        if not archive:raise ArchiveError('archive_record_missing')
        record=dict(archive)
    finally:db.close()
    raw=store.get(record['commit_id'],[record['manifest_path']])[record['manifest_path']]
    if digest(raw)!=record['manifest_sha']:raise ArchiveError('archive_manifest_hash_mismatch')
    manifest=json.loads(raw)
    if manifest.get('format')!='gensticker-template-archive-v1' or manifest['template']['key']!=key or manifest['template']['version']!=record['version']:raise ArchiveError('archive_identity_mismatch')
    files=store.get(record['commit_id'],list(manifest['assets']))
    for name,info in manifest['assets'].items():
        if not re.fullmatch(r'assets/[0-9a-f]{64}\.(png|gif)',name) or digest(files[name])!=info['sha256'] or len(files[name])!=info['bytes']:raise ArchiveError('archive_asset_verification_failed')
    with exclusive():
        db=connect()
        try:
            existing=db.execute('SELECT * FROM templates WHERE key=?',(key,)).fetchone()
            if existing and existing['status']!='archived':raise ArchiveError('restore_would_overwrite_live_template')
            original=manifest['template']
            if original['status']=='published' and db.execute("SELECT count(*) FROM templates WHERE status='published'").fetchone()[0]>=min(8000,int(os.getenv('GENSTICKER_PUBLIC_TEMPLATE_LIMIT','8000'))):raise ArchiveError('restore_requires_free_catalog_slot')
            from .storage import state_usage,limit
            incoming=sum(len(v) for v in files.values());used,count=state_usage()
            if used+incoming>limit('STATE_MAX_BYTES',12*1024**3) or count+len(files)>limit('STATE_MAX_FILES',100000) or shutil.disk_usage(root()).free-incoming<limit('MIN_FREE_BYTES',10*1024**3):raise ArchiveError('restore_storage_budget_reached')
            directory=root()/'template_assets';directory.mkdir(exist_ok=True)
            for name,data in files.items():
                path=directory/PurePosixPath(name).name;temporary=path.with_suffix(path.suffix+'.partial');temporary.write_bytes(data);os.replace(temporary,path)
            with db:
                fields=['id','key','version','fingerprint','metadata','spec','status']
                db.execute('INSERT OR REPLACE INTO templates('+','.join(fields)+') VALUES(?,?,?,?,?,?,?)',[original[k] for k in fields])
                for value in manifest['versions']:
                    fields=['template_id','version','fingerprint','metadata','spec'];db.execute('INSERT OR REPLACE INTO template_versions VALUES(?,?,?,?,?)',[value[k] for k in fields])
                db.execute('UPDATE template_archives SET restored=? WHERE key=? AND version=?',(time.time(),key,record['version']))
        finally:db.close()
    return {'key':key,'version':original['version'],'status':original['status'],'restored_bytes':incoming}


def monthly(*,force=False,store=None):
    repair_archive_states()
    stamp=time.time();month=datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m');db=connect()
    try:
        prior=db.execute('SELECT report FROM template_monthly_reports WHERE month=?',(month,)).fetchone()
        previous=json.loads(prior[0]) if prior else None
        if previous and not force and previous.get('status')=='completed':return previous
        history=previous.get('archived',[]) if previous and not force else []
        rows=list(db.execute("SELECT * FROM templates WHERE status IN ('published','withdrawn')"));protected=protected_keys(db)
        counts={status:sum(r['status']==status for r in rows) for status in ['published','withdrawn']}
        recent={r[0] for r in db.execute("SELECT DISTINCT key FROM popularity_daily WHERE day>=date('now','-30 days') AND kind IN ('generate','client_generate','ai_generate','ai_choose','favorite') AND count>0")}
        eligible=[]
        for row in rows:
            if row['key'] in protected|recent:continue
            try:metadata=public_record(row)
            except ArchiveError:continue
            created=float(metadata.get('created_at') or metadata.get('collected_at') or stamp)
            if row['status']=='withdrawn' or (created<stamp-90*86400 and counts['published']>1000):eligible.append(row)
        eligible.sort(key=lambda r:(r['status']!='withdrawn',float(json.loads(r['metadata']).get('created_at') or 0),r['key']))
        report={'month':month,'sampled':stamp,'catalog_limit':8000,'before':previous['before'] if history else counts,'pass_before':counts,'selected':len(eligible)+len(history),'archived':list(history),'errors':[],'protected_templates':len(protected),'public_runtime_baseline_preserved':sum(json.loads(r['metadata']).get('origin')=='bundled' for r in rows),'policy':'withdrawn public sources first; then >90 days old and no 30-day usage; favorites and retained jobs protected; builtin and user templates remain local'}
    finally:db.close()
    report['status']='running'
    def progress():
        db=connect()
        try:
            with db:db.execute('INSERT OR REPLACE INTO template_monthly_reports VALUES(?,?,?)',(month,time.time(),json.dumps(report,ensure_ascii=False)))
        finally:db.close()
    progress()
    completed_this_pass=0;published_this_pass=0
    for row in eligible[:1000]:
        if time.time()-stamp>5400:break
        if row['status']=='published' and counts['published']-published_this_pass<=1000:break
        try:
            result=archive_template(row['key'],store);result['was_published']=row['status']=='published';report['archived'].append(result);completed_this_pass+=1;published_this_pass+=int(result['was_published']);progress()
        except (ValueError,OSError) as error:
            report['errors'].append({'key':row['key'],'reason':str(error)[:140]})
            # Broken connectivity/configuration must not loop through 1000 items.
            if 'git_' in str(error) or 'not_configured' in str(error) or 'budget' in str(error):break
    report['remaining']=max(0,len(eligible)-completed_this_pass)
    report['local_bytes_freed']=sum(item['bytes_freed'] for item in report['archived'])
    report['uploaded_bytes']=sum(item['archive_bytes'] for item in report['archived'])
    report['status']='attention' if report['errors'] or report['remaining'] else 'completed'
    db=connect()
    try:
        with db:db.execute('INSERT OR REPLACE INTO template_monthly_reports VALUES(?,?,?)',(month,time.time(),json.dumps(report,ensure_ascii=False)))
    finally:db.close()
    return report


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('operation',choices=['monthly','restore','archive','list','report']);p.add_argument('--key');p.add_argument('--version',type=int);p.add_argument('--force',action='store_true');a=p.parse_args()
    with (root()/'archive.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if a.operation=='list':
            db=connect()
            try:result=[dict(row) for row in db.execute("SELECT a.key,a.version,a.archived,a.restored,a.bytes,json_extract(t.metadata,'$.name') name FROM template_archives a LEFT JOIN templates t ON t.key=a.key ORDER BY a.archived DESC LIMIT 1000")]
            finally:db.close()
        elif a.operation=='report':
            db=connect()
            try:result=[json.loads(row[0]) for row in db.execute('SELECT report FROM template_monthly_reports ORDER BY month DESC LIMIT 12')]
            finally:db.close()
        elif a.operation=='monthly':result=monthly(force=a.force)
        elif not a.key:raise SystemExit('--key required')
        elif a.operation=='restore':result=restore_template(a.key,a.version)
        else:result=archive_template(a.key)
        print(json.dumps(result,ensure_ascii=False),flush=True)
        raise SystemExit(1 if isinstance(result,dict) and result.get('status')=='attention' else 0)
