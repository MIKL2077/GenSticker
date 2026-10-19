#!/bin/bash
# Focused update for the already-authorised GenSticker deployment.
set -euo pipefail
archive=${1:-/tmp/gensticker-editor-live.tar.gz}
base=/opt/gensticker/meme-generator
backup=/opt/gensticker/backups/editor-live-$(date +%Y%m%d-%H%M%S)
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
  printf '%s\n' 'Update failed; previous source and Nginx restored.' >&2
 fi
 exit "$status"
}
trap restore EXIT
command -v ffmpeg >/dev/null
command -v ffprobe >/dev/null
systemctl stop gensticker gensticker-worker
python3 - "$backup" "$archive" "$base" "$nginx_conf" <<'PY'
import ast,sqlite3,sys,tarfile
from pathlib import Path
backup,archive,base,nginx=map(Path,sys.argv[1:])
for source,name in [(Path('/var/lib/gensticker/accounts.sqlite3'),'accounts.sqlite3'),(Path('/var/lib/gensticker/features/features.sqlite3'),'features.sqlite3')]:
 if source.exists():
  with sqlite3.connect(source) as src,sqlite3.connect(backup/name) as dst:src.backup(dst)
allowed={'meme_generator/account.py','meme_generator/app.py','meme_generator/features/editor.py','meme_generator/features/livegif.py','meme_generator/features/subjects.py','meme_generator/features/studio.py','meme_generator/features/recommend.py','meme_generator/features/worker.py'}
with tarfile.open(archive) as package:
 members=package.getmembers()
 if {m.name for m in members}!=allowed or any(not m.isfile() for m in members):raise SystemExit('Unexpected package contents')
 for member in members:
  content=package.extractfile(member).read();ast.parse(content);target=base/member.name;target.write_bytes(content);target.chmod(0o644)
text=nginx.read_text()
old='location = /gensticker/api/images/subject {\n        limit_req zone=gensticker_generate burst=3 nodelay;\n        client_max_body_size 6m;'
new=old.replace('6m;','12m;')
if old in text:text=text.replace(old,new)
elif new not in text:raise SystemExit('Subject proxy block differs; review before changing')
if 'location = /gensticker/api/studio/live/assets {' not in text:
 marker='    location = /gensticker/api/recommend/assets {'
 if marker not in text:raise SystemExit('Upload proxy insertion point missing')
 text=text.replace(marker,'''    location = /gensticker/api/studio/live/assets {
        limit_req zone=gensticker_generate burst=3 nodelay;
        client_max_body_size 31m;
        client_body_timeout 60s;
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
curl --fail --silent --max-time 5 http://127.0.0.1:3001/account/config | /opt/gensticker-venv/bin/python -c 'import json,sys; v=json.load(sys.stdin); assert v["features"]["livegif"] and v["features"]["template_editor"]; print(json.dumps(v))'
systemctl reload nginx
systemctl is-active gensticker gensticker-worker nginx
printf '%s\n' "Backup: $backup" 'Editor/Live API deployed; integration verification follows.'
trap - EXIT
