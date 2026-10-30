"""Resumable offline source-element drafts. No production DB or publication.

Source bytes and every decoded duration are inventoried before resampling.
OCR/face tracking are proposals; real avatar renders are for human review.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.parse
import urllib.request

from PIL import Image, ImageOps

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'tools/collect'))


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)


def source_identity(item):
    url = item.get('source_url','')
    if 'github.com/zhaoolee/ChineseBQB/blob/' in url:
        return 'chinesebqb:' + urllib.parse.unquote(url.split('/blob/',1)[1].split('/',1)[1])
    url = item.get('image_url') or item.get('source_image_url') or ''
    if 'weshine' in url:
        match = re.search(r'(?:s_)?([a-f0-9]{32})\.',url)
        if match:
            return 'weshine:' + match.group(1)
    return ''


def normalize(raw):
    """Preserve the complete bounded loop, recording its exact frame mapping."""
    with Image.open(BytesIO(raw)) as source:
        count = getattr(source, 'n_frames', 1)
        if count > 240 or source.width * source.height * count > 60_000_000:
            raise ValueError('source timeline exceeds offline decode budget')
        if min(source.size) < 64:
            raise ValueError('source too small for editable slots')
        durations = []
        # Decode all composited frames, including frames not selected below.
        for i in range(count):
            source.seek(i)
            source.load()
            durations.append(max(20, int(source.info.get('duration', 100))))
        if sum(durations) > 8000:
            raise ValueError('source loop longer than eight seconds; manual authoring required')
        if count == 1:
            durations = [100]
        indices = sorted(set(round(i * (count - 1) / min(23, count - 1))
                             for i in range(min(24, count)))) if count > 1 else [0]
        frames, timing = [], []
        size = None
        for position, i in enumerate(indices):
            source.seek(i)
            frame = Image.alpha_composite(Image.new('RGBA', source.size, 'white'), source.convert('RGBA')).convert('RGB')
            frame.thumbnail((384, 384), Image.Resampling.LANCZOS)
            size = frame.size
            frames.append(frame)
            end = indices[position + 1] if position + 1 < len(indices) else count
            timing.append(sum(durations[i:end]))
        loop = source.info.get('loop')
    output = BytesIO()
    if len(frames) > 1:
        frames[0].save(output, 'GIF', save_all=True, append_images=frames[1:],
                       duration=timing, disposal=2, optimize=False,
                       **({'loop':loop} if loop is not None else {}))
    else:
        frames[0].save(output, 'PNG')
    with Image.open(BytesIO(output.getvalue())) as result:
        decoded = []
        for i in range(getattr(result, 'n_frames', 1)):
            result.seek(i)
            decoded.append(int(result.info.get('duration', 100)))
        if sum(decoded) != sum(durations) or len(decoded) != len(indices):
            raise ValueError('GIF normalization merged frames or changed timing')
    return output.getvalue(), {'canvas': list(size), 'original_frames': count,
                               'frames': len(indices), 'source_indices': indices,
                               'durations': decoded, 'duration_ms': sum(durations),
                               'loop': loop, 'animated': len(indices) > 1}


def discover(directory):
    from meme_generator.features.bulk_templates import chinese_inventory, weshine_state_inventory
    tree = json.loads((directory / 'chinesebqb-tree.json').read_text())
    items = chinese_inventory(tree)
    ranked = weshine_state_inventory(json.loads((directory / 'weshine-rank.json').read_text()), ranked=True)
    home = weshine_state_inventory(json.loads((directory / 'weshine-home.json').read_text()))
    for path in sorted((directory/'weshine-ranks').glob('*.json')):
        state = json.loads(path.read_text())
        extra = weshine_state_inventory(state, ranked=True)
        for item in extra:
            item['source_url'] = 'https://u.weshineapp.com/rank/'+path.stem
            item['ranking_name'] = state['data'][0].get('title',path.stem)
        ranked.extend(extra)
    seen = set()
    candidates = []
    baseline = json.loads((directory/'baseline-public-metadata.json').read_text())
    known_sources = {source_identity(r['metadata']) for r in baseline} - {''}
    full = directory / 'weshine-full.json'
    if full.exists():
        resolved = json.loads(full.read_text())
        by_url = {x['poster_url']:x for x in resolved if x.get('detail_status') == 'resolved'}
        ranked = [by_url.get(x['image_url'], x) for x in ranked]
        home = [by_url.get(x['image_url'], x) for x in home]
    for item in [*ranked, *home, *items]:
        if source_identity(item) in known_sources:
            continue
        if item['image_url'] in seen:
            continue
        seen.add(item['image_url'])
        item['observed_at'] = '2026-10-30'
        item['hotness_method'] = item.get('hotness_method', 'repository-reference-no-popularity-data')
        candidates.append(item)
    candidates.sort(key=lambda i: (i.get('source_rank') or 100000,
                                    not i.get('animated'), i.get('bytes', 0) > 2_000_000,
                                    i['id']))
    save(directory / 'discovery.json', candidates)
    print(json.dumps({'discovered': len(candidates), 'excluded_known_source_identities':len(known_sources), 'gif_candidates': sum(x.get('animated', False) for x in candidates),
                      'observed_ranked': len(ranked), 'revision': tree['sha']}), flush=True)


def resolve_weshine(directory):
    """Use the public site's observed anonymous request contract, never guess
    a full GIF URL by editing a thumbnail name. No login/user token is used."""
    from meme_generator.features.bulk_templates import weshine_state_inventory
    rows = weshine_state_inventory(json.loads((directory/'weshine-rank.json').read_text()),ranked=True)
    rows += weshine_state_inventory(json.loads((directory/'weshine-home.json').read_text()))
    for path in sorted((directory/'weshine-ranks').glob('*.json')):
        state = json.loads(path.read_text())
        extra = weshine_state_inventory(state,ranked=True)
        for row in extra:
            row['source_url'] = 'https://u.weshineapp.com/rank/'+path.stem
            row['ranking_name'] = state['data'][0].get('title',path.stem)
        rows.extend(extra)
    unique = {x['image_url']:x for x in reversed(rows)}
    details = directory/'weshine-details'
    details.mkdir(exist_ok=True)

    def one(item):
        row = dict(item)
        try:
            identifier = Path(urllib.parse.urlsplit(item['image_url']).path).stem.removeprefix('s_')
            if not re.fullmatch('[a-f0-9]{32}',identifier):
                raise ValueError('no observed public GIF identifier')
            target = details/(identifier+'.json')
            if target.exists():
                data = json.loads(target.read_text())
            else:
                params = {'gif_uniqid':identifier,'from':'pc','timestamp':int(time.time()*1000)}
                query = urllib.parse.urlencode(sorted(params.items()))
                params['sign'] = hashlib.md5(('weshine@2021#'+hashlib.md5(query.encode()).hexdigest()+
                    '#Y2MyZTlmYmUxMWY5MjJkODE1ODE4NzgzNDNmZWI3NDM=').encode()).hexdigest().upper()
                url = 'https://platform.weshine.im/v1.0/package/emojidetail?'+urllib.parse.urlencode(params)
                request = urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0','Referer':'https://u.weshineapp.com/'})
                with urllib.request.urlopen(request,timeout=20) as response:
                    raw = response.read(256*1024+1)
                if len(raw)>256*1024:
                    raise ValueError('detail response too large')
                data = json.loads(raw)
                if data.get('meta',{}).get('status') != 200:
                    raise ValueError('public detail unavailable; no authentication bypass')
                save(target,data)
            info = data['data']
            url = info['path']
            parsed = urllib.parse.urlsplit(url)
            if parsed.scheme!='https' or parsed.hostname!='dl5.weshineapp.com' or not parsed.path.startswith('/gif/'):
                raise ValueError('untrusted original media URL')
            row.update(id=hashlib.sha256(url.encode()).hexdigest(),poster_url=item['image_url'],image_url=url,
                       name=info.get('title',''),source_author=info.get('author_name',''),
                       detail_status='resolved',detail_contract='public site /package/emojidetail',
                       animated=parsed.path.lower().endswith('.gif'))
        except Exception as error:
            row.update(detail_status='unavailable',reason=type(error).__name__+': '+str(error)[:120])
        return row

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(one,unique.values()))
    save(directory/'weshine-full.json',results)
    print(json.dumps({'weshine_details':Counter(r['detail_status'] for r in results)}),flush=True)


def rankings(directory):
    import subprocess
    state = json.loads((directory/'weshine-rank.json').read_text())['data'][0]
    observed = [child for group in state['rankData'] if group.get('type')=='expression'
                for child in group['child'] if re.fullmatch(r'expression_kind_[1-8]',str(child.get('category_id','')))]
    out = directory/'weshine-ranks'
    out.mkdir(exist_ok=True)
    for row in observed:
        name = row['category_id']
        target = out/(name+'.html')
        if not target.exists():
            request=urllib.request.Request('https://u.weshineapp.com/rank/'+name,headers={'User-Agent':'Mozilla/5.0'})
            with urllib.request.urlopen(request,timeout=25) as response:
                raw=response.read(2*1024**2+1)
            if len(raw)>2*1024**2:
                raise ValueError('ranking page exceeds limit')
            target.write_bytes(raw)
        subprocess.run(['node',str(REPO/'tools/collect/weshine-state.cjs'),str(target),str(target.with_suffix('.json'))],check=True,capture_output=True)
        parsed=json.loads(target.with_suffix('.json').read_text())
        print(json.dumps({'ranking':row['name'],'entries':len(parsed['data'][0].get('rankListData',[]))},ensure_ascii=False),flush=True)


def download(directory, limit, workers):
    from meme_generator.features.bulk_templates import fetch
    known = json.loads((directory / 'baseline-public-metadata.json').read_text())
    known_hashes = {r['metadata'].get('original_hash') for r in known}
    items = json.loads((directory / 'discovery.json').read_text())
    # Prioritize actual animation sources. Static sources remain a separate,
    # explicitly bounded reserve and never masquerade as GIF templates.
    selected = [i for i in items if i.get('animated')][:limit]
    selected += [i for i in items if not i.get('animated')][:max(60, limit // 5)]
    for i, item in enumerate(selected):
        item['_review_order'] = i
    for name in ['sources', 'originals', 'downloads']:
        (directory / name).mkdir(exist_ok=True)

    def one(item):
        dest = directory / 'downloads' / (item['id'] + '.json')
        if dest.exists():
            return {**json.loads(dest.read_text()), '_review_order':item['_review_order']}
        record = {**item, 'status': 'source-pending'}
        try:
            original = directory / 'originals' / (item['id'] + '.image')
            raw = original.read_bytes() if original.exists() else fetch(item['image_url'], 6 * 1024**2)
            digest = hashlib.sha256(raw).hexdigest()
            record['original_sha256'] = digest
            if digest in known_hashes:
                record.update(status='duplicate-published-or-withdrawn')
            else:
                original.write_bytes(raw)
                normalized, timeline = normalize(raw)
                suffix = '.gif' if timeline['animated'] else '.png'
                path = directory / 'sources' / (digest + suffix)
                path.write_bytes(normalized)
                record.update(timeline, path=str(path), original_path=str(original),
                              normalized_sha256=hashlib.sha256(normalized).hexdigest(),
                              key='auto_element_' + digest[:24], status='source-ready')
        except Exception as error:
            record.update(reason=type(error).__name__ + ': ' + str(error)[:180])
        save(dest, record)
        return record

    started = time.monotonic()
    results = []
    def inventory():
        unique, seen = [], set()
        for row in sorted(results, key=lambda r:r['_review_order']):
            if row['status'] != 'source-ready' or row['normalized_sha256'] in seen:
                continue
            seen.add(row['normalized_sha256'])
            unique.append({**row, 'index':row['_review_order']})
        save(directory/'inventory.json',unique)
        return unique
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for task in as_completed([pool.submit(one, item) for item in selected]):
            results.append(task.result())
            if len(results) % 25 == 0:
                print(json.dumps({'downloaded': len(results), 'states': Counter(r['status'] for r in results),
                                  'seconds': round(time.monotonic() - started)}), flush=True)
            if len(results) % 100 == 0:
                inventory()
    unique = inventory()
    save(directory / 'download-report.json', {'states': Counter(r['status'] for r in results),
                                              'unique_sources': len(unique),
                                              'animated': sum(r['animated'] for r in unique),
                                              'results': results})
    print(json.dumps({'unique_sources': len(unique), 'animated': sum(r['animated'] for r in unique)}), flush=True)


def prepare_one(row, directory, portrait_paths):
    import cv2
    import numpy as np
    from rapidocr_onnxruntime import RapidOCR
    from meme_generator.features.declarative import render
    from meme_generator.features.element_templates import compile_elements, fingerprint
    from meme_generator.features.store import root
    from rebuild_elements import propose, caption_tracks

    result_path = directory / 'drafts' / (row['key'] + '.json')
    if result_path.exists():
        return json.loads(result_path.read_text())
    result = {**row, 'status': 'pending', 'publication_status': 'not-published', 'review_status': 'awaiting-human'}
    try:
        if row['animated'] and row.get('loop') != 0:
            raise ValueError('finite/one-shot GIF needs a loop-aware adapter; not counted as a template')
        engine = getattr(prepare_one, '_ocr', None)
        if engine is None:
            engine = RapidOCR(intra_op_num_threads=1, inter_op_num_threads=1, det_limit_side_len=384, text_score=.65)
            prepare_one._ocr = engine
        cv2.setNumThreads(1)
        human = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        cat = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalcatface_extended.xml')
        frames, analysis = [], []
        with Image.open(row['path']) as source:
            for i in range(source.n_frames if hasattr(source, 'n_frames') else 1):
                source.seek(i)
                frame = np.array(source.convert('RGB'))
                frames.append(frame)
                gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
                faces = {kind: [[int(v) for v in box] for box in detector.detectMultiScale(
                    gray, scaleFactor=1.1, minNeighbors=5, minSize=(22,22))]
                    for kind, detector in [('person', human), ('cat', cat)]}
                scale = max(1, min(2, 512 / max(source.size)))
                detected, _ = engine(cv2.resize(frame, None, fx=scale, fy=scale))
                captions = [{'polygon': [[round(float(x)/scale), round(float(y)/scale)] for x,y in polygon],
                             'text': text, 'confidence': round(float(confidence),4)}
                            for polygon, text, confidence in detected or []]
                analysis.append({'index': i, 'duration_ms': row['durations'][i], 'faces': faces, 'captions': captions})
        # A measured face is optional. Captions stay independent. No generic
        # panel or extra phrase is added to a source that has no editable part.
        decision = {}
        people = analysis[0]['faces']['person']
        cats = analysis[0]['faces']['cat']
        chosen = max(people or cats, key=lambda b:b[2]*b[3], default=None)
        if chosen and chosen[2]*chosen[3] >= row['canvas'][0]*row['canvas'][1]*.035:
            decision['human'] = bool(people)
            if not people:
                decision['faces'] = [{'box': chosen, 'tone': 'original'}]
        if len(caption_tracks({'frames':analysis},tuple(row['canvas']))[0]) > 5:
            raise ValueError('more than five independent caption tracks; no partial-caption conversion')
        try:
            plans, defaults, captions, confidence = propose(row, {'frames': analysis}, decision, frames)
        except ValueError as error:
            if 'intersects another slot' not in str(error):
                raise
            plans, defaults, captions, confidence = propose(row, {'frames':analysis}, {}, frames)
        images = max((l.get('slot',0)+1 for frame in plans for l in frame if l['type']=='face'), default=0)
        if not images and not defaults:
            raise ValueError('no measured replaceable face or complete caption')
        if len(defaults) > 5:
            raise ValueError('too many independent captions for this adapter')
        # The proposal is retained when uncertain so the human can diagnose it;
        # weak tracking is not silently turned into visual approval.
        if confidence and min(min(x) for x in confidence) < .3:
            result['warnings'] = ['tracking-confidence-low; inspect full loop']
        raw = Path(row['path']).read_bytes()
        spec, assets, geometry = compile_elements(raw, plans, defaults)
        asset_dir = root() / 'template_assets'
        asset_dir.mkdir(exist_ok=True, parents=True)
        for digest, value in assets.items():
            suffix = '.gif' if value[:3] == b'GIF' else '.png'
            (asset_dir / (digest + suffix)).write_bytes(value)
        category = re.sub(r'^\d+[A-Za-z_]*|BQB|weshine-', '', row.get('category','')).strip('_')
        source_name = re.sub(r'^\d+[-_ ]*', '', row.get('name','')).strip()
        name = (source_name or (' / '.join(defaults) if defaults else '') or category or '来源待命名')[:40]
        media = directory / 'media'
        media.mkdir(exist_ok=True)
        outputs = []
        for sample_index, (sample, path) in enumerate(portrait_paths):
            with Image.open(path) as photo:
                inputs = [photo.convert('RGBA')] * images
            texts = defaults if images else [
                ('第一行\n第二行' if '\n' in value else ['哈哈','收到','好的'][sample_index])
                for value in defaults]
            data = render(spec, inputs, texts).getvalue()
            suffix = '.gif' if data[:3] == b'GIF' else '.png'
            dest = media / (row['key'] + '-' + sample + suffix)
            dest.write_bytes(data)
            with Image.open(BytesIO(data)) as output:
                times = []
                for i in range(getattr(output,'n_frames',1)):
                    output.seek(i)
                    times.append(int(output.info.get('duration',100)))
                if output.size != tuple(row['canvas']) or sum(times) != row['duration_ms']:
                    raise ValueError('actual output canvas or full-loop duration changed')
                if row['animated'] and len(times) < 2:
                    raise ValueError('actual output lost animation')
                if row['animated'] and output.info.get('loop') != row['loop']:
                    raise ValueError('actual output changed loop setting')
            outputs.append({'sample':sample if images else 'caption-'+str(sample_index+1),
                            'file':dest.name,'frames':len(times),'duration_ms':sum(times),
                            'bytes':len(data),'texts':texts})
        if defaults:
            with Image.open(portrait_paths[0][1]) as photo:
                inputs = [photo.convert('RGBA')] * images
            for label, texts in [('blank', ['']*len(defaults)),
                                 ('edited', ['第一行\n第二行' if '\n' in x else '收到' for x in defaults])]:
                data = render(spec, inputs, texts).getvalue()
                suffix = '.gif' if data[:3] == b'GIF' else '.png'
                dest = media / (row['key']+'-'+label+suffix)
                dest.write_bytes(data)
                outputs.append({'sample':label,'file':dest.name,'bytes':len(data),'texts':texts})
        from meme_generator.features.search_terms import keywords
        metadata = {'name':name,'keywords':[], 'tags':[category,'动图' if row['animated'] else '静图'],
                    'default_texts':defaults,'min_images':images,'max_images':images,
                    'min_texts':len(defaults),'max_texts':len(defaults),
                    'origin':row['origin'],'source_url':row['source_url'],'source_image_url':row['image_url'],
                    'source_revision':row.get('source_revision',''),'original_hash':row['original_sha256'],
                    'author':'原作者未核实','license':'unverified','source_use':'explicit-user-request-with-attribution',
                    'animated':row['animated'],'conversion':'element-replacement-v1',
                    'input_hint':'替换原图已有头像和/或原文；上传头像提供表情。待审核，保护区与每帧轨迹须复核。',
                    'caption_inventory':captions, 'review':{'visual_status':'pending-human-review'}}
        metadata['keywords'] = keywords(metadata)
        result.update(status='draft', name=name, metadata=metadata, spec=spec,
                      spec_sha256=fingerprint(spec), asset_hashes=list(assets),
                      image_slots=images, text_slots=len(defaults), defaults=defaults,
                      caption_inventory=captions, geometry=geometry, outputs=outputs,
                      tracking_confidence=confidence)
        save(directory / 'analysis' / (row['key']+'.json'), analysis)
    except Exception as error:
        result.update(reason=type(error).__name__ + ': ' + str(error)[:240])
    save(result_path, result)
    if result['status'] == 'draft':
        ready = directory / 'ready'
        ready.mkdir(exist_ok=True)
        (ready / row['key']).touch()
        if not row['animated']:
            static = directory / 'ready-static'
            static.mkdir(exist_ok=True)
            (static / row['key']).touch()
    return result


def prepare(directory, target, shard, shards, ranked_only=False):
    os.environ['GENSTICKER_STATE_DIR'] = str(directory / 'state')
    os.environ['GENSTICKER_BOOTSTRAP_SEEDS'] = '0'
    os.environ['OMP_NUM_THREADS'] = '1'
    rows = json.loads((directory / 'inventory.json').read_text())
    rows.sort(key=lambda row:(not row['animated'], row['index']))
    portraits = directory.parent / 'fusion-smallmodels-20261028/portraits'
    photos = [(name, portraits/(name+'.png')) for name in ['S03','S17','S29']]
    started = time.monotonic()
    counts = Counter()
    for row in rows:
        if ranked_only and (not row.get('source_rank') or not row['animated']):
            continue
        if row['index'] % shards != shard:
            continue
        if not row['animated'] and len(list((directory/'ready-static').glob('*'))) >= 150:
            continue
        if len(list((directory/'drafts').glob('*.json'))) >= len(rows):
            break
        drafts = len(list((directory/'ready').glob('*')))
        if drafts >= target:
            break
        result = prepare_one(row, directory, photos)
        counts[result['status']] += 1
        print(json.dumps({'shard':shard,'index':row['index'],'status':result['status'],
                          'name':result.get('name',''),'reason':result.get('reason',''),
                          'counts':counts,'seconds':round(time.monotonic()-started)},ensure_ascii=False),flush=True)
    save(directory / ('prepare-shard-'+str(shard)+'.json'), {'counts':counts,'seconds':round(time.monotonic()-started)})


def main():
    p=argparse.ArgumentParser()
    p.add_argument('command', choices=['discover','download','prepare','resolve-weshine','rankings'])
    p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--limit',type=int,default=1672)
    p.add_argument('--workers',type=int,default=4)
    p.add_argument('--target',type=int,default=650)
    p.add_argument('--shard',type=int,default=0)
    p.add_argument('--shards',type=int,default=1)
    p.add_argument('--ranked-only',action='store_true')
    a=p.parse_args();directory=a.directory.resolve();directory.mkdir(exist_ok=True)
    if a.command=='discover':discover(directory)
    elif a.command=='resolve-weshine':resolve_weshine(directory)
    elif a.command=='rankings':rankings(directory)
    elif a.command=='download':download(directory,a.limit,min(4,max(1,a.workers)))
    else:prepare(directory,a.target,a.shard,a.shards,a.ranked_only)


if __name__=='__main__':main()
