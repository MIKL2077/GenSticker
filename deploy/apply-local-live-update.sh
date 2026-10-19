#!/bin/bash
set -euo pipefail
archive=${1:-/tmp/gensticker-local-live.tar.gz}
base=/opt/gensticker/meme-generator
backup=/opt/gensticker/backups/local-live-$(date +%Y%m%d-%H%M%S)
nginx_conf=/etc/nginx/conf.d/nginx-gensticker.conf
install -d -m 700 "$backup"
tar -czf "$backup/source-before.tar.gz" -C "$base" meme_generator
cp -p "$nginx_conf" "$backup/nginx-before.conf"
if [ -f /var/www/gensticker-live/live-setup.html ]; then cp -p /var/www/gensticker-live/live-setup.html "$backup/guide-before.html"; fi
restore(){
 status=$?
 if [ "$status" -ne 0 ]; then
  systemctl stop gensticker gensticker-worker || true
  tar -xzf "$backup/source-before.tar.gz" -C "$base"
  cp -p "$backup/nginx-before.conf" "$nginx_conf"
  if [ -f "$backup/guide-before.html" ]; then cp -p "$backup/guide-before.html" /var/www/gensticker-live/live-setup.html; else rm -f /var/www/gensticker-live/live-setup.html; fi
  nginx -t && systemctl reload nginx || true
  systemctl start gensticker gensticker-worker || true
 fi
 exit "$status"
}
trap restore EXIT
systemctl stop gensticker gensticker-worker
python3 - "$backup" "$archive" "$base" "$nginx_conf" <<'PY'
import ast,sqlite3,sys,tarfile
from pathlib import Path
backup,archive,base,nginx=map(Path,sys.argv[1:])
for source,name in [(Path('/var/lib/gensticker/accounts.sqlite3'),'accounts.sqlite3'),(Path('/var/lib/gensticker/features/features.sqlite3'),'features.sqlite3')]:
 if source.exists():
  with sqlite3.connect(source) as src,sqlite3.connect(backup/name) as dst:src.backup(dst)
allowed={'meme_generator/app.py','meme_generator/features/livegif.py','meme_generator/features/live_import.py','static/live-setup.html'}
with tarfile.open(archive) as package:
 members=package.getmembers()
 if {m.name for m in members}!=allowed or any(not m.isfile() for m in members):raise SystemExit('Unexpected package contents')
 for member in members:
  content=package.extractfile(member).read()
  if member.name.endswith('.py'):
   ast.parse(content);target=base/member.name
  else:target=Path('/var/www/gensticker-live/live-setup.html');target.parent.mkdir(mode=0o755,exist_ok=True)
  target.write_bytes(content);target.chmod(0o644)
text=nginx.read_text()
marker='    location = /gensticker/api/studio/live/results {'
if 'location = /gensticker/api/studio/live/imports/receive {' not in text:
 if marker not in text:raise SystemExit('Live proxy missing')
 text=text.replace(marker,'''    location = /gensticker/live-setup.html {
        alias /var/www/gensticker-live/live-setup.html;
        default_type text/html;
        add_header Cache-Control "no-store" always;
        add_header X-Content-Type-Options "nosniff" always;
    }
    location = /gensticker/api/studio/live/imports/receive {
        limit_req zone=gensticker_generate burst=3 nodelay;
        client_max_body_size 8m;
        client_body_timeout 30s;
        rewrite ^/gensticker/api/(.*)$ /$1 break;
        proxy_pass http://127.0.0.1:3001;
        proxy_read_timeout 65s;
    }
'''+marker)
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
