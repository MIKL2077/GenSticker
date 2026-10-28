#!/usr/bin/env python3
"""Compile versioned human choices into a source-only, reviewable library delta.

No portraits, ONNX weights, generated portraits or private case files enter the
batch. Baseline and rejected choices leave the published recipe untouched.
"""
import argparse
import base64
import copy
import hashlib
import io
import json
from pathlib import Path

import numpy as np
from PIL import Image

from meme_generator.features.declarative import TemplateSpec
from meme_generator.features.storage import asset_refs
from meme_generator.features.store import root


def asset(image):
    buffer = io.BytesIO()
    image.save(buffer, 'PNG')
    raw = buffer.getvalue()
    digest = hashlib.sha256(raw).hexdigest()
    path = root() / 'template_assets' / (digest + '.png')
    if not path.exists():
        path.write_bytes(raw)
    return digest


def build(row, template, choice, lab, approval, actions=None):
    item = copy.deepcopy(row)
    spec = item['spec']
    frames = spec.get('frames') or [spec]
    for index, frame in enumerate(frames):
        guide = dict(np.load(lab / 'guides' / template['frames'][index]['file']))
        face = next(layer for layer in frame['layers'] if layer['type'] == 'face')
        if len([layer for layer in frame['layers'] if layer['type'] == 'face']) != 1:
            raise ValueError('unreviewed multiple-face adapter')
        old_box = face['box']
        # The original DSL carries a clean-patch asset before its face slot.
        # Replace that plate as well as the expression/fallback masks.
        frame['layers'] = [layer for layer in frame['layers']
                           if not (layer['type'] == 'asset' and layer['box'] == old_box)]
        original, clean = Image.fromarray(guide['original']), Image.fromarray(guide['base'])
        mask = Image.fromarray(guide['mask'])
        ys, xs = np.where(guide['mask'] > 0)
        if not len(xs):
            raise ValueError('empty reviewed support')
        box = [int(xs.min()), int(ys.min()), int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)]
        x, y, width, height = box
        original_asset, clean_asset = asset(original), asset(clean)
        frame.update(asset=clean_asset, asset_format='png', source_index=0, reference_asset=original_asset)
        old_expression = face.get('expression') or {}
        face.update(box=box, fit='cover', tone='original', rotation=0, feather=1,
                    erase_polygon=[], protect_polygons=[], fusion=None,
                    mask_asset=asset(mask.crop((x, y, x + width, y + height))))
        values = actions[index] if actions is not None else guide['aus'].tolist()
        face['expression'] = {
            'method': 'cpu-expression-ab-v1', 'mode': item['metadata']['expression_policy']['mode'],
            'domain': old_expression.get('domain', 'human'), 'points': guide['p'].tolist(),
            'reference_asset': original_asset, 'base_asset': clean_asset, 'mask_asset': asset(mask),
            'driver': {'method': 'geometry-v1' if choice == 'geometry' else 'ganimation-emotionnet-v1',
                       'aus': values}}
    item['spec'] = TemplateSpec.model_validate(spec).model_dump()
    policy = item['metadata']['expression_policy']
    policy.pop('recipe', None)
    policy.update(visual_status='user-approved' if approval else 'pending-user-review',
                  supported_regions=len(frames), regions=len(frames), disposition='expression',
                  driver='geometry-v1' if choice == 'geometry' else 'ganimation-emotionnet-v1')
    if approval:
        policy['review'] = approval
    else:
        policy.pop('review', None)
    item.update(base_version=row['version'], base_fingerprint=row['fingerprint'], version=row['version'] + 1)
    item.pop('id', None)
    item.pop('fingerprint', None)
    return item


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--lab', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--choices', type=Path, required=True)
    args = parser.parse_args()
    lab = args.lab.resolve()
    snapshot = json.loads((lab / 'snapshot.json').read_text())
    rows = {r['key']: r for r in snapshot['image_templates']}
    manifest = json.loads((lab / 'manifest.json').read_text())
    decisions = json.loads(args.choices.read_text())['records']
    digest = hashlib.sha256(args.choices.read_bytes()).hexdigest()
    chosen = {key: [r for r in decisions.values() if r['key'] == key] for key in rows}
    updates, ledger = [], []
    args.output.mkdir(parents=True, exist_ok=True)
    for template in manifest['templates']:
        row = rows[template['key']]
        reviews = chosen[row['key']]
        review = next((r for r in reviews if r['sample'] == 'S03'), None)
        if (not review or review.get('origin') != 'user' or review['version'] != row['version']
                or any(r['choice'] != review['choice'] for r in reviews)):
            raise ValueError('missing, stale or conflicting review: ' + template['id'])
        choice = review['choice']
        if choice not in {'baseline', 'reject', 'geometry', 'gan-emotionnet'}:
            raise ValueError('unapproved driver: ' + choice)
        record = {'id': template['id'], 'key': row['key'], 'name': template['name'],
                  'base_version': row['version'], 'choice': choice, 'note': review['note']}
        if choice in {'geometry', 'gan-emotionnet'}:
            approval = {'source': 'local-smallmodel-review', 'template_key': row['key'],
                        'source_version': row['version'], 'choice': choice, 'annotation_sha256': digest}
            item = build(row, template, choice, lab, approval)
            updates.append(item)
            record.update(action='apply-selected-driver', version=item['version'])
        else:
            record.update(action='retain-reviewed-baseline' if choice == 'baseline' else 'rejected-no-rollout',
                          version=row['version'])
        ledger.append(record)
    old_refs = set().union(*(asset_refs(row['spec']) | asset_refs(row['metadata']) for row in rows.values()))
    # Bound both template count and the actual serialized asset payload.
    batches, current = [], []
    def batch(items):
        refs = set().union(*(asset_refs(item['spec']) | asset_refs(item['metadata']) for item in items)) - old_refs
        assets = {digest: base64.b64encode((root() / 'template_assets' / (digest + '.png')).read_bytes()).decode()
                  for digest in sorted(refs)}
        return json.dumps({'format': 'gensticker-expression-ab-v1', 'templates': items, 'assets': assets},
                          ensure_ascii=False, separators=(',', ':')).encode()
    for item in updates:
        candidate = current + [item]
        if len(candidate) > 100 or len(batch(candidate)) > 32 * 1024 ** 2:
            if not current:
                raise ValueError('single template exceeds batch budget')
            batches.append(current)
            current = [item]
        else:
            current = candidate
    if current:
        batches.append(current)
    for index, items in enumerate(batches):
        raw = batch(items)
        if len(raw) > 32 * 1024 ** 2:
            raise ValueError('batch exceeds byte budget')
        (args.output / f'20261029-selected-drivers-{index + 1:02}.json').write_bytes(raw)
    (args.output / 'compiled.json').write_text(json.dumps(updates, ensure_ascii=False))
    (args.output / 'ledger.json').write_text(json.dumps(ledger, ensure_ascii=False, indent=2))
    print(json.dumps({'updated': len(updates), 'unchanged': len(ledger) - len(updates), 'batches': len(batches)}))


if __name__ == '__main__':
    main()
