"""Complete missing timeline rigs offline, then losslessly compact public assets."""
import argparse,base64,copy,importlib.util,json,os
from pathlib import Path
import numpy as np
from PIL import Image,ImageOps
from meme_generator.features.declarative import TemplateSpec
from meme_generator.features.storage import asset_refs
from meme_generator.features.store import root
from meme_generator.features import expression_runtime as rt


def main():
    p=argparse.ArgumentParser();p.add_argument('--compiled',type=Path,required=True);p.add_argument('--snapshot',type=Path,required=True);p.add_argument('--canonical',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    loader=importlib.util.spec_from_file_location('author',Path(__file__).with_name('author_expression_library.py'));author=importlib.util.module_from_spec(loader);loader.loader.exec_module(author)
    items=json.loads((a.compiled/'compiled.json').read_text());rows=json.loads(a.snapshot.read_text())['image_templates'];oldrefs=set().union(*(asset_refs(r['spec'])|asset_refs(r['metadata']) for r in rows));neutral=author.canonical(a.canonical)
    if not rt.warmup():raise RuntimeError('offline models unavailable')
    fills=[];compact_verified=0;crop_repairs=[]
    for item in items:
        policy=item['metadata']['expression_policy'];spec=item['spec'];filled=0
        repaired=0
        if spec:
            for f in spec.get('frames') or [spec]:
                for layer in f['layers']:
                    if layer['type']!='face' or layer.get('expression'):continue
                    digest=f.get('reference_asset') or f.get('asset') or spec.get('reference_asset')
                    if not digest:continue
                    image=author.read_asset(digest,f.get('source_index',0));base=image.convert('RGBA')
                    for l in f['layers']:
                        if l['type']=='face':break
                        if l['type']=='asset':
                            bx,by,bw,bh=l['box'];base.alpha_composite(ImageOps.contain(author.read_asset(l['value'],mode='RGBA'),(bw,bh)),(bx,by))
                    recipe,reason=author.make_recipe(image,layer,f['layers'],item['metadata'],policy['mode'],neutral,base)
                    if recipe:layer['expression']=recipe;repaired+=1
            if repaired:
                policy['supported_regions']+=repaired;policy['reasons'].append('source-slot-crop-rigs:'+str(repaired));crop_repairs.append({'key':item['key'],'regions':repaired})
        if spec and len(spec.get('frames',[]))>1:
            frames=spec['frames']
            slots={l['slot'] for f in frames for l in f['layers'] if l['type']=='face'}
            for slot in slots:
                candidates=[(i,l) for i,f in enumerate(frames) for l in f['layers'] if l['type']=='face' and l['slot']==slot and l.get('expression')]
                if not candidates:continue
                for i,f in enumerate(frames):
                    for layer in f['layers']:
                        if layer['type']!='face' or layer['slot']!=slot or layer.get('expression'):continue
                        left=max((c for c in candidates if c[0]<i),default=candidates[0],key=lambda c:c[0]);right=min((c for c in candidates if c[0]>i),default=candidates[-1],key=lambda c:c[0])
                        x,y,w,h=layer['box']
                        def transformed(candidate):
                            _,other=candidate;ox,oy,ow,oh=other['box'];points=np.array(other['expression']['points'],np.float32)
                            return (points-[ox,oy])*[w/ow,h/oh]+[x,y]
                        weight=np.clip((i-left[0])/max(1,right[0]-left[0]),0,1);points=(transformed(left)*(1-weight)+transformed(right)*weight).astype('float32')
                        digest=f.get('reference_asset') or f['asset'];image=author.read_asset(digest,f.get('source_index',0));base=image.convert('RGBA')
                        for l in f['layers']:
                            if l['type']=='face':break
                            if l['type']=='asset':
                                bx,by,bw,bh=l['box'];base.alpha_composite(ImageOps.contain(author.read_asset(l['value'],mode='RGBA'),(bw,bh)),(bx,by))
                        recipe,reason=author.make_recipe(image,layer,f['layers'],item['metadata'],policy['mode'],neutral,base,points_override=points)
                        if recipe:layer['expression']=recipe;filled+=1
            if filled:
                policy['supported_regions']+=filled;policy['reasons'].append('offline-interpolated-source-rigs:'+str(filled));fills.append({'key':item['key'],'filled_regions':filled})
        # Full original GIF frames remain in their existing compressed source.
        # The clean patch is lossless; reconstructing base is checked byte-for-byte.
        frames=(spec.get('frames') or [spec]) if spec else []
        recipes=[(l['expression'],f) for f in frames for l in f['layers'] if l.get('expression')]
        if policy.get('recipe'):recipes.append((policy['recipe'],None))
        for recipe,f in recipes:
            original=author.read_asset(recipe['reference_asset']);base=author.read_asset(recipe['base_asset']);before=np.array(base);original_pixels=np.array(original)
            yy,xx=np.where(np.any(before!=original_pixels,axis=2))
            box=(int(xx.min()),int(yy.min()),int(xx.max())+1,int(yy.max())+1) if len(xx) else (0,0,1,1)
            x0,y0,x1,y1=box;patch=base.crop(box);reconstructed=original_pixels.copy();reconstructed[y0:y1,x0:x1]=np.array(patch)
            if not np.array_equal(reconstructed,before):raise ValueError('clean patch compaction changed pixels')
            recipe['base_box']=[x0,y0,x1-x0,y1-y0];recipe['base_asset']=author.png_asset(patch);compact_verified+=1
            if f is not None:
                digest=f.get('reference_asset') or f.get('asset') or spec['reference_asset'];index=f.get('source_index',0)
                raw=author.read_asset(digest,index)
                if not np.array_equal(np.array(raw),original_pixels):raise ValueError('original timeline compaction changed pixels')
                recipe['reference_asset']=digest;recipe['reference_format']=f.get('asset_format','png');recipe['reference_index']=index
        if spec:item['spec']=TemplateSpec.model_validate(spec).model_dump()
    a.output.mkdir(parents=True,exist_ok=True)
    for p in a.output.glob('20261027-ab-*.json'):p.unlink()
    current=[];assets={};size=0;batches=[]
    for item in items:
        refs=(asset_refs(item['spec'])|asset_refs(item['metadata']))-oldrefs
        fresh={d:base64.b64encode((root()/'template_assets'/(d+'.png')).read_bytes()).decode() for d in refs if d not in assets}
        incoming=len(json.dumps(item).encode())+sum(len(v) for v in fresh.values())
        if current and (len(current)>=100 or size+incoming>30*1024**2):
            batches.append({'format':'gensticker-expression-ab-v1','templates':current,'assets':assets});current=[];assets={};size=0
            fresh={d:base64.b64encode((root()/'template_assets'/(d+'.png')).read_bytes()).decode() for d in refs}
            incoming=len(json.dumps(item).encode())+sum(len(v) for v in fresh.values())
        current.append(item);assets.update(fresh);size+=incoming
    if current:batches.append({'format':'gensticker-expression-ab-v1','templates':current,'assets':assets})
    for i,batch in enumerate(batches):(a.output/f'20261027-ab-{i+1:02}.json').write_text(json.dumps(batch,ensure_ascii=False,separators=(',',':')))
    (a.output/'compiled.json').write_text(json.dumps(items,ensure_ascii=False))
    proof={'source_slot_crop_repairs':crop_repairs,'lossless_clean_patch_checks':compact_verified,'timeline_fills':fills,'filled_regions':sum(x['filled_regions'] for x in fills),'batch_count':len(batches),'batch_bytes':sum(p.stat().st_size for p in a.output.glob('20261027-ab-*.json')),'visual_quality_approved':False}
    (a.output/'proof.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2));print(json.dumps(proof),flush=True);rt.close()

if __name__=='__main__':main()
