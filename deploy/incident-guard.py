#!/usr/bin/python3
"""Contain the known SSH scanning suite; this cannot certify a root-compromised OS."""
import hashlib
import os
from pathlib import Path
import signal
import syslog

evidence = Path('/root/incident-20261013')
known_hashes = {line.split()[0] for line in (evidence / 'hashes.txt').read_text().splitlines()}
malicious_dirs = ('/var/www/httpd/ssh_scan', str(evidence / 'ssh_scan-quarantined'))
victims = []
for process in Path('/proc').iterdir():
    if not process.name.isdigit() or int(process.name) == os.getpid():
        continue
    try:
        cwd = os.readlink(process / 'cwd')
        executable = os.readlink(process / 'exe')
        match = any(cwd == d or cwd.startswith(d + '/') for d in malicious_dirs)
        if not match and Path(executable).name.removesuffix(' (deleted)') in {'masscan', 'banner', 'parallel', 'hma', 'hma-quarantined'}:
            match = hashlib.sha256((process / 'exe').read_bytes()).hexdigest() in known_hashes
        if match:
            os.kill(int(process.name), signal.SIGSTOP)
            victims.append(int(process.name))
    except (OSError, PermissionError):
        continue
for pid in victims:
    try:
        os.kill(pid, signal.SIGKILL)
        syslog.syslog(syslog.LOG_WARNING, f'incident-guard stopped known malicious process pid={pid}')
    except ProcessLookupError:
        pass
