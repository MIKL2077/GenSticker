#!/usr/bin/env python3
"""Build the private model comparison page from completed experiment reports."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


def contact(path, output):
    with Image.open(path) as source:
        indices = sorted(set([0, getattr(source, 'n_frames', 1) // 2, getattr(source, 'n_frames', 1) - 1]))
        sheet = Image.new('RGB', (192 * len(indices), 214), 'white')
        for j, index in enumerate(indices):
            source.seek(index)
            thumb = source.convert('RGB')
            thumb.thumbnail((192, 192))
            sheet.paste(thumb, (j * 192 + (192 - thumb.width) // 2, 22 + (192 - thumb.height) // 2))
            ImageDraw.Draw(sheet).text((j * 192 + 6, 5), 'frame ' + str(index), fill='black')
        sheet.save(output, quality=90)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--lab', type=Path, required=True)
    args = parser.parse_args()
    lab = args.lab.resolve()
    gallery = lab / 'gallery'
    manifest = json.loads((lab / 'manifest.json').read_text())
    results = json.loads((gallery / 'report.json').read_text())
    baseline = json.loads((gallery / 'baseline-report.json').read_text())
    review = {r['id']: r for r in json.loads((lab / 'selection.json').read_text())}
    (gallery / 'sources').mkdir(exist_ok=True)
    server = {(c['template'], c['sample'], c['method']): c
              for path in lab.glob('server-*/report.json')
              for c in json.loads(path.read_text())['cases']}
    cases = {}
    for case in baseline['cases'] + results['cases']:
        if case.get('status') == 'failed':
            raise ValueError('a failed result needs explicit diagnosis before publication: ' + str(case))
        output = gallery / 'media' / case['output']['file']
        if not output.is_file():
            raise FileNotFoundError(output)
        if not case.get('contact'):
            case['contact'] = output.stem + '.jpg'
            contact(output, gallery / 'contacts' / case['contact'])
        case['server'] = server.get((case['template'], case['sample'], case['method']))
        case['structural_gate'] = 'failed' if case.get('folded_triangles', 0) else 'passed'
        cases.setdefault(case['template'] + ':' + case['sample'], {})[case['method']] = case
    templates = []
    for template in manifest['templates']:
        tid = template['id']
        original = [Image.fromarray(np.load(lab / 'guides' / f['file'])['original']) for f in template['frames']]
        durations = [f['duration'] for f in template['frames']]
        filename = tid + ('-source.gif' if len(original) > 1 else '-source.png')
        path = gallery / 'media' / filename
        if len(original) > 1:
            original[0].save(path, save_all=True, append_images=original[1:], duration=durations, loop=0, disposal=2, optimize=False)
        else:
            original[0].save(path)
        contact(path, gallery / 'contacts' / (tid + '-source.jpg'))
        limits = template.get('limitations', []).copy()
        limits.append('动作参数为逐模板人工编写，并非模型自动理解模板表情。')
        if '眼神' in template['note'] or tid in ['T147', 'T210']:
            limits.append('本轮没有独立视线控制；眨眼、挑眉不能代替瞳孔转向。')
        if tid == 'T164':
            limits.append('喝饮料涉及唇部与吸管接触，本轮只验证照片驱动与已标注遮挡。')
        if tid in ['T203', 'T303']:
            limits.append('D 侧向投影实测出现网格翻转，本轮不可用，保留结果供诊断。')
        templates.append({**template, 'version': review[tid]['version'], 'source': filename,
                          'source_contact': tid + '-source.jpg', 'limitations': limits})
    for sample in manifest['samples']:
        shutil.copyfile(lab / 'portraits' / (sample + '.png'), gallery / 'sources' / (sample + '.png'))
    data = {'templates': templates, 'samples': manifest['samples'], 'cases': cases,
            'models': json.loads((lab / 'models/export-report.json').read_text()),
            'local_peak_rss_mib': results['peak_rss_mib'],
            'source_preparation_ms': baseline['preparation_ms'],
            'server': json.loads((lab / 'server-report.json').read_text()) if (lab / 'server-report.json').exists() else None,
            'methods': [
                {'key': 'baseline', 'label': '原效果', 'description': 'S03 复用你已评价的原文件；其他照片按同一快照配方生成。'},
                {'key': 'geometry', 'label': 'G · 轻微几何', 'description': '移动本人五官纹理。不能补出牙齿、舌头或未拍到的脸侧。'},
                {'key': 'gan-emotionnet', 'label': 'E · GAN EmotionNet', 'description': '约 847 万参数，128px CPU 推理。可能生成眼镜、眼球和嘴部伪影。'},
                {'key': 'gan-celeba', 'label': 'C · GAN CelebA', 'description': '同一结构的第二组公开权重，用于对照；并非新的网络架构。'},
                {'key': 'geometry-3d', 'label': 'D · 3DDFA 辅助', 'description': '85 万参数估计深度，辅助有限侧向投影；仅对两张侧脸模板测试。'}]}
    # Keep explicitly staged follow-up repairs when rebuilding the original
    # comparison. They remain separate candidates and never rewrite reviews.
    extra_file = gallery / 'extra-results.json'
    if extra_file.is_file():
        extra = json.loads(extra_file.read_text())
        known = {method['key'] for method in data['methods']}
        for method in extra.get('methods', []):
            if method['key'] in known:
                raise ValueError('supplement cannot replace an evaluated method')
            data['methods'].append(method)
            known.add(method['key'])
        for key, variants in extra.get('cases', {}).items():
            if key not in data['cases'] or set(variants) & set(data['cases'][key]):
                raise ValueError('supplement cannot replace an evaluated case')
            for method, case in variants.items():
                if method not in known or Path(case['output']['file']).name != case['output']['file']:
                    raise ValueError('invalid supplemental output')
                if not (gallery / 'media' / case['output']['file']).is_file():
                    raise FileNotFoundError(case['output']['file'])
            data['cases'][key].update(variants)
        for template in data['templates']:
            template['limitations'].extend(extra.get('limitations', {}).get(template['id'], []))
        if extra.get('rollout'):
            data['rollout'] = extra['rollout']
    (gallery / 'data.json').write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')))
    shutil.copyfile(Path(__file__).with_name('smallmodel_review.html'), gallery / 'index.html')
    print(json.dumps({'templates': len(templates), 'samples': len(manifest['samples']), 'outputs': sum(len(v) for v in cases.values()),
                      'server_cases': len(server), 'directory': str(gallery)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
