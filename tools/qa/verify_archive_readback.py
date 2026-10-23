"""Verify an existing GitHub archive without restoring/retiring live templates."""
import json
import sqlite3
import time
from meme_generator.features.store import root
from meme_generator.features.template_archive import GitArchive,digest


def main():
    started=time.monotonic();db=sqlite3.connect('file:'+str(root()/'features.sqlite3')+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
    try:row=db.execute('SELECT * FROM template_archives ORDER BY archived DESC LIMIT 1').fetchone()
    finally:db.close()
    if not row:raise ValueError('no existing archive to inspect')
    store=GitArchive();raw=store.get(row['commit_id'],[row['manifest_path']])[row['manifest_path']]
    if digest(raw)!=row['manifest_sha']:raise ValueError('manifest hash differs')
    manifest=json.loads(raw);files=store.get(row['commit_id'],list(manifest['assets']))
    for name,info in manifest['assets'].items():
        if digest(files[name])!=info['sha256'] or len(files[name])!=info['bytes']:raise ValueError('asset differs')
    print(json.dumps({'status':'passed','key':row['key'],'objects':len(files)+1,'bytes':sum(map(len,files.values()))+len(raw),'seconds':round(time.monotonic()-started,1),'live_state_mutated':False}))


if __name__=='__main__':main()
