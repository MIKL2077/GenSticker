"""Idempotent restore of reviewed, CC BY-SA 4.0 chat reactions."""
import base64
import hashlib
import json
from pathlib import Path
from .store import root, connect


def restore():
    from .catalog import publish
    manifest=json.loads(Path(__file__).with_suffix('.json').read_text())
    db=connect()
    try:
        versions={r['key']:r['version'] for r in db.execute('SELECT key,version FROM templates')}
        blocked={r[0] for r in db.execute('SELECT key FROM template_blocks')}
    finally:db.close()
    count=0
    for item in manifest['templates']:
        if item['key'] in blocked or versions.get(item['key'],0)>=item['version']:continue
        metadata=item['metadata']
        if not (item['key'].startswith('auto_scene_') and metadata['license']=='CC BY-SA 4.0' and metadata['source_url'].startswith('https://github.com/hfg-gmuend/openmoji/blob/15.1.0/color/618x618/')):raise ValueError('invalid scene source')
        for layer in item['spec']['layers']:
            if layer['type']!='asset':continue
            digest=layer['value'];raw=base64.b64decode(manifest['assets'][digest],validate=True)
            if hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('scene asset mismatch')
            directory=root()/'template_assets';directory.mkdir(exist_ok=True);(directory/(digest+'.png')).write_bytes(raw)
        publish(item['key'],metadata,item['spec'],minimum_version=item['version']);count+=1
    return count
