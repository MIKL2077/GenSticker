#!/usr/bin/env python3
"""Daily private snapshot; encrypt with a public certificate, retain seven files.
The decryption key belongs off-host. Run with the service file in this directory.
"""
from pathlib import Path
from datetime import datetime,timezone
import json,os,shutil,subprocess,tarfile,tempfile
from meme_generator.features.backup import snapshot,verify,digest
os.umask(0o077)
root=Path('/var/backups/gensticker-daily');root.mkdir(mode=0o700,exist_ok=True)
certificate=Path('/etc/gensticker-backup-recipient.pem')
if not certificate.is_file():raise SystemExit('Missing off-host backup public certificate')
if shutil.disk_usage(root).free<10*1024**3:raise SystemExit('Backup postponed: free disk below 10 GiB')
stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
output=root/('gensticker-'+stamp+'.cms');partial=output.with_suffix('.partial')
try:
 with tempfile.TemporaryDirectory(prefix='.snapshot-',dir=root) as name:
  folder=Path(name);snapshot('/var/lib/gensticker',folder/'application')
  result=verify(folder/'application')
  if result['status']!='passed':raise RuntimeError('Snapshot verification failed')
  config=folder/'configuration';config.mkdir(mode=0o700)
  exact=[Path('/etc/nginx/conf.d/nginx-gensticker.conf')]
  credential=Path(os.environ['CREDENTIALS_DIRECTORY'])/'gensticker.env'
  shutil.copyfile(credential,config/'gensticker.env');(config/'gensticker.env').chmod(0o600)
  exact += [Path('/etc/systemd/system')/n for n in ['gensticker.service','gensticker-worker.service','gensticker-ingest.service','gensticker.slice','gensticker-monitor.service','gensticker-monitor.timer','gensticker-backup.service','gensticker-backup.timer']]
  for path in exact:
   if path.is_file() and not path.is_symlink():
    target=config/path.name;shutil.copyfile(path,target);target.chmod(0o600)
  (folder/'release.json').write_text(json.dumps({'release':str(Path('/opt/gensticker-current').resolve()),'created_utc':stamp,'scope':'online SQLite backups and linked files; validate cross-file references on restore; excludes other host services and models'},indent=2)+'\n')
  with partial.open('xb') as encrypted:
   proc=subprocess.Popen(['openssl','cms','-encrypt','-binary','-aes-256-gcm','-outform','DER',str(certificate)],stdin=subprocess.PIPE,stdout=encrypted,stderr=subprocess.PIPE)
   try:
    with tarfile.open(fileobj=proc.stdin,mode='w|gz') as archive:archive.add(folder,arcname='gensticker-backup',recursive=True)
    proc.stdin.close();message=proc.stderr.read();code=proc.wait(timeout=30)
    if code:raise RuntimeError('Encryption failed: '+message.decode(errors='replace')[:120])
   finally:
    if proc.poll() is None:proc.kill();proc.wait()
  os.replace(partial,output)
 old=sorted(root.glob('gensticker-*.cms'),reverse=True)
 for path in old[7:]:
  if path.is_file() and not path.is_symlink():path.unlink()
 print(json.dumps({'status':'passed','archive':output.name,'bytes':output.stat().st_size,'sha256':digest(output),'verified_files':result['files'],'retained':min(7,len(old))}),flush=True)
finally:partial.unlink(missing_ok=True)
