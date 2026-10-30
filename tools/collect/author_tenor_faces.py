"""Measured cat-face rigs + existing bounded CPU expression drivers.

Private authoring only. Explicit human-measured eyes/support and authored AU
curves are not automatic cat landmark/expression estimates. Never publishes.
"""
import os
for option in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','VECLIB_MAXIMUM_THREADS']:
    os.environ[option]='1'
import argparse
import copy
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
import sys
import time

import cv2
import numpy as np
from PIL import Image, ImageDraw

REPO=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(REPO/'backend/meme-generator'),str(REPO/'tools/qa')]
from meme_generator.features.declarative import TemplateSpec, render
from meme_generator.features.element_templates import fingerprint
from meme_generator.features.expression_driver import AU_ORDER, MODEL_SHA256
from meme_generator.features.search_terms import keywords
from meme_generator.features.storage import asset_refs
from author_expression_library import canonical


def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');temporary.replace(path)


def source_adoptions(directory):
    path=directory/'source_adoptions.json'
    if not path.exists():return {},set()
    value=json.loads(path.read_text());adopted=value.get('adopted',value)
    retired=value.get('retired_source_ids',[]) if 'adopted' in value else []
    if (not isinstance(adopted,dict) or not isinstance(retired,list)
            or any(not re.fullmatch(r'\d{1,24}',str(k)) or not isinstance(v,str)
                   or not re.fullmatch(r'tenor_face_[a-f0-9]{24}',v) for k,v in adopted.items())
            or any(not re.fullmatch(r'\d{1,24}',str(k)) for k in retired)):
        raise ValueError('invalid measured-source adoption')
    return adopted,set(map(str,retired))


def actions(brief,index):
    if brief.get('au_keys'):
        times=[k['frame'] for k in brief['au_keys']]
        states=np.asarray([k['aus'] for k in brief['au_keys']],dtype='float32')
        if states.shape!=(len(times),17) or not np.isfinite(states).all() or np.any((states<0)|(states>1)):
            raise ValueError('invalid authored AU states')
        return [round(float(np.interp(index,times,states[:,i]))/.05)*.05 for i in range(17)]
    keys=np.asarray(brief['action_keys'],dtype='float32')
    amount=float(np.interp(index,keys[:,0],keys[:,1]));kind=brief['action']
    au={}
    if kind=='body':au={}
    elif kind=='surprise':au={1:.15,2:.2,5:.35}
    elif kind=='blink':au={12:.15,45:.95*amount}
    elif kind=='squint':au={4:.4*amount,7:.4*amount,45:.8*amount}
    elif kind=='smile':au={6:.5,12:.8,45:.65}
    elif kind=='closed':au={4:.15,12:.2,45:.9}
    elif kind=='stare':au={4:.18,7:.15}
    elif kind=='angry':au={4:.5+.25*amount,7:.3,23:.15,45:.15}
    elif kind in {'laugh','laugh-open'}:
        au={6:.5*amount,12:.8*amount,25:.55*amount,26:.45*amount,45:.75*amount}
    elif kind=='scream':au={1:.2,5:.25,20:.25,25:.75*amount,26:.65*amount}
    else:raise ValueError('unsupported authored action')
    # Quantized, repeated action states are reused by the request-local cache.
    return [round(float(au.get(k,0))/.05)*.05 for k in AU_ORDER]


def track(frames,brief):
    """Offline optical-flow proposal; every resulting support is shown for review."""
    x,y,w,h=brief['box'];height,width=frames[0].shape[:2]
    original=Image.new('L',(width,height));draw=ImageDraw.Draw(original)
    draw.ellipse((x,y,x+w-1,y+h-1),fill=255)
    support=np.array(original);matrix=np.eye(3,dtype='float32')
    base=np.array(brief['eyes'],dtype='float32');rows=[]
    for i,frame in enumerate(frames):
        keys=brief.get('pose_keys')
        if keys:
            if keys[0]['frame']!=0 or keys[-1]['frame']!=len(frames)-1:
                raise ValueError('measured pose keys must cover the complete loop')
            times=np.array([k['frame'] for k in keys]);values=np.array([k['eyes'] for k in keys])
            target=np.array([[np.interp(i,times,values[:,a,b]) for b in range(2)] for a in range(2)],np.float32)
            before=base[1]-base[0];after=target[1]-target[0]
            scale=np.linalg.norm(after)/np.linalg.norm(before)
            angle=np.arctan2(after[1],after[0])-np.arctan2(before[1],before[0])
            c,s=np.cos(angle)*scale,np.sin(angle)*scale
            matrix=np.eye(3,dtype='float32');matrix[:2,:2]=[[c,-s],[s,c]]
            matrix[:2,2]=target.mean(axis=0)-matrix[:2,:2]@base.mean(axis=0)
        elif i:
            before=cv2.cvtColor(frames[i-1],cv2.COLOR_RGB2GRAY)
            after=cv2.cvtColor(frame,cv2.COLOR_RGB2GRAY)
            mask=cv2.warpAffine(support,matrix[:2],(width,height))
            points=cv2.goodFeaturesToTrack(before,180,.01,4,mask=mask)
            if points is None or len(points)<8:raise ValueError('insufficient measured tracking features')
            forward,status,_=cv2.calcOpticalFlowPyrLK(before,after,points,None,winSize=(21,21),maxLevel=3)
            back,reverse,_=cv2.calcOpticalFlowPyrLK(after,before,forward,None,winSize=(21,21),maxLevel=3)
            valid=(status.ravel()>0)&(reverse.ravel()>0)&(np.linalg.norm(points-back,axis=2).ravel()<2)
            if valid.sum()<6:raise ValueError('tracking consistency failed; manual keyframe needed')
            step,inliers=cv2.estimateAffinePartial2D(points[valid],forward[valid],method=cv2.RANSAC,ransacReprojThreshold=2)
            if step is None or inliers.mean()<.45:raise ValueError('head pose proposal unreliable')
            scale=float(np.linalg.norm(step[:,0]));angle=float(np.arctan2(step[1,0],step[0,0]))
            if not .8<scale<1.25 or abs(angle)>.35:raise ValueError('source cut/large pose needs manual tracking')
            affine=np.eye(3);affine[:2]=step;matrix=(affine@matrix).astype('float32')
        mask=cv2.warpAffine(support,matrix[:2],(width,height),flags=cv2.INTER_NEAREST)
        if np.count_nonzero(mask)<.75*np.count_nonzero(support)*np.linalg.det(matrix[:2,:2]):
            raise ValueError('face leaves canvas; cannot recover unseen profile')
        if brief.get('protect_polygons'):
            protected=Image.fromarray(mask);draw=ImageDraw.Draw(protected)
            for polygon in brief['protect_polygons']:draw.polygon([tuple(p) for p in polygon],fill=0)
            mask=np.array(protected)
        eyes=base@matrix[:2,:2].T+matrix[:2,2]
        rows.append((mask,eyes,matrix.copy()))
    return rows


def template_keywords(metadata,brief,row):
    aliases={
        'surprise':['瞪眼','睁眼','惊讶','吃惊','震惊','抬眉','凝视'],
        'blink':['眨眼','闭眼','眯眼','盯着看','凝视'],
        'smile':['微笑','开心','笑','坏笑','憋笑'],
        'laugh':['大笑','狂笑','爆笑','哈哈','哈哈哈','笑死','笑到肚子疼'],
        'closed':['闭眼','摇头','拒绝','不愿意','不同意'],
        'angry':['生气','愤怒','不爽','生闷气','气鼓鼓','郁闷','闷闷不乐'],
        'stare':['无语','凝视','盯着','沉默','不说话'],
        'scream':['尖叫','惊叫','惊吓','叫喊','张嘴','大叫','呐喊','嚎叫'],
    }
    scene_aliases={
        '跳舞':['尬舞','蹦迪','摇摆','扭动','热舞','dance','dancing','party'],
        '歪头':['好奇','疑惑','问号','什么情况','歪脑袋','tilt','confused'],
        '发呆':['愣住','放空','呆住','呆滞','走神','bored'],
        '害羞':['羞涩','脸红','可爱','撒娇','萌','shy','cute'],
        '探头':['张望','偷看','观察','看看','瞧','好奇','peek'],
        '哈欠':['困了','犯困','想睡觉','睡意','累了','yawn','sleepy'],
        '不高兴':['不开心','烦躁','郁闷','恼火','不爽','angry','grumpy'],
        '咆哮':['怒吼','吼叫','愤怒','生气','尖叫','嚎叫'],
        '警告':['别过来','威胁','拿枪','枪口','小心','别惹我','gun','warning'],
    }
    extra=[term for word,terms in scene_aliases.items() if word in brief['name'] for term in terms]
    source_terms=[x.strip()[:60] for x in row.get('source_tags',[]) if isinstance(x,str) and x.strip()]
    return list(dict.fromkeys(keywords(metadata)+aliases.get(brief['action'],[])+extra+source_terms))[:128]


def build(directory,brief,row,neutral):
    asset_dir=directory/'state/features/template_assets';asset_dir.mkdir(parents=True,exist_ok=True)
    def asset(image):
        output=BytesIO();image.save(output,'PNG');raw=output.getvalue();digest=hashlib.sha256(raw).hexdigest()
        (asset_dir/(digest+'.png')).write_bytes(raw);return digest
    with Image.open(row['path']) as source:
        frames=[]
        for i in range(source.n_frames):source.seek(i);frames.append(np.array(source.convert('RGB')))
    transforms=track(frames,brief)
    raw=Path(row['path']).read_bytes();source_hash=hashlib.sha256(raw).hexdigest()
    (asset_dir/(source_hash+'.gif')).write_bytes(raw)
    spec_frames=[];geometry=[]
    for i,(rgb,(mask,eyes,matrix)) in enumerate(zip(frames,transforms)):
        # Remove measured source features rather than flattening the entire
        # face plate. Fur between/around them remains available for blending.
        distance=np.linalg.norm(eyes[1]-eyes[0])
        erasure=Image.new('L',(rgb.shape[1],rgb.shape[0]));ink=ImageDraw.Draw(erasure)
        for eye in eyes:
            rx,ry=distance*.36,distance*.29
            ink.ellipse((eye[0]-rx,eye[1]-ry,eye[0]+rx,eye[1]+ry),fill=255)
        mouth=np.array(brief['mouth'],np.float32)@matrix[:2,:2].T+matrix[:2,2]
        center=(eyes.mean(axis=0)+mouth)*.5
        rx=distance*(.56 if 'scream' in brief['action'] or 'laugh' in brief['action'] else .46)
        ry=max(distance*.4,abs(mouth[1]-center[1])+distance*.23)
        lower=.55 if brief['action']=='scream' else .32
        ink.ellipse((center[0]-rx,center[1]-ry,center[0]+rx,mouth[1]+distance*lower),fill=255)
        erase=np.minimum(np.array(erasure),mask)
        clean=cv2.inpaint(rgb,erase,3,cv2.INPAINT_TELEA)
        ys,xs=np.where(mask>0);x,y=int(xs.min()),int(ys.min());w,h=int(xs.max()-x+1),int(ys.max()-y+1)
        local_mask=Image.fromarray(mask[y:y+h,x:x+w])
        patch=Image.fromarray(clean[y:y+h,x:x+w]).convert('RGBA');patch.putalpha(Image.fromarray(erase[y:y+h,x:x+w]))
        delta=eyes[1]-eyes[0];distance=np.linalg.norm(delta);u=delta/distance;v=np.array([-u[1],u[0]])
        points=(neutral*distance)@np.stack([u,v],axis=1).T+eyes.mean(axis=0)
        recipe={'method':'cpu-expression-ab-v1','mode':'A','domain':'animal','points':points.tolist(),
            'reference_asset':source_hash,'reference_format':'gif','reference_index':i,
            'base_asset':asset(Image.fromarray(clean)),'mask_asset':asset(Image.fromarray(mask)),
            'driver':{'method':'ganimation-emotionnet-v1','aus':actions(brief,i)}}
        face={'type':'face','slot':0,'box':[x,y,w,h],'fit':'cover','tone':'original','feather':2,
              'mask_asset':asset(local_mask),'expression':recipe}
        spec_frames.append({'asset':source_hash,'asset_format':'gif','source_index':i,
            'duration_ms':row['durations'][i],'layers':[{'type':'asset','box':[x,y,w,h],'value':asset(patch)},face]})
        geometry.append([{'type':'face','slot':0,'box':[x,y,w,h],'eyes':eyes.tolist(),'affine':matrix[:2].tolist()}])
    primary=TemplateSpec.model_validate({'width':row['canvas'][0],'height':row['canvas'][1],
                        'frames':spec_frames,'defaults':[]}).model_dump()
    variants={}
    comparison_methods=set(brief.get('render_methods',['direct','geometry','gan']))|{'gan'}
    for method,label in [('direct','面部融合，保留照片表情'),('geometry','轻微几何驱动'),('gan','GANimation 全脸小模型'),('hybrid','GAN 嘴部 + 几何眼部')]:
        if method not in comparison_methods:continue
        spec=copy.deepcopy(primary)
        for frame in spec['frames']:
            for layer in frame['layers']:
                if layer['type']!='face':continue
                if method=='direct':
                    layer['expression']['driver']={'method':'geometry-v1','aus':[0]*17}
                elif method=='geometry':layer['expression']['driver']['method']=brief.get('geometry_method','geometry-v1')
                elif method=='hybrid':layer['expression']['driver']['method']='ganimation-mouth-eye-v3'
                if method=='gan' and brief['action']=='surprise':
                    aus=layer['expression']['driver']['aus']
                    for action,maximum in [(1,.2),(2,.25),(5,.35)]:
                        aus[AU_ORDER.index(action)]=min(aus[AU_ORDER.index(action)],maximum)
        spec=TemplateSpec.model_validate(spec).model_dump()
        variants[method]={'label':label,'spec':spec,'spec_sha256':fingerprint(spec)}
    recommended=brief.get('recommended_method','geometry' if brief['action'] in {'body','surprise','angry','blink','closed','stare'} else 'gan')
    if recommended not in variants:raise ValueError('recommended method was not rendered')
    primary=copy.deepcopy(variants[recommended]['spec'])
    outputs=[];timings=[];media=directory/'media';media.mkdir(exist_ok=True)
    for sample in ['S03','S17','S29']:
        photo=Image.open(directory.parent/'fusion-smallmodels-20261028/portraits'/(sample+'.png')).convert('RGBA')
        for method,variant in variants.items():
            cache={};start=time.monotonic()
            data=render(variant['spec'],[photo],[],_fusion_inputs=cache).getvalue()
            elapsed=round(time.monotonic()-start,3);timings.append(elapsed)
            stats=cache.get('expression_stats',[])
            if len(stats)!=len(frames) or not all(s.get('applied') for s in stats):
                raise ValueError('expression driver fell back; not counted as fused output')
            path=media/(row['key']+'-'+sample+'-'+method+'.gif');path.write_bytes(data)
            with Image.open(path) as image:
                durations=[]
                for index in range(image.n_frames):image.seek(index);image.load();durations.append(image.info.get('duration',100))
                if image.n_frames<2 or image.size!=tuple(row['canvas']) or sum(durations)!=row['duration_ms'] or image.info.get('loop')!=0:
                    raise ValueError('actual animation output lost canvas/full timeline')
            outputs.append({'sample':sample+'-'+method,'portrait':sample,'method':method,'file':path.name,
                'frames':len(durations),'duration_ms':sum(durations),'bytes':len(data),'seconds':elapsed,
                'expression_applied_frames':len(stats),'unique_action_states':sum(s.get('driver_state_generated',False) for s in stats)})
    metadata={'name':brief['name'],'keywords':[],'tags':['猫咪','动图',brief['action'],'头像替换','表情融合'],
        'origin':'tenor','source_url':row['source_url'],'source_image_url':row['image_url'],
        'source_author':row.get('source_author'),'source_shares':row.get('source_shares'),
        'license':'unverified','source_use':'explicit-user-request-private-reference',
        'min_images':1,'max_images':1,'min_texts':0,'max_texts':0,'default_texts':[],
        'input_hint':'换入猫脸内部，保留猫耳、身体、原字幕与场景；离线手工表情曲线，待审核。',
        'caption_inventory':brief.get('caption_inventory',[]),
        'review':{'visual_status':'pending-human-review'},'model_sha256':MODEL_SHA256,
        'expression_policy':{'visual_status':'pending-user-review','disposition':'expression','authored_actions':True}}
    metadata['keywords']=template_keywords(metadata,brief,row)
    result={**row,'name':brief['name'],'status':'draft','publication_status':'not-published',
        'image_slots':1,'text_slots':0,'defaults':[],'caption_inventory':brief.get('caption_inventory',[]),
        'spec':primary,'spec_sha256':fingerprint(primary),'variants':variants,'outputs':outputs,
        'asset_hashes':sorted(asset_refs(primary)),
        'metadata':metadata,'geometry':geometry,'brief':brief,'seconds':round(sum(timings),2),
        'recommended_method':recommended,
        'blocked_methods':brief.get('blocked_methods',{}),
        'limitations':['动作曲线为离线手工标定，非自动动物表情识别','不生成不可见侧脸，不承诺眼神方向、伸舌或新牙齿还原']}
    save(directory/'drafts'/(row['key']+'.json'),result)
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--directory',type=Path,required=True)
    parser.add_argument('--limit',type=int,default=100);args=parser.parse_args();directory=args.directory.resolve()
    os.environ['GENSTICKER_STATE_DIR']=str(directory/'state');os.environ['GENSTICKER_BOOTSTRAP_SEEDS']='0'
    os.environ['GENSTICKER_FUSION_SITE']=str(REPO/'artifacts/cpu-fusion-20261027/landmark-venv/lib/python3.12/site-packages')
    os.environ['GENSTICKER_EXPRESSION_DRIVER_MODEL']=str(directory.parent/'fusion-selected-20261029/reproduced-driver.onnx')
    for name in ['face_landmarker-v1.task','selfie_multiclass_256x256.tflite']:
        dest=directory/'state/features/models'/name;dest.parent.mkdir(parents=True,exist_ok=True)
        if not dest.exists():dest.symlink_to(directory.parent/'fusion-review-20261028/state/features/models'/name)
    cv2.setNumThreads(1)
    neutral=canonical(directory.parent/'fusion-lab-20261027/models/canonical_face_model.obj')
    rows={r['source_id']:r for r in json.loads((directory/'inventory.json').read_text()) if r['status']=='source-ready'}
    # Exact-byte deduplication can retain another public ID for the same GIF.
    # Preserve an existing measured brief's provenance without duplicating keys.
    for path in (directory/'downloads').glob('*.json'):
        row=json.loads(path.read_text())
        if row['status']=='source-ready':rows.setdefault(row['source_id'],row)
    count=0
    adoption,retired=source_adoptions(directory)
    for index,brief in enumerate(json.loads((directory/'briefs.json').read_text())):
        if count>=args.limit:break
        if brief['source_id'] in retired:continue
        if brief['source_id'] not in rows:
            print(json.dumps({'source_id':brief['source_id'],'status':'held','reason':'source unavailable'},ensure_ascii=False),flush=True)
            continue
        row={**rows[brief['source_id']],'index':index}
        row['key']=adoption.get(brief['source_id'],row['key'])
        dest=directory/'drafts'/(row['key']+'.json')
        if dest.exists():continue
        started=time.monotonic()
        try:
            result=build(directory,brief,row,neutral);count+=1
            print(json.dumps({'name':brief['name'],'status':'draft','outputs':len(result['outputs']),
                'seconds':round(time.monotonic()-started,2)},ensure_ascii=False),flush=True)
        except Exception as error:
            save(directory/'holds'/(row['key']+'.json'),{'source':row,'brief':brief,'reason':str(error)})
            print(json.dumps({'name':brief['name'],'status':'held','reason':str(error)},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
