"""Verify source assets, full rendered timelines and fixed pixels privately.

This is technical evidence only. It never manufactures visual approval or
changes production. Each source-element candidate still needs human review.
"""
import argparse
from io import BytesIO
import hashlib
import json
import os
from pathlib import Path
import time

import numpy as np
from PIL import Image


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--directory',type=Path,required=True)
    args=parser.parse_args();directory=args.directory.resolve()
    os.environ['GENSTICKER_STATE_DIR']=str(directory/'state')
    os.environ['GENSTICKER_BOOTSTRAP_SEEDS']='0'
    from meme_generator.features.declarative import TemplateSpec,render
    from meme_generator.features.element_templates import fingerprint
    from meme_generator.features.store import root
    from meme_generator.features.face_slot import removal_mask
    outputs=directory/'technical';outputs.mkdir(exist_ok=True)
    with Image.open(directory.parent/'fusion-smallmodels-20261028/portraits/S03.png') as photo:
        portrait=photo.convert('RGBA')
    seen=set();started=time.monotonic();reports=[]
    for path in sorted((directory/'drafts').glob('*.json')):
        row=json.loads(path.read_text())
        if row['status']!='draft':continue
        target=outputs/(row['key']+'.json')
        if target.exists():
            previous=json.loads(target.read_text())
            if previous['spec_sha256']==row['spec_sha256'] and previous.get('audit_revision')==2:
                reports.append(previous);continue
        report={'key':row['key'],'spec_sha256':row['spec_sha256'],'status':'failed','audit_revision':2,
                'human_review':'required','publication':'not-published',
                'fixed_pixel_scope':'outside declared face masks, cleaned-patch alpha and caption boxes, before GIF quantization'}
        try:
            assert fingerprint(row['spec'])==row['spec_sha256'],'recipe changed'
            spec=TemplateSpec.model_validate(row['spec']);checked=0;max_error=0
            for digest in row['asset_hashes']:
                asset=next(iter((root()/'template_assets').glob(digest+'.*')),None)
                assert asset and hashlib.sha256(asset.read_bytes()).hexdigest()==digest,'asset missing/corrupt'
            frames={}
            for frame in spec.frames:
                asset=root()/'template_assets'/(frame.asset+'.'+frame.asset_format)
                if frame.asset not in frames:
                    with Image.open(asset) as source:
                        frames[frame.asset]=[]
                        for i in range(getattr(source,'n_frames',1)):
                            source.seek(i);frames[frame.asset].append(source.convert('RGBA').copy())
                base=frames[frame.asset][frame.source_index]
                support=np.zeros((spec.height,spec.width),dtype=bool)
                for layer in frame.layers:
                    x,y,w,h=layer.box
                    if layer.type=='face':
                        support|=np.asarray(removal_mask(base.size,[layer]))>0
                    elif layer.type=='text':
                        support[y:y+h,x:x+w]=True
                    elif layer.type=='asset':
                        with Image.open(root()/'template_assets'/(layer.value+'.png')) as patch:
                            support[y:y+h,x:x+w]|=np.asarray(patch.convert('RGBA').getchannel('A'))>0
                if frame.layers:
                    single=TemplateSpec(width=spec.width,height=spec.height,defaults=spec.defaults,
                                        background_prepared=True,layers=frame.layers)
                    cache={}
                    result=render(single,[portrait]*row['image_slots'],row['defaults'],
                                  _transparent=True,_base=base,_reference=base,_return_image=True,
                                  _fusion_inputs=cache).convert('RGB')
                    if any(l.type=='face' and l.expression for l in frame.layers):
                        stats=cache.get('expression_stats',[])
                        assert stats and all(s.get('applied') for s in stats),'expression infrastructure fell back'
                    delta=np.abs(np.asarray(result,dtype='int16')-np.asarray(base.convert('RGB'),dtype='int16'))
                    error=int(delta[~support].max()) if np.any(~support) else 0
                    max_error=max(max_error,error)
                checked+=1
            assert max_error==0,'pixels outside declared editable support changed'
            for output in row['outputs']:
                with Image.open(directory/'media'/output['file']) as image:
                    assert image.size==tuple(row['canvas']),'output canvas changed'
                    count=getattr(image,'n_frames',1);duration=0
                    for i in range(count):image.seek(i);image.load();duration+=int(image.info.get('duration',100))
                    assert duration==row['duration_ms'],'full output timing changed'
                    if row['animated']:
                        assert count>1 and image.info.get('loop')==row['loop'],'motion/loop changed'
            if row['image_slots']:
                actual=[(directory/'media'/x['file']).read_bytes() for x in row['outputs'][:3]]
                assert len({hashlib.sha256(x).digest() for x in actual})>1,'distinct portraits produced identical output'
            if row['text_slots']:
                try:render(spec,[portrait]*row['image_slots'],['x'*201]*row['text_slots'])
                except ValueError:pass
                else:raise AssertionError('oversized text did not fail clearly')
            report.update(status='passed',analyzed_frames=checked,protected_pixel_max_error=max_error,
                          decoded_outputs=len(row['outputs']),timing_ms=row['duration_ms'],animated=row['animated'])
        except Exception as error:
            report['reason']=type(error).__name__+': '+str(error)[:300]
        temporary=target.with_suffix('.tmp');temporary.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');temporary.replace(target)
        reports.append(report)
        if len(reports)%50==0:print(json.dumps({'audited':len(reports),'failed':sum(x['status']!='passed' for x in reports),'seconds':round(time.monotonic()-started)}),flush=True)
    summary={'audited':len(reports),'passed':sum(x['status']=='passed' for x in reports),
             'failed':sum(x['status']!='passed' for x in reports),'seconds':round(time.monotonic()-started,2),
             'human_review':'required','publication':'not-published','results':reports}
    (directory/'technical-audit.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k!='results'}),flush=True)


if __name__=='__main__':main()
