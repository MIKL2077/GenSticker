"""Compile measured themed plans into private, reviewable drafts; never publish.

Usage: PYTHONPATH=backend/meme-generator .venv/bin/python
       tools/collect/prepare_themed_expansion.py MANIFEST --output DIRECTORY
"""
import argparse
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path

import numpy as np
from PIL import Image


def normalize(path, size):
    frames, durations = [], []
    with Image.open(path) as source:
        count = getattr(source, 'n_frames', 1)
        if count > 40 or size[0] * size[1] * count > 8_000_000:
            raise ValueError('source exceeds complete-frame authoring budget')
        for index in range(count):
            source.seek(index)
            frame = Image.alpha_composite(Image.new('RGBA', source.size, 'white'), source.convert('RGBA'))
            frames.append(frame.resize(size, Image.Resampling.LANCZOS).convert('RGB'))
            durations.append(max(20, int(source.info.get('duration', 100))))
    output = BytesIO()
    if len(frames) > 1:
        frames[0].save(output, 'GIF', save_all=True, append_images=frames[1:],
                       duration=durations, loop=0, disposal=2, optimize=False)
    else:
        frames[0].save(output, 'PNG')
    return output.getvalue(), durations


def prepare(manifest, output):
    os.environ['GENSTICKER_STATE_DIR'] = str(output / 'state')
    from meme_generator.features.declarative import TemplateSpec, render
    from meme_generator.features.element_templates import compile_elements, fingerprint
    from meme_generator.features.search_terms import keywords
    from meme_generator.features.store import root

    assets_dir = root() / 'template_assets'
    assets_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for row in manifest:
        if not row.get('plan'):
            results.append({'id': row['id'], 'status': 'reference-only', 'reason': row.get('reason', '')})
            continue
        plan = json.loads(Path(row['plan']).read_text())
        folder = output / 'media' / row['id']
        folder.mkdir(parents=True, exist_ok=True)
        try:
            original = Path(row['path']).read_bytes()
            if hashlib.sha256(original).hexdigest() != row['sha256']:
                raise ValueError('source changed since measurement')
            raw, timing = normalize(row['path'], tuple(plan['normalization']['size']))
            spec, assets, geometry = compile_elements(raw, plan['frames'], plan['defaults'],
                                                     caption_margin=6, caption_tolerance=60)
            if clean := plan.get('clean_source'):
                clean_raw = Path(clean['path']).read_bytes()
                if hashlib.sha256(clean_raw).hexdigest() != clean['sha256']:
                    raise ValueError('prepared clean source changed')
                with Image.open(BytesIO(clean_raw)) as plate:
                    for index, frame in enumerate(spec['frames']):
                        plate.seek(clean['frame_map'][index])
                        background = plate.convert('RGBA').resize(tuple(plan['normalization']['size']), Image.Resampling.LANCZOS)
                        for layer in frame['layers']:
                            if layer['type'] != 'asset':
                                continue
                            x, y, w, h = layer['box']
                            patch = BytesIO()
                            background.crop((x, y, x+w, y+h)).save(patch, 'PNG')
                            data = patch.getvalue()
                            digest = hashlib.sha256(data).hexdigest()
                            assets[digest] = data
                            layer['value'] = digest
            for digest, data in assets.items():
                (assets_dir / (digest + ('.gif' if data.startswith(b'GIF') else '.png'))).write_bytes(data)
            value = TemplateSpec.model_validate(spec)
            suffix = '.gif' if len(value.frames) > 1 else '.png'
            (folder / ('source' + suffix)).write_bytes(raw)
            checks = {}
            variants = {'default': plan['defaults'], 'changed': plan['sample_texts'],
                        'blank': [''] * len(plan['defaults']),
                        'multiline': ['第一行\n第二行' for _ in plan['defaults']]}
            fixed_error = 0
            default_error = 0
            decoded = Image.open(BytesIO(raw))
            for index, frame in enumerate(value.frames):
                decoded.seek(index)
                base = decoded.convert('RGBA')
                if not frame.layers:
                    # Captions can disappear before the source loop ends.
                    # Keep these frames intact, including their duration.
                    continue
                fixed = np.ones((value.height, value.width), dtype=bool)
                for layer in frame.layers:
                    x, y, w, h = layer.box
                    fixed[y:y+h, x:x+w] = False
                static = TemplateSpec(width=value.width, height=value.height, defaults=value.defaults,
                                      background_prepared=True, layers=frame.layers)
                for name in ['default', 'changed', 'blank']:
                    rendered = render(static, [], variants[name], _transparent=True,
                                      _base=base, _reference=base, _return_image=True).convert('RGB')
                    difference = np.abs(np.asarray(rendered).astype(int) - np.asarray(base.convert('RGB')).astype(int))
                    fixed_error = max(fixed_error, int(difference[fixed].max(initial=0)))
                    if name == 'default':
                        default_error = max(default_error, int(difference.max(initial=0)))
            decoded.close()
            if fixed_error or default_error:
                raise ValueError(f'fixed/default pixels changed: {fixed_error}/{default_error}')
            for name, texts in variants.items():
                try:
                    data = render(value, [], texts).getvalue()
                    (folder / (name + suffix)).write_bytes(data)
                    with Image.open(BytesIO(data)) as image:
                        encoded_timing = []
                        for i in range(getattr(image, 'n_frames', 1)):
                            image.seek(i)
                            encoded_timing.append(int(image.info.get('duration', 100)))
                        if len(timing) > 1 and sum(encoded_timing) != sum(timing):
                            raise ValueError('encoded loop duration changed')
                    checks[name] = {'status': 'rendered-for-visual-review', 'sha256': hashlib.sha256(data).hexdigest(),
                                    'bytes': len(data), 'frames': len(encoded_timing), 'duration_ms': sum(encoded_timing)}
                except ValueError as error:
                    checks[name] = {'status': 'needs-adjustment', 'reason': str(error)}
            try:
                render(value, [], ['长文测试' * 1000] * len(plan['defaults']))
            except ValueError:
                checks['overflow'] = {'status': 'rejected-visibly'}
            else:
                raise ValueError('overlong caption was silently accepted')
            metadata = plan['metadata']
            metadata['keywords'] = keywords(metadata)
            metadata['quality'] = {'spec_sha256': fingerprint(spec), 'analyzed_frames': len(value.frames),
                                   'fixed_pixel_error_before_gif_quantization': fixed_error,
                                   'default_pixel_error_before_gif_quantization': default_error,
                                   'caption_inventory': metadata['caption_inventory'], 'checks': checks}
            draft = {'key': plan['key'], 'spec': spec, 'metadata': metadata, 'geometry': geometry,
                     'source_sha256': row['sha256'], 'normalization': plan['normalization'],
                     'clean_source': plan.get('clean_source')}
            (folder / 'draft.json').write_text(json.dumps(draft, ensure_ascii=False, indent=2))
            result = {'id': row['id'], 'key': plan['key'], 'name': metadata['name'], 'group': row['group'],
                      'status': 'draft-pending-review', 'spec_sha256': fingerprint(spec), 'suffix': suffix,
                      'keywords': metadata['keywords'], 'source_url': row['source_url'],
                      'license': 'unverified', 'checks': checks, 'fixed_pixel_error': fixed_error,
                      'default_pixel_error': default_error, 'frames': len(value.frames), 'duration_ms': sum(timing)}
        except Exception as error:
            result = {'id': row['id'], 'status': 'needs-adjustment', 'reason': str(error)}
        results.append(result)
        print(json.dumps({k: result[k] for k in ['id', 'status', 'reason'] if k in result}, ensure_ascii=False), flush=True)
    (output / 'drafts.json').write_text(json.dumps(results, ensure_ascii=False, indent=2))
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    prepare(json.loads(args.manifest.read_text()), args.output.resolve())
