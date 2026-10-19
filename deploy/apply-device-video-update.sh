#!/bin/bash
set -euo pipefail
archive=${1:-/tmp/gensticker-device-video.tar.gz}
base=/opt/gensticker/meme-generator
backup=/opt/gensticker/backups/device-video-$(date +%Y%m%d-%H%M%S)
nginx_conf=/etc/nginx/conf.d/nginx-gensticker.conf
install -d -m 700 "$backup"
tar -czf "$backup/source-before.tar.gz" -C "$base" meme_generator
cp -p "$nginx_conf" "$backup/nginx-before.conf"
restore(){
 status=$?
 if [ "$status" -ne 0 ]; then
  systemctl stop gensticker gensticker-worker || true
  tar -xzf "$backup/source-before.tar.gz" -C "$base"
  cp -p "$backup/nginx-before.conf" "$nginx_conf"
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
allowed={'meme_generator/features/livegif.py','meme_generator/features/vision.py','meme_generator/features/portrait.py'}
with tarfile.open(archive) as package:
 members=package.getmembers()
 if {m.name for m in members}!=allowed or any(not m.isfile() for m in members):raise SystemExit('Unexpected package contents')
 for member in members:
  content=package.extractfile(member).read();ast.parse(content);target=base/member.name;target.write_bytes(content);target.chmod(0o644)
text=nginx.read_text().replace('zone=gensticker_jobs:10m rate=6r/m','zone=gensticker_jobs:10m rate=60r/m').replace('limit_req zone=gensticker_jobs burst=3 nodelay','limit_req zone=gensticker_jobs burst=20 nodelay')
marker='    location = /gensticker/api/studio/live/assets {'
if 'location = /gensticker/api/studio/live/results {' not in text:
 if marker not in text:raise SystemExit('Live upload proxy missing')
 text=text.replace(marker,'''    location = /gensticker/api/studio/live/results {
        limit_req zone=gensticker_generate burst=5 nodelay;
        client_max_body_size 520k;
        rewrite ^/gensticker/api/(.*)$ /$1 break;
        proxy_pass http://127.0.0.1:3001;
        proxy_read_timeout 20s;
    }
'''+marker)
text=text.replace('client_max_body_size 31m;','client_max_body_size 61m;')
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
