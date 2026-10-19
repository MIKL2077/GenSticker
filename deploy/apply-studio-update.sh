#!/bin/bash
# Run on the explicitly authorised GenSticker host as root.
set -euo pipefail
archive=${1:-/tmp/studio-update.tar.gz}
base=/opt/gensticker/meme-generator
stamp=$(date +%Y%m%d-%H%M%S)
backup=/opt/gensticker/backups/studio-$stamp
install -d -m 700 "$backup"
tar -czf "$backup/source-before.tar.gz" -C "$base" meme_generator
if [ -f /etc/gensticker.env ]; then cp -p /etc/gensticker.env "$backup/environment-before"; fi
printf '%s\n' "Backup: $backup"
restore(){
  status=$?
  if [ "$status" -ne 0 ]; then
    systemctl stop gensticker gensticker-worker || true
    tar -xzf "$backup/source-before.tar.gz" -C "$base"
    if [ -f "$backup/environment-before" ]; then cp -p "$backup/environment-before" /etc/gensticker.env; fi
    systemctl start gensticker gensticker-worker || true
    printf '%s\n' 'Deployment failed; previous source/environment restored. Additive database tables retained.' >&2
  fi
  exit "$status"
}
trap restore EXIT
systemctl stop gensticker gensticker-worker
python3 - "$backup" <<'PY'
import sqlite3,sys
from pathlib import Path
for source,name in [(Path('/var/lib/gensticker/accounts.sqlite3'),'accounts.sqlite3'),(Path('/var/lib/gensticker/features/features.sqlite3'),'features.sqlite3')]:
    if source.exists():
        with sqlite3.connect(source) as src,sqlite3.connect(Path(sys.argv[1])/name) as dest:src.backup(dest)
PY
# Trusted package contains only the seven reviewed source paths, never state/config.
python3 - "$archive" "$base" <<'PY'
import sys,tarfile
from pathlib import Path
allowed={'meme_generator/account.py','meme_generator/app.py','meme_generator/features/recommend.py','meme_generator/features/store.py','meme_generator/features/worker.py','meme_generator/features/studio.py','meme_generator/features/quality.py'}
with tarfile.open(sys.argv[1]) as archive:
    members=archive.getmembers()
    if {m.name for m in members}!=allowed or any(not m.isfile() for m in members):raise SystemExit('Unexpected package entry')
    for m in members:
        target=Path(sys.argv[2])/m.name;target.write_bytes(archive.extractfile(m).read());target.chmod(0o644)
path=Path('/etc/gensticker.env');lines=path.read_text().splitlines() if path.exists() else []
settings={'GENSTICKER_DAILY_LIMIT':'0','GENSTICKER_GLOBAL_LIMIT':'0','WX_APPID':'wx2e3a058ed0117034'}
lines=[line for line in lines if line.partition('=')[0] not in settings]
path.write_text('\n'.join(lines+[f'{k}={v}' for k,v in settings.items()])+'\n');path.chmod(0o600)
PY
PYTHONDONTWRITEBYTECODE=1 /opt/gensticker-venv/bin/python -c 'import ast; from pathlib import Path; [ast.parse((Path("/opt/gensticker/meme-generator")/p).read_text()) for p in ("meme_generator/account.py","meme_generator/app.py","meme_generator/features/recommend.py","meme_generator/features/store.py","meme_generator/features/worker.py","meme_generator/features/studio.py","meme_generator/features/quality.py")]; print("Python syntax OK")'
systemctl start gensticker gensticker-worker
ready=0
for attempt in $(seq 1 30); do
  if curl --fail --silent --max-time 2 http://127.0.0.1:3001/healthz > "$backup/health-after.json"; then ready=1; break; fi
  sleep 1
done
[ "$ready" = 1 ]
systemctl is-active gensticker gensticker-worker
curl --fail --silent --max-time 5 http://127.0.0.1:3001/account/config
printf '\n%s\n' 'Source deployed. External and authenticated integration checks must still be run.'
trap - EXIT
