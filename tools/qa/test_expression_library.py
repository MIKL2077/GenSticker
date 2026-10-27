#!/usr/bin/env python3
"""Private six-portrait x 100-template evaluation using production call paths.

Run in isolated GENSTICKER_STATE_DIR. Input/output files never enter the delta.
The report retains every sampled template and all failures, including fallbacks.
"""
import argparse,copy,hashlib,io,json,os,random,time,resource,sys
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image,ImageOps
from meme_generator.features import catalog,expression_runtime as rt
from meme_generator.features.declarative import render
from meme_generator.features.store import connect,root
from meme_generator.manager import get_meme

SAMPLES=['S03','S17','S29','S32','S09','S26']


def inspect(raw,path):
    path=path.with_suffix('.gif' if raw.startswith(b'GIF') else '.png' if raw.startswith(b'\x89PNG') else '.jpg');path.write_bytes(raw)
    durations=[];hashes=[]
    with Image.open(io.BytesIO(raw)) as im:
        for i in range(getattr(im,'n_frames',1)):
            im.seek(i);durations.append(im.info.get('duration',0));hashes.append(hashlib.sha256(im.convert('RGB').tobytes()).hexdigest())
        return {'file':path.name,'bytes':len(raw),'size':list(im.size),'frames':len(durations),'durations':durations,'frame_hashes':hashes}


def initialize(rows):
    db=connect()
    try:
        with db:
            for row in rows:
                spec=json.dumps(row['spec']) if row['spec'] else None;metadata=json.dumps(row['metadata'],ensure_ascii=False)
                db.execute('INSERT OR IGNORE INTO templates(id,key,version,fingerprint,metadata,spec) VALUES(?,?,?,?,?,?)',(row['id'],row['key'],row['version'],row['fingerprint'],metadata,spec))
                db.execute('INSERT OR IGNORE INTO template_versions VALUES(?,?,?,?,?)',(row['id'],row['version'],row['fingerprint'],metadata,spec))
    finally:db.close()


def main():
    p=argparse.ArgumentParser();p.add_argument('--snapshot',type=Path,required=True);p.add_argument('--selection',type=Path,required=True);p.add_argument('--inputs',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    snapshot=json.loads(a.snapshot.read_text());rows={r['key']:r for r in snapshot['image_templates']};selection=json.loads(a.selection.read_text());initialize(list(rows.values()))
    originals={key:get_meme(key).function for key,row in rows.items() if not row['spec']}
    from meme_generator.features.expression_library import restore
    changed=restore();again=restore();catalog.refresh()
    db=connect()
    try:versions={r['key']:dict(r) for r in db.execute('SELECT * FROM templates')}
    finally:db.close()
    if len(versions)!=482 or any(json.loads(r['metadata']).get('expression_policy',{}).get('mode')!=selection['assignment'][k] for k,r in versions.items()):raise ValueError('incomplete A/B policy installation')
    a.output.mkdir(parents=True,exist_ok=True);media=a.output/'media';media.mkdir(exist_ok=True)
    report={'status':'running','scope':'100 preselected templates x six retained test photos; real production generation paths; local CPU, no queue/network latency','selection':selection,'snapshot_published':snapshot['published_count'],'policy_templates':len(rows),'restore_changed':changed,'second_restore_changed':again,'samples':SAMPLES,'cases':[],'templates':[],'visual_quality_approved':False}
    for n,key in enumerate(selection['sample_keys'],1):
        row=rows[key];current=get_meme(key);old=replace(current,function=originals[key]) if key in originals else None
        metadata=json.loads(versions[key]['metadata']);policy=metadata['expression_policy'];tid=f'T{n:03}'
        texts=metadata.get('default_texts',[]).copy();minimum=metadata.get('min_texts',0);maximum=metadata.get('max_texts',0)
        if not minimum<=len(texts)<=maximum:texts=['测试'+str(i+1) for i in range(minimum)]
        count=max(1,metadata.get('min_images',1));args={'user_infos':[{'name':'测试用户'+str(i+1)} for i in range(count)]}
        template={'id':tid,'key':key,'name':metadata['name'],'mode':policy['mode'],'adapter':policy['adapter'],'supported_regions':policy['supported_regions'],'regions':policy['regions'],'reasons':policy['reasons'],'base_version':row['version'],'version':versions[key]['version'],'texts':texts,'image_slots':count}
        if row['spec']:
            raw=render(row['spec'],[],preview=True).getvalue()
        else:
            folder=Path(sys.modules['meme_generator'].__file__).parent/'memes'/key
            example=next(iter(sorted(folder.glob('example.*'))),None)
            raw=example.read_bytes() if example else None
        if raw:template['preview']=inspect(raw,media/(tid+'-template'))['file']
        report['templates'].append(template)
        for sample in SAMPLES:
            raw_input=(a.inputs/(sample+'.png')).read_bytes();images=[raw_input]*count;seed=int(hashlib.sha256((key+sample).encode()).hexdigest()[:8],16)
            case={'template':tid,'key':key,'sample':sample,'mode':policy['mode'],'status':'running','metrics':[],'source_prepare_calls':0,'supported_sources':0}
            try:
                random.seed(seed);np.random.seed(seed);start=time.perf_counter()
                if old:baseline=old(images=images,texts=texts,args=args).getvalue()
                else:baseline=render(row['spec'],[Image.open(io.BytesIO(raw_input))]*count,texts).getvalue()
                case['baseline_ms']=round((time.perf_counter()-start)*1000,1);case['baseline']=inspect(baseline,media/(tid+'-'+sample+'-before'))
                prepare=rt.prepare;frame=rt.math.render_frame
                def observe_prepare(image):
                    case['source_prepare_calls']+=1;value=prepare(image);case['supported_sources']+=value is not None;return value
                def observe_frame(*args,**kwargs):
                    image,metric=frame(*args,**kwargs);case['metrics'].append(metric);return image,metric
                random.seed(seed);np.random.seed(seed);start=time.perf_counter()
                with patch.object(rt,'prepare',side_effect=observe_prepare),patch.object(rt.math,'render_frame',side_effect=observe_frame):
                    result=current(images=images,texts=texts,args=args).getvalue()
                case['render_ms']=round((time.perf_counter()-start)*1000,1);case['result']=inspect(result,media/(tid+'-'+sample+'-after'))
                case['applied_regions']=len(case['metrics']);case['status']='fused' if case['metrics'] else 'fallback'
                case['timeline_matches_baseline']=case['result']['frames']==case['baseline']['frames'] and case['result']['durations']==case['baseline']['durations']
                case['dimensions_match_baseline']=case['result']['size']==case['baseline']['size']
                case['visible_change']=case['result']['frame_hashes']!=case['baseline']['frame_hashes']
                if not case['metrics']:case['reason']='template_has_no_expression_rig' if not policy['supported_regions'] else 'source_face_unavailable'
                if case['source_prepare_calls']>count:raise ValueError('source inference repeated within one generation')
            except Exception as exc:
                case['status']='failed';case['error']=type(exc).__name__+': '+str(exc)[:240]
            report['cases'].append(case)
            print(tid,metadata['name'],sample,policy['mode'],case['status'],case.get('render_ms'),flush=True)
            (a.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    report['status']='completed';report['peak_rss_mib']=round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/(1048576 if sys.platform=='darwin' else 1024),1)
    from collections import Counter
    report['counts']=dict(Counter(c['status'] for c in report['cases']));report['timeline_mismatches']=sum(c.get('timeline_matches_baseline') is False for c in report['cases']);report['dimension_mismatches']=sum(c.get('dimensions_match_baseline') is False for c in report['cases'])
    (a.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));rt.close();print('DONE',report['counts'],flush=True)

if __name__=='__main__':main()
