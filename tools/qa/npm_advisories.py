"""Query npm's official bulk-advisory endpoint without slow meta-vulnerability expansion."""
import argparse, json, urllib.request
from pathlib import Path
p = argparse.ArgumentParser()
p.add_argument('--lock', default='frontend/package-lock.json')
p.add_argument('--output', required=True)
p.add_argument('--production', action='store_true')
a = p.parse_args()
packages = json.loads(Path(a.lock).read_text())['packages']
versions = {}
for location, item in packages.items():
    if not location or (a.production and item.get('dev')):
        continue
    name = location.rsplit('node_modules/', 1)[-1]
    version = item.get('version')
    if version:
        versions.setdefault(name, set()).add(version)
payload = json.dumps({k: sorted(v) for k, v in versions.items()}).encode()
request = urllib.request.Request('https://registry.npmjs.org/-/npm/v1/security/advisories/bulk', data=payload, headers={'Content-Type': 'application/json', 'User-Agent': 'GenSticker-delivery-audit/1.0'})
with urllib.request.urlopen(request, timeout=40) as response:
    data = json.load(response)
report = {'source': 'npm official bulk advisory API', 'scope': 'lockfile non-dev dependency graph; not reachability in generated WeChat bundle' if a.production else 'entire lockfile dependency graph', 'queried_packages': len(versions), 'affected_packages': len(data), 'advisory_matches': sum((len(x) for x in data.values())), 'advisories': data}
Path(a.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
print({k: v for k, v in report.items() if k != 'advisories'})
