#!/usr/bin/env python3
"""Render reviewed CPU fusion fixtures privately and verify their fixed pixels.

PYTHONPATH=backend/meme-generator .venv/bin/python tools/qa/cpu_fusion.py \
 --batch backend/meme-generator/meme_generator/features/template_batches/20261027-cpu-fusion-*.json \
 --photo /private/head.png --model /private/face_landmarker-v1.task \
 --state /tmp/fusion-qa --output /private/fusion-results

Never commit the photo, outputs, or a directory containing private inputs.
"""
import argparse,base64,hashlib,json,os,statistics,time
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image,ImageDraw


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--batch',type=Path,nargs='+',required=True);parser.add_argument('--photo',type=Path,required=True);parser.add_argument('--model',type=Path,required=True);parser.add_argument('--model-site',type=Path);parser.add_argument('--state',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--key',action='append');parser.add_argument('--repeat',type=int,default=1)
    a=parser.parse_args()
    if not 1<=a.repeat<=20:parser.error('repeat must be 1..20')
    os.environ['GENSTICKER_STATE_DIR']=str(a.state.resolve());os.environ['GENSTICKER_FACE_LANDMARK_MODEL']=str(a.model.resolve())
    if a.model_site:os.environ['GENSTICKER_FUSION_SITE']=str(a.model_site.resolve())
    from meme_generator.features import face_fusion
    from meme_generator.features.declarative import TemplateSpec,render
    from meme_generator.features.element_templates import validate_elements
    from meme_generator.features.face_slot import removal_mask
    from meme_generator.features.store import root
    assets=root()/'template_assets';assets.mkdir(exist_ok=True);a.output.mkdir(parents=True,exist_ok=True,mode=0o700)
    items=[]
    for path in a.batch:
        batch=json.loads(path.read_text());items.extend(batch['templates'])
        for digest,encoded in batch['assets'].items():
            raw=base64.b64decode(encoded,validate=True)
            if hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('asset checksum mismatch')
            (assets/(digest+('.gif' if raw.startswith(b'GIF') else '.png'))).write_bytes(raw)
    photo=Image.open(a.photo).convert('RGBA');portrait=face_fusion.prepare(photo)
    if portrait is None:raise ValueError('QA requires a detectable portrait; no fallback counted as fusion')
    results=[]
    try:
        for item in items:
            if a.key and item['key'] not in a.key:continue
            validate_elements(item['spec'],item['metadata']);spec=TemplateSpec.model_validate(item['spec']);error=0
            for frame in spec.frames:
                with Image.open(assets/(frame.asset+'.'+frame.asset_format)) as image:
                    image.seek(frame.source_index);original=Image.alpha_composite(Image.new('RGBA',image.size,spec.background),image.convert('RGBA'))
                mask=removal_mask(original.size,frame.layers);draw=ImageDraw.Draw(mask)
                for layer in frame.layers:
                    if layer.type=='text':x,y,w,h=layer.box;draw.rectangle((x,y,x+w-1,y+h-1),fill=255)
                static=TemplateSpec(width=spec.width,height=spec.height,layers=frame.layers,defaults=spec.defaults,background_prepared=True)
                out=render(static,[photo],spec.defaults,_base=original,_transparent=True,_return_image=True,_fusion_inputs={0:portrait})
                fixed=np.asarray(mask)==0
                if fixed.any():error=max(error,int(np.abs(np.asarray(out).astype(int)-np.asarray(original).astype(int))[fixed].max()))
            if error:raise ValueError(item['key']+': fixed pixels changed')
            timings=[]
            for _ in range(a.repeat):
                t=time.perf_counter();raw=render(spec,[photo],spec.defaults).getvalue();timings.append((time.perf_counter()-t)*1000)
            suffix='gif' if raw.startswith(b'GIF') else 'png';(a.output/(item['key']+'.'+suffix)).write_bytes(raw)
            with Image.open(BytesIO(raw)) as image:
                count=getattr(image,'n_frames',1);duration=0
                for i in range(count):image.seek(i);duration+=image.info.get('duration',100)
            if len(spec.frames)>1 and duration!=sum(f.duration_ms for f in spec.frames):raise ValueError('loop timing changed')
            results.append({'key':item['key'],'frames':count,'checked_frames':len(spec.frames),'duration_ms':duration,'fixed_pixel_max_error':error,'bytes':len(raw),'samples':a.repeat,'median_ms':round(statistics.median(timings),1),'maximum_ms':round(max(timings),1)})
        (a.output/'report.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
        print(json.dumps({'templates':len(results),'checked_frames':sum(r['checked_frames'] for r in results),'fixed_pixels':'unchanged','report':str((a.output/'report.json').resolve())}))
    finally:face_fusion.close()


if __name__=='__main__':main()
