#!/usr/bin/env python3
"""Idempotent bounded host logs. No container data or application files deleted.
Existing containers retain their original driver until explicitly recreated.
"""
from pathlib import Path
import json,os,shutil,subprocess,time


def run(*args):return subprocess.run(args,capture_output=True,text=True,check=True).stdout.strip()

def main():
    if os.geteuid()!=0:raise SystemExit('root required')
    source=Path(__file__).with_name('logging');backup=Path('/var/backups')/('gensticker-log-policy-'+str(int(time.time())));backup.mkdir(mode=0o700)
    mappings={source/'gensticker-journal.conf':Path('/etc/systemd/journald.conf.d/90-gensticker-capacity.conf'),source/'gensticker-nginx.logrotate':Path('/etc/logrotate.d/nginx'),source/'gensticker-rsyslog.logrotate':Path('/etc/logrotate.d/rsyslog'),source/'hourly-logrotate.conf':Path('/etc/systemd/system/logrotate.timer.d/90-gensticker-hourly.conf')}
    installed=[]
    try:
        for src,dst in mappings.items():
            if dst.exists():shutil.copy2(dst,backup/(dst.parent.name+'-'+dst.name))
            dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst);dst.chmod(0o644);installed.append(dst)
        run('logrotate','--debug','/etc/logrotate.conf')
        docker=Path('/etc/docker/daemon.json');previous=json.loads(docker.read_text()) if docker.exists() else {}
        if docker.exists():shutil.copy2(docker,backup/'docker-daemon.json')
        configured={**previous,'log-driver':'local','log-opts':{'max-size':'20m','max-file':'3','compress':'true'}}
        docker.parent.mkdir(parents=True,exist_ok=True);docker.write_text(json.dumps(configured,indent=2)+'\n');docker.chmod(0o644)
        run('dockerd','--validate','--config-file',str(docker))
        run('systemctl','daemon-reload');run('systemctl','restart','logrotate.timer');run('systemctl','restart','systemd-journald')
        # Respect other services: never restart Docker with running containers.
        running=run('docker','ps','-q').splitlines()
        if not running:run('systemctl','restart','docker')
        run('journalctl','--rotate');run('journalctl','--vacuum-size=1G','--vacuum-time=14d')
        print(json.dumps({'status':'passed','journal_limit':'1GiB / 14 days','nginx':'daily or >50MiB on hourly checks, 14 compressed rotations','syslog':'same bounded rotation','docker_default':'local, 20MiB x 3, compression','docker_restarted':not bool(running),'existing_containers_recreated':False,'backup':str(backup)}))
    except Exception:
        for src,dst in mappings.items():
            old=backup/(dst.parent.name+'-'+dst.name)
            if old.exists():shutil.copy2(old,dst)
            elif dst in installed:dst.unlink(missing_ok=True)
        old=backup/'docker-daemon.json'
        if old.exists():shutil.copy2(old,Path('/etc/docker/daemon.json'))
        run('systemctl','daemon-reload')
        raise


if __name__=='__main__':main()
