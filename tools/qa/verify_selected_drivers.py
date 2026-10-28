#!/usr/bin/env python3
"""Verify the actual publication/DSL path against the exact selected experiment.

Run only in an isolated GENSTICKER_STATE_DIR. Portraits and generated evidence
stay in the private --output directory, outside the source repository.
"""
import argparse
import hashlib
import importlib.util
import io
import json
import resource
import sys
import time
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

from meme_generator.features import expression_driver as driver, expression_library, expression_runtime as rt
from meme_generator.features.declarative import render
from meme_generator.features.store import connect


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    out = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(out)
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--lab', type=Path, required=True)
    parser.add_argument('--compiled', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'media').mkdir(exist_ok=True)
    helper = module('expression_test_helpers', Path(__file__).with_name('test_expression_library.py'))
    reference = module('selected_experiment', args.lab / 'evaluate.py')
    snapshot = json.loads((args.lab / 'snapshot.json').read_text())
    rows = {r['key']: r for r in snapshot['image_templates']}
    updates = {r['key']: r for r in json.loads((args.compiled / 'compiled.json').read_text())}
    templates = {t['key']: t for t in json.loads((args.lab / 'manifest.json').read_text())['templates']}
    helper.initialize(list(rows.values()))
    db = connect()
    fields = 'key,version,fingerprint,metadata,spec,status'
    before = {r['key']: dict(r) for r in db.execute('SELECT ' + fields + ' FROM templates')}
    db.close()
    loader = args.output / 'loader'
    loader.mkdir(exist_ok=True)
    link = loader / 'expression_batches'
    if not link.exists():
        link.symlink_to(args.compiled.resolve(), target_is_directory=True)
    # The loader directory contains only the same release JSON filenames.
    # Non-batch evidence JSON is excluded by copying the approved batch list.
    if link.is_symlink():
        link.unlink()
        link.mkdir()
    for path in args.compiled.glob('*selected-drivers-*.json'):
        (link / path.name).write_bytes(path.read_bytes())
    with patch.object(expression_library, '__file__', str(loader / 'expression_library.py')):
        restored = expression_library.restore()
        if restored != len(updates) or expression_library.restore() != 0:
            raise ValueError('release restore is incomplete or not idempotent')
    db = connect()
    after = {r['key']: dict(r) for r in db.execute('SELECT ' + fields + ' FROM templates')}
    db.close()
    for key in set(rows) - set(updates):
        if before[key] != after[key]:
            raise ValueError('unselected template changed: ' + key)
    reference_session = reference.session('ganimation-emotionnet')
    expected_states = {}
    real_frame = driver.render_frame
    report = {'updated_templates': len(updates), 'unselected_templates_unchanged': len(rows) - len(updates),
              'source_preparation_ms': {}, 'cases': [], 'max_selected_frame_pixel_error': 0}
    for sample in ['S03', 'S17', 'S29']:
        image = Image.open(args.lab / 'inputs' / (sample + '.png')).convert('RGBA')
        start = time.perf_counter()
        source = rt.prepare(image)
        if source is None:
            raise ValueError('test portrait preparation failed: ' + sample)
        report['source_preparation_ms'][sample] = round((time.perf_counter() - start) * 1000, 1)
        prepared = dict(np.load(args.lab / 'portraits' / (sample + '.npz')))
        cache = {('expression', 0): source}
        for key, item in updates.items():
            template = templates[key]
            tid = template['id']
            case = {'template': tid, 'key': key, 'sample': sample, 'status': 'running', 'metrics': [], 'frame_errors': []}
            frame_index = 0
            def observe(source, guide, control, cache, slot):
                nonlocal frame_index
                result = real_frame(source, guide, control, cache, slot)
                if result is None:
                    raise ValueError('selected driver fell back')
                pixels, metrics = result
                original = dict(np.load(args.lab / 'guides' / template['frames'][frame_index]['file']))
                if control.method == 'geometry-v1':
                    q = reference.geometric(prepared['p'], original['aus'])
                    rgb, folds = reference.deform(prepared['rgb'], prepared['p'], q)
                    if folds:
                        raise ValueError('reference mesh folded')
                else:
                    state = (sample, original['aus'].tobytes())
                    if state not in expected_states:
                        tensor = (prepared['rgb'].astype('float32') / 127.5 - 1).transpose(2, 0, 1)[None].copy()
                        generated = reference_session.run(None, {'image': tensor, 'aus': original['aus'][None]})[0]
                        expected_states[state] = np.clip((generated[0].transpose(1, 2, 0) + 1) * 127.5, 0, 255).astype('uint8')
                    rgb = expected_states[state]
                expected, _ = reference.paste(rgb, prepared, original)
                error = int(np.max(np.abs(np.array(pixels).astype('int16') - expected.astype('int16'))))
                case['frame_errors'].append(error)
                case['metrics'].append(metrics)
                frame_index += 1
                return result
            start = time.perf_counter()
            with patch.object(driver, 'render_frame', side_effect=observe):
                raw = render(item['spec'], [image], item['metadata'].get('default_texts', []), _fusion_inputs=cache).getvalue()
            case['verification_render_ms'] = round((time.perf_counter() - start) * 1000, 1)
            case['output'] = helper.inspect(raw, args.output / 'media' / f'{tid}-{sample}-selected')
            spec_frames = item['spec'].get('frames') or [item['spec']]
            durations = [f.get('duration_ms', 0) for f in spec_frames] if len(spec_frames) > 1 else [0]
            if (case['output']['size'] != [item['spec']['width'], item['spec']['height']]
                    or case['output']['durations'] != durations or frame_index != len(spec_frames)):
                raise ValueError('production output changed timeline or dimensions')
            if max(case['frame_errors']) != 0:
                raise ValueError('production driver differs from selected output: ' + str((tid, sample, max(case['frame_errors']))))
            case['status'] = 'passed'
            report['cases'].append(case)
            (args.output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
            print(tid, sample, 'EXACT', len(case['frame_errors']), flush=True)
        # Caption removal/replacement uses the existing independently authored
        # clean caption assets, even when face support has changed.
        for key, item in updates.items():
            text_count = item['metadata'].get('max_texts', 0)
            if text_count:
                render(item['spec'], [image], ['测试'] * text_count, _fusion_inputs=cache)
    rt.close()
    report['status'] = 'passed'
    report['peak_rss_mib'] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1048576 if sys.platform == 'darwin' else 1024), 1)
    (args.output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print('PASS', len(report['cases']), report['unselected_templates_unchanged'], flush=True)


if __name__ == '__main__':
    main()
