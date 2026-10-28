#!/usr/bin/env python3
"""Evaluate every published image template, retaining failures and stable IDs.

Test portraits and generated media stay in a private, isolated state directory.
The before image uses the exact live recipe captured before region corrections.
"""
import argparse, copy, hashlib, importlib.util, io, json, random, resource, sys, time
from collections import Counter
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image
from meme_generator.features import catalog, expression_runtime as rt
from meme_generator.features.declarative import render
from meme_generator.features.store import connect
from meme_generator.manager import get_meme


def main():
    p=argparse.ArgumentParser()
    for name in ['snapshot','updates','review','inputs','output']:
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--sample',default='S03')
    p.add_argument('--only',nargs='*')
    p.add_argument('--reuse',type=Path)
    a=p.parse_args()
    loader=importlib.util.spec_from_file_location('test_ab',Path(__file__).with_name('test_expression_library.py'))
    helper=importlib.util.module_from_spec(loader);loader.loader.exec_module(helper)
    snapshot=json.loads(a.snapshot.read_text());rows={r['key']:r for r in snapshot['image_templates']}
    updates={i['key']:i for i in json.loads((a.updates/'compiled.json').read_text())}
    review=json.loads(a.review.read_text());decisions={r['key']:r for r in review}
    order=[r['key'] for r in review]+sorted(set(rows)-set(decisions))
    ids={key:f'T{n:03}' for n,key in enumerate(order,1)}
    if a.only:order=[key for key in order if ids[key] in a.only or key in a.only]
    helper.initialize(list(rows.values()))
    native_originals={key:get_meme(key).function for key,row in rows.items() if not row['spec']}
    # Install the bounded corrections through the production publication path.
    for key,item in updates.items():
        catalog.publish(key,item['metadata'],item['spec'],minimum_version=item['version'])
    catalog.refresh()
    db=connect()
    try:versions={r['key']:dict(r) for r in db.execute('SELECT * FROM templates')}
    finally:db.close()
    a.output.mkdir(parents=True,exist_ok=True);media=a.output/'media';media.mkdir(exist_ok=True)
    prior=json.loads((a.reuse/'report.json').read_text()) if a.reuse and (a.reuse/'report.json').exists() else {}
    prior_cases={c['key']:c for c in prior.get('cases',[]) if c['sample']==a.sample}
    prior_templates={t['key']:t for t in prior.get('templates',[])}
    report={'status':'running','scope':'all published image templates; S03 representative portrait as requested; actual production generation paths',
            'snapshot_published':snapshot['published_count'],'image_templates':len(rows),'samples':[a.sample],
            'cases':[],'templates':[],'visual_quality_approved':False,'review_counts':dict(Counter(r['rating'] for r in review)),
            'selection':{'seed':'GenSticker-expression-AB-20261027-v1','sample_keys':order}}
    raw_input=(a.inputs/(a.sample+'.png')).read_bytes()
    report['input_sha256']=hashlib.sha256(raw_input).hexdigest()
    for n,key in enumerate(order,1):
        row=rows[key];tid=ids[key];current=get_meme(key);meta=json.loads(versions[key]['metadata'])
        policy=meta.get('expression_policy',{});rating=decisions.get(key,{}).get('rating','未标注')
        texts=meta.get('default_texts',[]).copy();minimum=meta.get('min_texts',0);maximum=meta.get('max_texts',0)
        if not minimum<=len(texts)<=maximum:texts=['测试'+str(i+1) for i in range(minimum)]
        count=max(1,meta.get('min_images',1));args={'user_infos':[{'name':'测试用户'+str(i+1)} for i in range(count)]}
        t={'id':tid,'key':key,'name':meta['name'],'mode':policy.get('mode','原算法'),
           'adapter':policy.get('adapter','declarative' if row['spec'] else 'native-input'),
           'supported_regions':policy.get('supported_regions',0),'regions':policy.get('regions',0),
           'reasons':policy.get('reasons',[]),'base_version':row['version'],'version':versions[key]['version'],
           'previous_rating':rating,'changed':key in updates,'texts':texts,'image_slots':count,
           'calibration':policy.get('calibration'),'fingerprint':versions[key]['fingerprint'],
           'baseline_fingerprint':row['fingerprint']}
        try:
            if row['spec']:raw=render(row['spec'],[],preview=True).getvalue()
            else:
                folder=Path(sys.modules['meme_generator'].__file__).parent/'memes'/key
                example=next(iter(sorted(folder.glob('example.*'))),None);raw=example.read_bytes() if example else None
            if raw:t['preview']=helper.inspect(raw,media/(tid+'-template'))['file']
        except Exception as exc:t['preview_error']=type(exc).__name__+': '+str(exc)[:200]
        report['templates'].append(t)
        cached=prior_cases.get(key)
        if (cached and cached.get('status')!='failed' and prior.get('input_sha256')==report['input_sha256']
                and all(prior_templates[key].get(field)==t[field] for field in ['version','fingerprint','baseline_fingerprint'])):
            c=copy.deepcopy(cached)
            for variant in ['baseline','result']:
                if c.get(variant):
                    src=a.reuse/'media'/c[variant]['file'];dst=media/src.name
                    if not dst.exists():dst.hardlink_to(src.resolve())
            c['reused_verified_case']=True
        else:
            c={'template':tid,'key':key,'sample':a.sample,'mode':t['mode'],'status':'running',
               'metrics':[],'source_prepare_calls':0,'supported_sources':0}
            seed=int(hashlib.sha256((key+a.sample).encode()).hexdigest()[:8],16)
            try:
                images=[raw_input]*count
                random.seed(seed);np.random.seed(seed);start=time.perf_counter()
                if row['spec']:
                    baseline=render(row['spec'],[Image.open(io.BytesIO(raw_input))]*count,texts).getvalue()
                else:
                    oldpolicy=row['metadata'].get('expression_policy',{})
                    old=replace(current,function=rt.wrap_native(native_originals[key],oldpolicy))
                    baseline=old(images=images,texts=texts,args=args).getvalue()
                c['baseline_ms']=round((time.perf_counter()-start)*1000,1)
                c['baseline']=helper.inspect(baseline,media/(tid+'-'+a.sample+'-before'))
                prepare=rt.prepare;frame=rt.math.render_frame
                def observe_prepare(image):
                    c['source_prepare_calls']+=1;v=prepare(image);c['supported_sources']+=v is not None;return v
                def observe_frame(*args,**kwargs):
                    image,metric=frame(*args,**kwargs);c['metrics'].append(metric);return image,metric
                random.seed(seed);np.random.seed(seed);start=time.perf_counter()
                with patch.object(rt,'prepare',side_effect=observe_prepare),patch.object(rt.math,'render_frame',side_effect=observe_frame):
                    result=current(images=images,texts=texts,args=args).getvalue()
                c['render_ms']=round((time.perf_counter()-start)*1000,1)
                c['result']=helper.inspect(result,media/(tid+'-'+a.sample+'-after'))
                c['applied_regions']=len(c['metrics']);c['status']='fused' if c['metrics'] else 'fallback'
                c['timeline_matches_baseline']=c['result']['frames']==c['baseline']['frames'] and c['result']['durations']==c['baseline']['durations']
                c['dimensions_match_baseline']=c['result']['size']==c['baseline']['size']
                c['visible_change']=c['result']['frame_hashes']!=c['baseline']['frame_hashes']
                if c['source_prepare_calls']>count:raise ValueError('source inference repeated')
            except Exception as exc:c.update(status='failed',error=type(exc).__name__+': '+str(exc)[:300])
        c['previous_rating']=rating;c['changed']=key in updates
        if rating=='可用' and c.get('result') and c.get('baseline'):
            c['accepted_output_unchanged']=c['result']['frame_hashes']==c['baseline']['frame_hashes']
        report['cases'].append(c)
        print(n,len(order),tid,meta['name'],c['status'],c.get('render_ms'),flush=True)
        (a.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    report['status']='completed';report['counts']=dict(Counter(c['status'] for c in report['cases']))
    report['dimension_mismatches']=sum(c.get('dimensions_match_baseline') is False for c in report['cases'])
    report['timeline_mismatches']=sum(c.get('timeline_matches_baseline') is False for c in report['cases'])
    report['accepted_output_changes']=sum(c.get('accepted_output_unchanged') is False for c in report['cases'])
    report['peak_rss_mib']=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/(1048576 if sys.platform=='darwin' else 1024),1)
    (a.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    rt.close();print('DONE',report['counts'],flush=True)


if __name__=='__main__':main()
