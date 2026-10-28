#!/usr/bin/env python3
"""Compile measured, source-only region corrections; never change A/B math.

Plans contain source-pixel geometry, not test portraits. Run in isolated state
with the public source assets installed. Only explicitly listed keys are edited.
"""
import argparse, base64, copy, hashlib, importlib.util, json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw
from meme_generator.features import expression_math as m
from meme_generator.features.declarative import TemplateSpec
from meme_generator.features.storage import asset_refs
from meme_generator.features.store import root


def semantic_points(neutral, anchors):
    """Smoothly map a canonical rig to measured eyes/nose/mouth/contour anchors."""
    controls = np.array([(neutral[33]+neutral[133])/2,
                         (neutral[362]+neutral[263])/2, neutral[1],
                         neutral[m.OUTER].mean(0), neutral[152], neutral[10],
                         neutral[234], neutral[454]], dtype='float64')
    target = np.array([anchors[k] for k in
                       ['left_eye','right_eye','nose','mouth','chin','top','left','right']], dtype='float64')
    def radial(a, b):
        r2 = np.sum((a[:, None]-b[None, :])**2, axis=2)
        return r2*np.log(np.maximum(r2, 1e-12))
    affine = np.column_stack([np.ones(len(controls)), controls])
    system = np.block([[radial(controls, controls), affine],
                       [affine.T, np.zeros((3, 3))]])
    weights = np.linalg.solve(system, np.vstack([target, np.zeros((3, 2))]))
    return (np.column_stack([radial(neutral, controls), np.ones(len(neutral)), neutral]) @ weights).astype('float32')


def authored_mask(size, points, plan, offset):
    image = Image.new('L', size)
    draw = ImageDraw.Draw(image)
    polygon = plan.get('support')
    if polygon:
        draw.polygon([(x+offset[0], y+offset[1]) for x,y in polygon], fill=255)
    else:
        draw.polygon([tuple(p) for p in points[m.OVAL]], fill=255)
    for polygon in plan.get('protect', []):
        draw.polygon([(x+offset[0], y+offset[1]) for x,y in polygon], fill=0)
    return image


def compile_repairs(snapshot, plans, review, canonical, author):
    rows = {r['key']:r for r in snapshot['image_templates']}
    neutral = author.canonical(canonical)
    updates, proof = [], []
    for decision in review:
        if decision['rating'] not in {'需调整','不需要'}:
            continue
        row = rows[decision['key']]
        item = copy.deepcopy(row)
        policy = item['metadata']['expression_policy']
        spec = item['spec']
        plan = plans.get(row['key'])
        direct = decision['rating']=='不需要' or (plan or {}).get('action')=='paste'
        record = {'key':row['key'], 'id':decision['id'], 'rating':decision['rating'],
                  'action':'paste' if direct else 'region-repair', 'frames':[]}
        if direct:
            policy.pop('recipe', None)
            policy['supported_regions'] = 0
            policy['disposition'] = 'paste'
            policy['reasons'] = ['user-reviewed:direct-paste' if decision['rating']=='不需要'
                                 else 'review-correction:uploaded-image-is-a-prop']
            if spec:
                for frame in spec.get('frames') or [spec]:
                    for layer in frame['layers']:
                        if layer['type']=='face':
                            layer['expression'] = None
                            layer['fusion'] = None
        else:
            if not plan or not spec:
                raise ValueError('missing measured region plan: '+row['key'])
            frames = spec.get('frames') or [spec]
            first_layer = next(l for l in frames[0]['layers'] if l['type']=='face')
            first_box = first_layer['box']
            for index, frame in enumerate(frames):
                frame_plan={**plan,**plan.get('frames',{}).get(str(index),{})}
                layer = next(l for l in frame['layers'] if l['type']=='face')
                old_box=layer['box'].copy()
                original = author.read_asset(frame.get('reference_asset') or frame['asset'], frame.get('source_index',0))
                if original.size != (spec['width'], spec['height']):
                    raise ValueError('source canvas mismatch')
                offset = np.array(layer['box'][:2])-first_box[:2] if frame_plan.get('follow_box') else np.zeros(2)
                if frame_plan.get('points')=='existing':
                    points = np.array(layer['expression']['points'], dtype='float32')
                else:
                    anchors = {k:(np.array(v)+offset).tolist() for k,v in frame_plan['anchors'].items()}
                    points = semantic_points(neutral, anchors)
                if roi:=frame_plan.get('mouth_color_roi'):
                    x,y,w,h=roi;crop=np.array(original)[y:y+h,x:x+w].astype(int)
                    colored=((crop[:,:,0]>crop[:,:,1]+frame_plan.get('mouth_red_min',65))&(crop[:,:,0]>crop[:,:,2]+5)&(crop[:,:,0]>150)).astype('uint8')
                    contours,_=cv2.findContours(colored,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
                    viable=[c for c in contours if cv2.contourArea(c)>=2]
                    if viable:
                        mx,my,mw,mh=cv2.boundingRect(max(viable,key=cv2.contourArea))
                        center=np.array([x+mx+mw/2,y+my+mh/2])
                        old_center=points[m.OUTER].mean(0);outer=points[m.OUTER]-old_center
                        outer*=np.array([mw/max(np.ptp(outer[:,0]),1),mh/max(np.ptp(outer[:,1]),1)])
                        points[m.OUTER]=center+outer
                        points[m.INNER]=center+outer*np.array([.8,.75])
                if bounds:=frame_plan.get('mouth_box'):
                    x,y,w,h=bounds;center=np.array([x+w/2,y+h/2])+offset
                    outer=points[m.OUTER]-points[m.OUTER].mean(0)
                    outer*=np.array([w/max(np.ptp(outer[:,0]),1),h/max(np.ptp(outer[:,1]),1)])
                    points[m.OUTER]=center+outer
                    points[m.INNER]=center+outer*np.array([.88,.78])
                mask = authored_mask(original.size, points, frame_plan, offset)
                pixels = np.array(original)
                if frame_plan.get('protect_bangs'):
                    eye_y = min(points[m.L_EYE,1].mean(), points[m.R_EYE,1].mean())
                    yy,xx = np.indices(pixels.shape[:2])
                    # Only measured upper hair is excluded; dark eyes remain editable.
                    hair = (yy < eye_y-1) & (pixels.max(2)<92)
                    values=np.array(mask);values[hair]=0;mask=Image.fromarray(values)
                draw = ImageDraw.Draw(mask)
                for other in frame['layers']:
                    if other['type']=='text':
                        x,y,w,h=other['box'];draw.rectangle((x,y,x+w-1,y+h-1),fill=0)
                for x,y,w,h in frame_plan.get('protect_white_glyphs',[]):
                    crop=pixels[y:y+h,x:x+w];glyph=(crop.min(2)>190).astype('uint8')
                    glyph=cv2.dilate(glyph,np.ones((5,5),np.uint8))
                    values=np.array(mask);values[y:y+h,x:x+w][glyph>0]=0;mask=Image.fromarray(values)
                support = np.array(mask)
                if not support.any():
                    raise ValueError('empty support')
                if 'clean_color_from' in frame_plan:
                    x,y = np.rint(np.array(frame_plan['clean_color_from'])+offset).astype(int)
                    color = np.median(pixels[max(0,y-1):y+2,max(0,x-1):x+2].reshape(-1,3),axis=0)
                    clean=pixels.copy();clean[support>0]=color
                else:
                    removal=np.zeros(support.shape, np.uint8)
                    for group in [m.L_EYE,m.R_EYE,m.L_BROW,m.R_BROW,m.NOSE,m.OUTER]:
                        cv2.fillConvexPoly(removal,cv2.convexHull(np.rint(points[group]).astype('int32')),255)
                    removal=cv2.dilate(removal,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(5,5)))
                    for x,y,w,h in frame_plan.get('erase_features',[]):
                        ox,oy=np.rint(offset).astype(int)
                        cv2.rectangle(removal,(x+ox,y+oy),(x+ox+w-1,y+oy+h-1),255,-1)
                    clean=cv2.inpaint(pixels,np.minimum(removal,support),3,cv2.INPAINT_TELEA)
                # The fallback uses the same complete support and prepared patch.
                yy,xx=np.where(support>0);x0,y0,x1,y1=int(xx.min()),int(yy.min()),int(xx.max())+1,int(yy.max())+1
                box=[x0,y0,x1-x0,y1-y0]
                layer.update(box=box, mask_asset=author.png_asset(mask.crop((x0,y0,x1,y1))),
                             erase_polygon=[], protect_polygons=[], fusion=None,
                             fit='cover', feather=1)
                recipe={'method':m.REVISION, 'mode':policy['mode'], 'domain':frame_plan['domain'],
                        'points':points.tolist(), 'reference_asset':frame.get('reference_asset') or frame['asset'],
                        'reference_format':frame.get('asset_format','png'), 'reference_index':frame.get('source_index',0),
                        'base_box':box, 'base_asset':author.png_asset(Image.fromarray(clean).crop((x0,y0,x1,y1))),
                        'mask_asset':author.png_asset(mask)}
                layer['expression']=recipe
                # Replace the old, inaccurate clean patch too; preserve other layers.
                before=[]
                for other in frame['layers']:
                    if other is layer:break
                    if other['type']=='asset' and other['box']==old_box:before.append(other)
                for other in before:frame['layers'].remove(other)
                patch=Image.fromarray(clean).convert('RGBA').crop((x0,y0,x1,y1))
                patch.putalpha(mask.crop((x0,y0,x1,y1)))
                transparent=np.array(patch);transparent[transparent[:,:,3]==0,:3]=0
                frame['layers'].insert(frame['layers'].index(layer),
                                       {'type':'asset','box':box,'value':author.png_asset(Image.fromarray(transparent))})
                record['frames'].append({'frame':index,'source_index':frame.get('source_index',0),
                                         'support_box':box,'support_pixels':int((support>0).sum()),
                                         'fixed_clean_pixel_max_error':int(np.abs(clean.astype(int)-pixels.astype(int))[support==0].max()) if (support==0).any() else 0})
            policy.update(supported_regions=len(frames), regions=len(frames), disposition='expression',
                          reasons=['review-correction:measured-full-region-and-semantic-anchors'])
            item['spec']=TemplateSpec.model_validate(spec).model_dump()
        policy['calibration']={'date':'2026-10-28','source_rating':decision['rating'],
                               'action':record['action'],'reason':(plan or {}).get('reason','direct-paste-requested')}
        policy['visual_status']='pending-user-review'
        item.update(base_version=row['version'],base_fingerprint=row['fingerprint'],version=row['version']+1)
        item.pop('id',None);item.pop('fingerprint',None)
        updates.append(item);proof.append(record)
    return updates,proof


def main():
    parser=argparse.ArgumentParser()
    for name in ['snapshot','plans','review','canonical','output']:
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    loader=importlib.util.spec_from_file_location('author',Path(__file__).with_name('author_expression_library.py'))
    author=importlib.util.module_from_spec(loader);loader.loader.exec_module(author)
    snapshot=json.loads(args.snapshot.read_text())
    plans=json.loads(args.plans.read_text())['templates']
    review=json.loads(args.review.read_text())
    updates,proof=compile_repairs(snapshot,plans,review,args.canonical,author)
    oldrefs=set().union(*(asset_refs(r['spec'])|asset_refs(r['metadata']) for r in snapshot['image_templates']))
    refs=set().union(*(asset_refs(r['spec'])|asset_refs(r['metadata']) for r in updates))-oldrefs
    assets={d:base64.b64encode((root()/'template_assets'/(d+'.png')).read_bytes()).decode() for d in refs}
    batch={'format':'gensticker-expression-ab-v1','templates':updates,'assets':assets}
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output/'20261028-review-01.json').write_text(json.dumps(batch,ensure_ascii=False,separators=(',',':')))
    (args.output/'compiled.json').write_text(json.dumps(updates,ensure_ascii=False))
    (args.output/'proof.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2))
    print(json.dumps({'updated':len(updates),'new_assets':len(assets),'bytes':(args.output/'20261028-review-01.json').stat().st_size}))


if __name__=='__main__':main()
