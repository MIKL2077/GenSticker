#!/bin/bash
set -euo pipefail
archive=${1:-/tmp/gensticker-editor-v3.tar.gz}
base=/opt/gensticker/meme-generator
backup=/opt/gensticker/backups/editor-v3-$(date +%Y%m%d-%H%M%S)
nginx_conf=/etc/nginx/conf.d/nginx-gensticker.conf
install -d -m 700 "$backup"
tar -czf "$backup/source-before.tar.gz" -C "$base" meme_generator
cp -p "$nginx_conf" "$backup/nginx-before.conf"
for name in /var/www/gensticker-live/live-setup.html /opt/gensticker/static/live-setup.html; do
 if [ -f "$name" ]; then cp -p "$name" "$backup/guide-before.html"; fi
done
restore(){
 status=$?
 if [ "$status" -ne 0 ]; then
  systemctl stop gensticker gensticker-worker || true
  tar -xzf "$backup/source-before.tar.gz" -C "$base"
  cp -p "$backup/nginx-before.conf" "$nginx_conf"
  if [ -f "$backup/guide-before.html" ]; then install -d -m 755 /var/www/gensticker-live; cp -p "$backup/guide-before.html" /var/www/gensticker-live/live-setup.html; fi
  python3 - "$backup" <<'PY'
import sqlite3,sys
from pathlib import Path
backup=Path(sys.argv[1]);target=Path('/var/lib/gensticker/features/features.sqlite3')
if (backup/'features.sqlite3').exists():
 with sqlite3.connect(backup/'features.sqlite3') as source:
  if source.execute("SELECT 1 FROM sqlite_master WHERE name='live_imports'").fetchone():
   rows=source.execute('SELECT id,user_id,created,status,asset_id FROM live_imports').fetchall()
   with sqlite3.connect(target) as destination:
    destination.execute('CREATE TABLE IF NOT EXISTS live_imports(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,created REAL NOT NULL,status TEXT NOT NULL,asset_id TEXT)')
    destination.executemany('INSERT OR REPLACE INTO live_imports VALUES(?,?,?,?,?)',rows)

PY
  nginx -t && systemctl reload nginx || true
  systemctl start gensticker gensticker-worker || true
 fi
 exit "$status"
}
trap restore EXIT
systemctl stop gensticker gensticker-worker
python3 - "$backup" "$archive" "$base" "$nginx_conf" <<'PY'
import ast,re,sqlite3,sys,tarfile
from pathlib import Path
backup,archive,base,nginx=map(Path,sys.argv[1:])
for source,name in [(Path('/var/lib/gensticker/accounts.sqlite3'),'accounts.sqlite3'),(Path('/var/lib/gensticker/features/features.sqlite3'),'features.sqlite3')]:
 if source.exists():
  with sqlite3.connect(source) as src,sqlite3.connect(backup/name) as dst:src.backup(dst)
allowed={'meme_generator/app.py'}|{'meme_generator/features/'+name+'.py' for name in ('animation','caption','declarative','livegif','portrait','recommend','vision','worker')}
with tarfile.open(archive) as package:
 members=package.getmembers()
 if {member.name for member in members}!=allowed or any(not member.isfile() for member in members):raise SystemExit('Unexpected package contents')
 for member in members:
  content=package.extractfile(member).read();ast.parse(content);target=base/member.name;target.write_bytes(content);target.chmod(0o644)
(base/'meme_generator/features/live_import.py').unlink(missing_ok=True)
for path in (base/'meme_generator/features/__pycache__').glob('live_import.*.pyc'):path.unlink()
for path in (Path('/var/www/gensticker-live/live-setup.html'),Path('/opt/gensticker/static/live-setup.html')):path.unlink(missing_ok=True)
with sqlite3.connect('/var/lib/gensticker/features/features.sqlite3') as db:db.execute('DROP TABLE IF EXISTS live_imports')
text=nginx.read_text()
# Retire the old capability endpoint and tutorial. Keep originals private.
for url in ('/gensticker/live-setup.html','/gensticker/api/studio/live/imports/receive'):
 text=re.sub(r'    location = '+re.escape(url)+r' \{[^}]*\}\n','',text)
marker='    location = /gensticker/api/studio/live/results {'
if marker not in text:raise SystemExit('Live proxy missing')
if 'location = /gensticker/api/recommend/subjects/detect {' not in text:
 text=text.replace(marker,'''    location = /gensticker/api/recommend/subjects/detect {
        limit_req zone=gensticker_jobs burst=10 nodelay;
        client_max_body_size 4m;
        rewrite ^/gensticker/api/(.*)$ /$1 break;
        proxy_pass http://127.0.0.1:3001;
        proxy_read_timeout 25s;
    }
'''+marker)
if 'location ^~ /gensticker/api/studio/live/imports' not in text:text=text.replace(marker,'    location ^~ /gensticker/api/studio/live/imports { return 410; }\n'+marker)
text=text.replace(marker,'    location = /gensticker/live-setup.html { return 410; }\n'+marker)
nginx.write_text(text)
PY
nginx -t
systemctl start gensticker gensticker-worker
ready=0
for attempt in $(seq 1 30); do
 if curl --fail --silent --max-time 2 http://127.0.0.1:3001/healthz > "$backup/health-after.json"; then ready=1; break; fi
 sleep 1
done
[ "$ready" = 1 ]
systemctl reload nginx
systemctl is-active gensticker gensticker-worker nginx
printf '%s\n' "Backup: $backup"
trap - EXIT
