"""High-confidence working-tree secret/file hygiene checks, not full-history scanning."""
import argparse, json, re, subprocess
from pathlib import Path
root = Path(__file__).resolve().parents[2]
p = argparse.ArgumentParser()
p.add_argument('--output', default='docs/testing/evidence/latest-repo-checks.json')
a = p.parse_args()
paths = subprocess.check_output(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd=root).decode().split('\x00')
findings = []
scanned = 0
for name in paths:
    if not name:
        continue
    path = root / name
    if not path.is_file():
        continue
    if re.search('(^|/)(\\.env(?:\\.local)?|[^/]+\\.sqlite3(?:-(?:wal|shm))?|[^/]+\\.pem)$', name):
        findings.append({'file': name, 'kind': 'private-state-or-key-file'})
    if path.stat().st_size > 2 * 1024 * 1024:
        continue
    try:
        text = path.read_text()
    except (UnicodeError, OSError):
        continue
    scanned += 1
    for pattern, label in [('-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----', 'private-key'), ('AKIA[0-9A-Z]{16}', 'aws-key-id'), ('WX_APP_SECRET\\s*=\\s*[\\\'\\"][0-9a-fA-F]{32}[\\\'\\"]', 'literal-wechat-secret')]:
        if re.search(pattern, text):
            findings.append({'file': name, 'kind': label})
result = {'scope': 'tracked and nonignored text files in current working tree; filenames only, no secret values; not Git history, binaries, cloud credentials or proof of absence', 'text_files_scanned': scanned, 'findings': findings, 'status': 'passed' if not findings else 'review-required'}
out = root / a.output
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
print(result)
raise SystemExit(0 if not findings else 1)
