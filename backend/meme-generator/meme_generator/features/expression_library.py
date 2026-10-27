"""Replay the explicitly requested experimental A/B library delta, idempotently.

This is separate from visually approved source ingestion. It never approves a
new source or erases the original review; policies remain pending user review.
"""
import base64
import hashlib
import json
import os
import tempfile
from pathlib import Path
from .store import connect, root
from .storage import asset_refs


def restore():
    from .catalog import publish
    from .declarative import ExpressionRecipe, TemplateSpec
    updated = 0
    for path in sorted(Path(__file__).with_name('expression_batches').glob('*.json')):
        batch = json.loads(path.read_text())
        if batch.get('format')!='gensticker-expression-ab-v1':
            raise ValueError('unknown expression library format')
        for item in batch['templates']:
            db=connect()
            try:
                row=db.execute('SELECT * FROM templates WHERE key=?',(item['key'],)).fetchone()
                blocked=db.execute('SELECT 1 FROM template_blocks WHERE key=?',(item['key'],)).fetchone()
            finally:db.close()
            if not row or blocked or row['status']!='published' or row['version']>=item['version']:
                continue
            if row['version']!=item['base_version'] or row['fingerprint']!=item['base_fingerprint']:
                # Never overwrite a newer operator edit or a different source.
                continue
            policy=item['metadata']['expression_policy']
            if policy['mode'] not in {'A','B'} or policy['visual_status']!='pending-user-review':
                raise ValueError('invalid experimental policy')
            if policy.get('recipe'):ExpressionRecipe.model_validate(policy['recipe'])
            if item['spec']:TemplateSpec.model_validate(item['spec'])
            refs=asset_refs(item['spec']) | asset_refs(item['metadata'])
            directory=root()/'template_assets';directory.mkdir(exist_ok=True)
            for digest in refs:
                if digest in batch['assets']:
                    raw=base64.b64decode(batch['assets'][digest],validate=True)
                    if hashlib.sha256(raw).hexdigest()!=digest or not raw.startswith(b'\x89PNG\r\n\x1a\n'):
                        raise ValueError('expression artwork checksum mismatch')
                    target=directory/(digest+'.png')
                    if not target.exists():
                        with tempfile.NamedTemporaryFile(dir=directory,prefix=digest+'-',suffix='.tmp',delete=False) as temporary:
                            temporary.write(raw);name=Path(temporary.name)
                        try:name.chmod(0o644);os.replace(name,target)
                        finally:name.unlink(missing_ok=True)
                    elif target.stat().st_mode & 0o444 != 0o444:
                        # Artwork is public; a root-run upgrade must remain
                        # readable by the API/worker service account.
                        target.chmod(0o644)
                elif not any((directory/(digest+ext)).is_file() for ext in ['.png','.gif']):
                    raise ValueError('expression artwork missing')
            publish(item['key'],item['metadata'],item['spec'],minimum_version=item['version'])
            updated+=1
    return updated
