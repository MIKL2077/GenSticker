"""Curate technically checked drafts for human review; never approve or publish.

Conservative OCR/anchor checks remove obvious failures. A three-keyframe
perceptual signature also keeps re-encoded copies out of the review count.
These checks do not establish visual quality, popularity or reuse rights.
"""
import argparse
from collections import Counter, defaultdict, deque
import hashlib
import json
from pathlib import Path
import re
import sys

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'backend/meme-generator'))
from meme_generator.features.search_terms import keywords

BRANDING = re.compile(r'腾讯视频|爱奇艺|闪萌|抖音|快手|微博|公众号|水印|@|bilibili|IQIYI|QIYI|SBS|YOUKU', re.I)


def preflight(row):
    reasons = []
    text = ' '.join(row['defaults'])
    if row['text_slots'] and not re.search('[\u4e00-\u9fff]', text) and not re.fullmatch(
            r'(?i)[ !?.,\n]*(?:ok|yes|no|what|hello)[ !?.,\n]*', text):
        reasons.append('unreliable-caption-ocr')
    if BRANDING.search(text):
        reasons.append('source-credit-is-not-an-editable-caption')
    width, height = row['canvas']
    for caption in row['caption_inventory']:
        if caption.get('editable') and caption['box'][2]*caption['box'][3] > .35*width*height:
            reasons.append('large-caption-erasure-needs-repair')
        if row['text_slots'] and not caption.get('editable') and re.search(
                '[\u4e00-\u9fff]', caption['original_text']) and not BRANDING.search(caption['original_text']):
            reasons.append('caption-inventory-needs-completeness-review')
    if row.get('warnings'):
        reasons.append('weak-tracking-needs-repair')
    # A detected face near the bottom edge can actually be a caption/prop.
    for frame in row['geometry']:
        for layer in frame:
            if layer['type'] == 'face':
                x,y,w,h = layer['box']
                if w*h < .045*width*height or y > .7*height:
                    reasons.append('small-or-low-face-anchor-needs-manual-check')
    return sorted(set(reasons))


def readable_name(row):
    name = row['name'].strip()
    if '|' in name or not re.search('[\u4e00-\u9fff]', name):
        captions = list(dict.fromkeys(x.replace('\n','').strip() for x in row['defaults']))
        if captions and any(re.search('[\u4e00-\u9fff]', x) for x in captions):
            name = ' / '.join(captions)
    name = re.sub(r'(?<=[\u4e00-\u9fff])\d{3,6}[-_]*', ' · ', name)
    name = re.sub(r'^[\d_ -]+', '', name)
    return name[:40] or row['key']


def signature(row):
    values = []
    with Image.open(row['path']) as source:
        for index in [0, source.n_frames//2, source.n_frames-1]:
            source.seek(index)
            pixels = np.asarray(source.convert('L').resize((17,16)), dtype='int16')
            values.append(pixels[:,1:] > pixels[:,:-1])
    return np.concatenate([x.ravel() for x in values])


def select(directory, target):
    rows = [json.loads(p.read_text()) for p in (directory/'drafts').glob('*.json')]
    ready = [x for x in rows if x['status']=='draft']
    held, eligible = {}, []
    for row in ready:
        reasons = preflight(row)
        audit_path = directory/'technical'/(row['key']+'.json')
        audit = json.loads(audit_path.read_text()) if audit_path.exists() else {}
        if audit.get('status')!='passed' or audit.get('spec_sha256')!=row['spec_sha256']:
            reasons.append('technical-audit-not-passed')
        if reasons:
            held[row['key']] = reasons
        else:
            eligible.append(row)
    ranked = sorted([x for x in eligible if x.get('source_rank')],
                    key=lambda x:(not x['animated'],x['source_rank'],x['index']))
    families = defaultdict(deque)
    for row in sorted([x for x in eligible if not x.get('source_rank')],key=lambda x:x['index']):
        families[row['category']].append(row)
    reference = []
    while any(families.values()):
        for family in sorted(families):
            if families[family]: reference.append(families[family].popleft())
    ordered = sorted(ranked+reference,key=lambda x:not x['animated'])
    selected, signatures, reserve = [], [], []
    for row in ordered:
        sig = signature(row)
        duplicate = next((old for old,old_sig in signatures
            if old['animated']==row['animated']
            and abs(old['canvas'][0]/old['canvas'][1]-row['canvas'][0]/row['canvas'][1])<.05
            and .75 < old['duration_ms']/row['duration_ms'] < 1.34
            and np.count_nonzero(sig != old_sig) / len(sig) < .025), None)
        if duplicate:
            held[row['key']] = ['perceptual-near-duplicate:'+duplicate['key']]
            continue
        signatures.append((row,sig))
        row['name'] = readable_name(row)
        row['metadata']['name'] = row['name']
        ranking = row.get('ranking_name','')
        hints = {'影视明星':['影视','明星'], '真人':['真人'], '萌宠':['动物','宠物'],
                 '动漫':['动漫','卡通'], '搞笑':['搞笑'], '可爱':['可爱']}
        if row['origin']=='weshine':
            row['metadata']['tags'] = list(dict.fromkeys(
                [term for signal,terms in hints.items() if signal in ranking for term in terms]
                + ['动图' if row['animated'] else '静图']))
        if row['image_slots']:
            row['metadata']['input_hint'] = ('替换原图头像，保留原有动作；表情来自上传照片。'
                + (f"另有 {row['text_slots']} 段原文可编辑。" if row['text_slots'] else '原文字保留。'))
        else:
            row['metadata']['input_hint'] = f"替换原图的 {row['text_slots']} 段文字，主体与动作保留。"
        # Rebuild generated terms from measured captions/source family, not from
        # last run's generated aliases. Explicit user edits live in reviews.json.
        row['metadata']['keywords'] = []
        row['metadata']['keywords'] = keywords(row['metadata'])
        path = directory/'drafts'/(row['key']+'.json')
        temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps(row,ensure_ascii=False,indent=2)+'\n');temp.replace(path)
        if len(selected)<target:
            selected.append(row)
        else:
            reserve.append(row['key'])
    records_path = directory/'reviews.json'
    records = json.loads(records_path.read_text()).get('records',{}) if records_path.exists() else {}
    # Never silently hide a template the human already annotated.
    selected_keys = {x['key'] for x in selected}
    selected.extend(x for x in ready if x['key'] in records and x['key'] not in selected_keys)
    selected_keys = {x['key'] for x in selected}
    reserve = [key for key in reserve if key not in selected_keys]
    held = {key:reasons for key,reasons in held.items() if key not in selected_keys}
    manifest = {'version':1,'publication':'not-published','human_review':'required',
        'baseline':959,'target':1500,'needed':541,'review_target':target,
        'keys':[x['key'] for x in selected],
        'recipes':{x['key']:x['spec_sha256'] for x in selected},
        'counts':{'converted_drafts':len(ready),'selected':len(selected),
            'animated':sum(x['animated'] for x in selected),
            'ranked_animated':sum(x['animated'] and bool(x.get('source_rank')) for x in selected),
            'image_slots':sum(bool(x['image_slots']) for x in selected),
            'reserve':len(reserve),'held':len(held),'unconverted':len(rows)-len(ready)},
        'selection_policy':'actual animations first; observed rankings, then rotating source families; technical and conservative semantic preflight; three-keyframe near-duplicate filter',
        'held_reasons':dict(Counter(reason.split(':')[0] for reasons in held.values() for reason in reasons))}
    manifest['selection_sha256'] = hashlib.sha256(json.dumps(manifest['recipes'],sort_keys=True).encode()).hexdigest()
    for name,value in [('selection.json',manifest),('preflight-holds.json',held),('reserve.json',reserve)]:
        path=directory/name;temp=path.with_suffix('.tmp')
        temp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');temp.replace(path)
    print(json.dumps(manifest['counts'],ensure_ascii=False))
    return manifest


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--target',type=int,default=650);args=p.parse_args()
    select(args.directory.resolve(),args.target)
