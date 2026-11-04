"""Export hash-bound human approvals, or publish a verified private release.

Publication adds database rows and immutable assets; no runtime source changes
or service restart is needed. Never overwrites an existing template.
"""
import argparse
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import shutil
import sqlite3
import time


def sha(data):
    return hashlib.sha256(data).hexdigest()


def export(directory, destination):
    from meme_generator.features.element_templates import fingerprint
    from meme_generator.features.declarative import TemplateSpec
    from meme_generator.features.storage import asset_refs
    reviews_raw = (directory / 'reviews.json').read_bytes()
    reviews = json.loads(reviews_raw)
    findings = json.loads((directory / 'review-findings.json').read_text())
    rows = json.loads((directory / 'drafts.json').read_text())
    destination.mkdir(parents=True, exist_ok=False)
    assets = destination / 'assets'
    assets.mkdir()
    bundle = {'created_at': time.time(), 'review_sha256': sha(reviews_raw),
              'templates': [], 'excluded': [], 'assets': {}}
    for row in rows:
        if row.get('status') != 'draft-pending-review':
            continue
        review = reviews.get(row['key'], {})
        if review.get('rating') != '通过':
            bundle['excluded'].append({'id': row['id'], 'key': row['key'], 'rating': review.get('rating', '')})
            continue
        if findings.get(row['id'], {}).get('blocked'):
            raise ValueError('blocked draft: ' + row['id'])
        draft = json.loads((directory / 'media' / row['id'] / 'draft.json').read_text())
        spec = draft['spec']
        assert draft['key'] == row['key']
        assert fingerprint(spec) == review['spec_sha256'] == row['spec_sha256']
        TemplateSpec.model_validate(spec)
        metadata = draft['metadata']
        assert metadata['quality']['spec_sha256'] == review['spec_sha256']
        assert metadata['quality']['fixed_pixel_error_before_gif_quantization'] == 0
        assert metadata['quality']['default_pixel_error_before_gif_quantization'] == 0
        for variant in ['default', 'changed', 'blank', 'multiline']:
            check = row['checks'][variant]
            data = (directory / 'media' / row['id'] / (variant + row['suffix'])).read_bytes()
            assert check['status'] == 'rendered-for-visual-review' and sha(data) == check['sha256']
        assert row['checks']['overflow']['status'] == 'rejected-visibly'
        metadata['source_use'] = 'explicit-user-request-with-attribution'
        metadata['review'] = {**metadata.get('review', {}), 'visual_status': 'approved',
                              'user_approval': True, 'spec_sha256': review['spec_sha256'],
                              'updated_at': review['updated_at'], 'review_sha256': bundle['review_sha256'],
                              'checks': ['source', 'changed', 'blank', 'multiline', 'complete-timeline']}
        metadata['created_at'] = review['updated_at']
        metadata['original_hash'] = draft['source_sha256']
        for digest in asset_refs(spec):
            matches = list((directory / 'state/features/template_assets').glob(digest + '.*'))
            assert len(matches) == 1
            data = matches[0].read_bytes()
            assert sha(data) == digest
            name = matches[0].name
            (assets / name).write_bytes(data)
            bundle['assets'][digest] = name
        bundle['templates'].append({'id': row['id'], 'key': row['key'], 'spec': spec, 'metadata': metadata})
    assert 0 < len(bundle['templates']) <= 100
    assert len({t['key'] for t in bundle['templates']}) == len(bundle['templates'])
    (destination / 'reviews.json').write_bytes(reviews_raw)
    (destination / 'bundle.json').write_text(json.dumps(bundle, ensure_ascii=False, indent=2))
    shutil.copy2(__file__, destination / 'release_themed_review.py')
    return {'approved': len(bundle['templates']), 'excluded': len(bundle['excluded']),
            'assets': len(bundle['assets']), 'bundle_sha256': sha((destination / 'bundle.json').read_bytes())}


def apply(release, expected_sha):
    from PIL import Image
    from meme_generator.features.declarative import render, TemplateSpec
    from meme_generator.features.element_templates import fingerprint
    from meme_generator.features.storage import asset_refs, exclusive
    from meme_generator.features.store import root, connect
    from meme_generator.features.catalog import publish
    raw = (release / 'bundle.json').read_bytes()
    assert sha(raw) == expected_sha
    bundle = json.loads(raw)
    assert sha((release / 'reviews.json').read_bytes()) == bundle['review_sha256']
    reviews = json.loads((release / 'reviews.json').read_text())
    keys = [item['key'] for item in bundle['templates']]
    assert 0 < len(keys) <= 100 and len(set(keys)) == len(keys)
    assert not set(keys) & {item['key'] for item in bundle['excluded']}
    asset_data = {}
    for digest, name in bundle['assets'].items():
        assert name in {digest + '.png', digest + '.gif'}
        data = (release / 'assets' / name).read_bytes()
        assert sha(data) == digest
        with Image.open(BytesIO(data)) as image:
            assert image.format in {'PNG', 'GIF'}
            image.verify()
        asset_data[name] = data
    for item in bundle['templates']:
        m = item['metadata']
        assert reviews[item['key']]['rating'] == '通过'
        assert fingerprint(item['spec']) == reviews[item['key']]['spec_sha256'] == m['review']['spec_sha256']
        assert m['review']['visual_status'] == 'approved' and m['review']['user_approval'] is True
        assert asset_refs(item['spec']) <= set(bundle['assets'])
        TemplateSpec.model_validate(item['spec'])
    with exclusive():
        db = connect()
        try:
            assert not any(db.execute('SELECT 1 FROM templates WHERE key=?', (key,)).fetchone() for key in keys), 'existing key; inspect receipt before retry'
            receipt_dir = root() / 'reviewed_releases' / expected_sha[:16]
            receipt_dir.mkdir(parents=True, exist_ok=False)
            with sqlite3.connect(receipt_dir / 'before.sqlite3') as backup:
                db.backup(backup)
            (receipt_dir / 'bundle.json').write_bytes(raw)
            (receipt_dir / 'reviews.json').write_bytes((release / 'reviews.json').read_bytes())
            folder = root() / 'template_assets'
            folder.mkdir(exist_ok=True)
            for name, data in asset_data.items():
                target = folder / name
                if target.exists():
                    assert target.read_bytes() == data
                else:
                    temporary = target.with_suffix(target.suffix + '.release-tmp')
                    temporary.write_bytes(data)
                    temporary.replace(target)
            # Complete every real replacement render before adding public rows.
            for item in bundle['templates']:
                for texts in [item['metadata']['default_texts'], ['测试'] * item['metadata']['min_texts'], [''] * item['metadata']['min_texts']]:
                    render(item['spec'], [], texts)
            introduced = []
            try:
                for item in bundle['templates']:
                    row = publish(item['key'], item['metadata'], item['spec'])
                    introduced.append({'key': item['key'], 'version': row['version'], 'fingerprint': row['fingerprint']})
                assert all(db.execute("SELECT 1 FROM templates WHERE key=? AND status='published'", (key,)).fetchone() for key in keys)
            except BaseException:
                # Retain history, withdraw only this release's new keys.
                with db:
                    for key in keys:
                        db.execute("UPDATE templates SET status='withdrawn' WHERE key=?", (key,))
                raise
            receipt = {'status': 'published', 'time': time.time(), 'bundle_sha256': expected_sha,
                       'introduced': introduced, 'excluded': bundle['excluded'], 'backup': str(receipt_dir / 'before.sqlite3')}
            (receipt_dir / 'receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2))
            return receipt
        finally:
            db.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('export'); p.add_argument('directory', type=Path); p.add_argument('destination', type=Path)
    p = sub.add_parser('apply'); p.add_argument('release', type=Path); p.add_argument('--sha256', required=True); p.add_argument('--state', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'export':
        result = export(args.directory.resolve(), args.destination.resolve())
    else:
        os.environ['GENSTICKER_STATE_DIR'] = str(args.state.resolve())
        result = apply(args.release.resolve(), args.sha256)
    print(json.dumps(result, ensure_ascii=False, indent=2))
