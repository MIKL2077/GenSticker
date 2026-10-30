"""Build bound per-method audit views without copying any private portraits."""
import argparse
import copy
import json
import os
from pathlib import Path
import subprocess
import sys

REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO/'backend/meme-generator'))
from meme_generator.features.storage import asset_refs


def prepare(directory,output):
    output.mkdir(exist_ok=True);(output/'drafts').mkdir(exist_ok=True)
    for name,target in [('state',directory/'state'),('media',directory/'media')]:
        link=output/name
        if not link.exists():link.symlink_to(target.resolve(),target_is_directory=True)
        if link.resolve()!=target.resolve():raise ValueError('audit state differs from authoring state')
    expected=set()
    for path in (directory/'drafts').glob('*.json'):
        row=json.loads(path.read_text())
        if row['status']!='draft':continue
        for method,variant in row['variants'].items():
            value=copy.deepcopy(row);value.update(key=row['key']+'-'+method,
                spec=variant['spec'],spec_sha256=variant['spec_sha256'],asset_hashes=sorted(asset_refs(variant['spec'])),
                outputs=[o for o in row['outputs'] if o['method']==method])
            name=value['key']+'.json';expected.add(name)
            (output/'drafts'/name).write_text(json.dumps(value,ensure_ascii=False))
    # Historical reports remain; stale view rows are not audited as current.
    for path in (output/'drafts').glob('*.json'):
        if path.name not in expected:path.unlink()
    return len(expected)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--directory',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    prepare(a.directory.resolve(),a.output.resolve())
    subprocess.run([sys.executable,str(REPO/'tools/qa/audit_expansion_drafts.py'),'--directory',str(a.output.resolve())],check=True)
