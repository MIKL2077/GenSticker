#!/usr/bin/env python3
"""Source-only, per-template calibration after the complete 483-item review.

Coordinates are fractions of ORIGINAL artwork, never an uploaded portrait.
Optical flow propagates measured geometry; explicit keyframes override cuts.
Every emitted frame has its own finite support, clean patch and donor masks.
"""
import argparse,base64,copy,importlib.util,json
from pathlib import Path
import cv2
import numpy as np
from PIL import Image,ImageDraw
from meme_generator.features import expression_math as m
from meme_generator.features.declarative import TemplateSpec
from meme_generator.features.storage import asset_refs
from meme_generator.features.store import root


def load_module(name):
    s=importlib.util.spec_from_file_location(name,Path(__file__).with_name(name+'.py'));v=importlib.util.module_from_spec(s);s.loader.exec_module(v);return v


def geometry(neutral,plan,size):
    w,h=size;b=np.array(plan['box'])*[w,h,w,h];x,y,r,d=b
    eyes=np.array(plan['eyes'])*[w,h];mouth=np.array(plan['mouth'])*[w,h]
    nose=np.array(plan.get('nose',[(eyes[:,0].mean()+mouth[0]/w)/2, (eyes[:,1].mean()/h+mouth[1]/h)/2]))*[w,h] if 'nose' in plan else eyes.mean(0)*.45+mouth*.55
    anchors=dict(left_eye=eyes[0],right_eye=eyes[1],nose=nose,mouth=mouth,
                 top=[(x+r)/2,y],chin=[mouth[0],d],left=[x,(y+d)/2],right=[r,(y+d)/2])
    p=load_module('repair_expression_regions').semantic_points(neutral,anchors)
    # Explicit eye and lip footprints are measured from the source, not inferred
    # from the old (sometimes neck-centred) face box.
    eye_size=plan.get('eye_size',[[.11,.065],[.11,.065]])
    for group,center,sz in zip([m.L_EYE,m.R_EYE],eyes,eye_size):
        local=p[group]-p[group].mean(0);local*=np.array(sz)*[w,h]/np.maximum(np.ptp(local,axis=0),.1);p[group]=center+local
    for group in [m.OUTER,m.INNER]:
        local=p[group]-p[group].mean(0);local*=np.array(plan.get('mouth_size',[.14,.055]))*[w,h]/np.maximum(np.ptp(local,axis=0),.1)
        p[group]=mouth+local*(1 if group==m.OUTER else .72)
    # Iris positions are only used to warp the uploaded eyes; template gaze is
    # carried by source-pixel components, not a fabricated iris position.
    for group,iris in [(m.L_EYE,list(range(468,473))),(m.R_EYE,list(range(473,478)))]:p[iris]=p[group].mean(0)
    return p


def flow_transform(previous,current,mask):
    a=cv2.cvtColor(np.array(previous),cv2.COLOR_RGB2GRAY);b=cv2.cvtColor(np.array(current),cv2.COLOR_RGB2GRAY)
    # Include the immediate head boundary, but exclude moving hands and scenery.
    roi=cv2.dilate(mask,np.ones((9,9),np.uint8));pts=cv2.goodFeaturesToTrack(a,90,.015,3,mask=roi)
    identity=np.array([[1.,0,0],[0,1.,0]])
    if pts is None or len(pts)<4:return identity,'static-insufficient-tracks'
    nxt,status,_=cv2.calcOpticalFlowPyrLK(a,b,pts,None,winSize=(25,25),maxLevel=3)
    back,status2,_=cv2.calcOpticalFlowPyrLK(b,a,nxt,None,winSize=(25,25),maxLevel=3)
    good=(status[:,0]>0)&(status2[:,0]>0)&(np.linalg.norm(back[:,0]-pts[:,0],axis=1)<1.8)
    if good.sum()<4:return identity,'static-rejected-tracks'
    transform,inliers=cv2.estimateAffinePartial2D(pts[good],nxt[good],method=cv2.RANSAC,ransacReprojThreshold=2)
    if transform is None:return identity,'static-no-affine'
    scale=np.linalg.norm(transform[0,:2]);shift=np.linalg.norm(transform[:,2])
    if not .72<scale<1.38 or shift>max(a.shape)*.35 or inliers.sum()<4:return identity,'static-rejected-cut'
    return transform,'source-optical-flow'


def transform_points(p,mat):return p@mat[:,:2].T+mat[:,2]


def support_mask(size,p,plan,transform):
    mask=Image.new('L',size);d=ImageDraw.Draw(mask)
    if plan.get('support'):
        points=transform_points(np.array(plan['support'])*size,transform);d.polygon([tuple(v) for v in points],fill=255)
    else:
        # The measured contour is deliberately convex; cartoon eyes can sit
        # outside a human-shaped oval and must not be left behind.
        pts=p[m.OVAL].copy();pts=np.vstack([pts,p[m.L_EYE],p[m.R_EYE],p[m.OUTER]])
        hull=cv2.convexHull(np.rint(pts).astype('int32')).reshape(-1,2);d.polygon([tuple(v) for v in hull],fill=255)
    for poly in plan.get('protect',[]):
        pts=transform_points(np.array(poly)*size,transform);d.polygon([tuple(v) for v in pts],fill=0)
    return np.array(mask)


def component_mask(size,p,group,mask,padding=1):
    out=np.zeros(mask.shape,np.uint8);cv2.fillConvexPoly(out,cv2.convexHull(np.rint(p[group]).astype('int32')),255)
    radius=max(1,round(m.basis(p)[1]*padding*.055));out=cv2.dilate(out,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(radius*2+1,)*2))
    return np.minimum(out,mask)


def rebuild(row,plan,neutral,author):
    spec=row['spec'];frames=spec.get('frames') or [spec];proof=[];prev=None;states={}
    for i,frame in enumerate(frames):
        original=author.read_asset(frame.get('reference_asset') or frame['asset'],frame.get('source_index',0));rgb=np.array(original)
        frame['asset']=frame.get('reference_asset') or frame['asset']
        faces=[l for l in frame['layers'] if l['type']=='face'];plans=plan.get('faces') or [plan]
        if not faces and plan.get('allow_missing_faces'):
            prev=original;continue
        if len(faces)!=len(plans):raise ValueError('unplanned face count '+str((row['key'],i,len(faces),len(plans))))
        for j,(layer,fp) in enumerate(zip(faces,plans)):
            active={**plan,**fp,**fp.get('keyframes',{}).get(str(i),{})}
            if i==0 or str(i) in fp.get('keyframes',{}):
                p=geometry(neutral,active,original.size);transform=np.array([[1.,0,0],[0,1.,0]]);tracking='measured-keyframe'
            else:
                last=states[j];mat,tracking=flow_transform(prev,original,last['mask']) if active.get('track',True) else (np.array([[1.,0,0],[0,1.,0]]),'static-authored')
                p=transform_points(last['points'],mat).astype('float32');transform=mat@np.vstack([last['transform'],[0,0,1]])
                active=last['active']|{k:v for k,v in active.items() if k not in ['box','eyes','nose','mouth','eye_size','mouth_size','support','protect']}
            unclosed=p.copy()
            if 'apertures' in active:
                for group,v in zip([m.L_EYE,m.R_EYE],active['apertures'][i]):
                    center=p[group].mean(0);p[group,1]=center[1]+(p[group,1]-center[1])*v
            mask=support_mask(original.size,p,active,transform)
            # Captions always remain outside face support.
            for other in frame['layers']:
                if other['type']=='text':
                    x,y,w,h=other['box'];mask[y:y+h,x:x+w]=0
            if active.get('bars'):
                gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY)
                binary=((gray<active.get('bar_threshold',95))&(mask>0)).astype('uint8')
                length=max(5,round(original.height*active.get('bar_length',.18)))
                bars=cv2.morphologyEx(binary,cv2.MORPH_OPEN,np.ones((length,1),np.uint8));bars=cv2.dilate(bars,np.ones((1,3),np.uint8));mask[bars>0]=0
            if active.get('protect_colors'):
                for color in active['protect_colors']:
                    if color=='blue':fixed=(rgb[:,:,2]>rgb[:,:,0]*1.22)&(rgb[:,:,2]>rgb[:,:,1]*1.05)
                    elif color=='green':fixed=(rgb[:,:,1]>rgb[:,:,0]*1.2)&(rgb[:,:,1]>rgb[:,:,2]*1.08)
                    else:raise ValueError(color)
                    mask[fixed]=0
            if not mask.any():raise ValueError('empty calibrated mask')
            erase=np.zeros(mask.shape,np.uint8)
            for group in [m.L_EYE,m.R_EYE,m.L_BROW,m.R_BROW,m.NOSE,m.OUTER]:
                cv2.fillConvexPoly(erase,cv2.convexHull(np.rint(p[group]).astype('int32')),255)
            radius=max(2,round(m.basis(p)[1]*.09));erase=cv2.dilate(erase,np.ones((radius*2+1,)*2,np.uint8))
            clean=cv2.inpaint(rgb,np.minimum(erase,mask),max(2,radius),cv2.INPAINT_TELEA)
            yy,xx=np.where(mask>0);x0,y0,x1,y1=int(xx.min()),int(yy.min()),int(xx.max())+1,int(yy.max())+1;box=[x0,y0,x1-x0,y1-y0]
            controls={'eye_strength':active.get('eye_strength',1),'mouth':active.get('mouth_control','geometry'),'pose_weight':active.get('pose_weight',.85),'ink_contrast':active.get('ink_contrast',.35),'components':[],'profile':active.get('profile',0)}
            if active.get('lower_face_only'):controls['lower_face_only']=True
            if 'apertures' in active:controls['eye_aperture']=[max(.015,float(v)*.29) for v in active['apertures'][i]]
            for name,group in [('left-eye',m.L_EYE),('right-eye',m.R_EYE),('nose',m.NOSE),('mouth',m.OUTER)]:
                if name not in active.get('components',['left-eye','right-eye']):continue
                cm=component_mask(original.size,p,group,mask,active.get('component_padding',1))
                controls['components'].append({'name':name,'mask_asset':author.png_asset(Image.fromarray(cm)),'strength':1})
            if active.get('accessory_box'):
                cm=Image.new('L',original.size);pts=np.array(active['accessory_box']).reshape(2,2)*original.size;poly=np.array([[pts[0,0],pts[0,1]],[pts[1,0],pts[0,1]],[pts[1,0],pts[1,1]],[pts[0,0],pts[1,1]]]);poly=transform_points(poly,transform);ImageDraw.Draw(cm).polygon([tuple(v) for v in poly],fill=255)
                controls['components'].append({'name':'accessory','mask_asset':author.png_asset(Image.fromarray(np.minimum(np.array(cm),mask))),'strength':1})
            if 'fade' in active:
                progress=i/max(1,len(frames)-1);controls['blur']=round(progress*active['fade'][0],3);controls['opacity']=round(1-progress*active['fade'][1],3)
            recipe={'method':m.REVISION,'mode':row['metadata']['expression_policy']['mode'],'domain':active.get('domain',(layer.get('expression') or {}).get('domain','animal')),
                    'points':p.tolist(),'reference_asset':frame.get('reference_asset') or frame['asset'],'reference_format':frame.get('asset_format','png'),'reference_index':frame.get('source_index',0),
                    'base_box':box,'base_asset':author.png_asset(Image.fromarray(clean).crop((x0,y0,x1,y1))),'mask_asset':author.png_asset(Image.fromarray(mask)),'controls':controls}
            oldbox=layer['box'];oldpatches=[]
            for other in frame['layers']:
                if other is layer:break
                if other['type']=='asset' and other['box']==oldbox:oldpatches.append(other)
            for other in oldpatches:frame['layers'].remove(other)
            patch=Image.fromarray(clean).convert('RGBA').crop((x0,y0,x1,y1));patch.putalpha(Image.fromarray(mask).crop((x0,y0,x1,y1)));arr=np.array(patch);arr[arr[:,:,3]==0,:3]=0
            frame['layers'].insert(frame['layers'].index(layer),{'type':'asset','box':box,'value':author.png_asset(Image.fromarray(arr))})
            layer.update(box=box,mask_asset=author.png_asset(Image.fromarray(mask).crop((x0,y0,x1,y1))),expression=recipe,fusion=None,erase_polygon=[],protect_polygons=[],fit='cover',feather=1,rotation=0)
            states[j]={'points':unclosed,'mask':mask,'active':active,'transform':transform}
            proof.append({'frame':i,'face':j,'support_box':box,'support_pixels':int((mask>0).sum()),'tracking':tracking,'components':[c['name'] for c in controls['components']], 'fixed_clean_pixel_max_error':int(np.abs(clean.astype(int)-rgb.astype(int))[mask==0].max()) if (mask==0).any() else 0})
        prev=original
    row['spec']=TemplateSpec.model_validate(spec).model_dump();policy=row['metadata']['expression_policy'];policy.update(disposition='expression',supported_regions=len(proof),regions=len(proof))
    return proof


def main():
    p=argparse.ArgumentParser()
    for name in ['snapshot','plans','review','canonical','output']:p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();author=load_module('author_expression_library');neutral=author.canonical(a.canonical)
    snapshot=json.loads(a.snapshot.read_text());rows={r['key']:r for r in snapshot['image_templates']};plans=json.loads(a.plans.read_text());review=json.loads(a.review.read_text());updates=[];proof=[];ledger=[]
    for decision in review:
        tid=decision['id'];old=rows[decision['key']];row=copy.deepcopy(old);policy=row['metadata'].get('expression_policy',{});rating=decision['rating']
        entry={'id':tid,'key':row['key'],'name':row['metadata']['name'],'source_version':row['version'],'rating':rating}
        change=False
        if rating=='不需要':
            entry['action']='direct-paste'
            active=bool(policy.get('recipe')) or any(l.get('expression') or l.get('fusion') for f in ((row['spec'].get('frames') or [row['spec']]) if row['spec'] else []) for l in f['layers'])
            if active:
                policy.pop('recipe',None);policy.update(disposition='paste',supported_regions=0,reasons=['user-reviewed:direct-paste'])
                if row['spec']:
                    for f in row['spec'].get('frames') or [row['spec']]:
                        for l in f['layers']:
                            if l['type']=='face':l['expression']=None;l['fusion']=None
                change=True
        elif rating=='需调整' or decision.get('note'):
            if tid not in plans:raise ValueError('missing individually reviewed plan '+tid)
            plan=plans[tid];entry['action']=plan.get('action','region-and-expression');entry['reason']=plan['reason']
            if tid=='T337':
                policy.pop('recipe',None);policy.update(disposition='paste',supported_regions=0,reasons=['native-ascii:alpha-composite-and-black-density-corrected'])
            elif plan.get('action') in ['icon-and-text','editable-text']:
                if plan['action']=='editable-text':entry['frames']=rebuild(row,plan,neutral,author)
                special(row,plan,author)
            else:
                entry['frames']=rebuild(row,plan,neutral,author)
            policy=row['metadata']['expression_policy'];change=True
        else:entry['action']='preserve-reviewed-output'
        if change:
            policy['calibration']={'date':'2026-10-28','source_rating':rating,'action':entry['action'],'reason':entry.get('reason','direct-paste-request-applied'),'revision':'complete-review-v2'};policy['visual_status']='pending-user-review'
            row['metadata']['expression_policy']=policy
            row.update(base_version=old['version'],base_fingerprint=old['fingerprint'],version=old['version']+1);row.pop('id',None);row.pop('fingerprint',None);updates.append(row);proof.append(entry)
        entry['changed']=change;entry['version']=row['version'];ledger.append(entry)
    a.output.mkdir(parents=True,exist_ok=True)
    oldrefs=set().union(*(asset_refs(r['spec'])|asset_refs(r['metadata']) for r in rows.values()))
    for offset in range(0,len(updates),60):
        part=updates[offset:offset+60];refs=set().union(*(asset_refs(r['spec'])|asset_refs(r['metadata']) for r in part))-oldrefs
        assets={d:base64.b64encode((root()/'template_assets'/(d+'.png')).read_bytes()).decode() for d in refs}
        batch={'format':'gensticker-expression-ab-v1','templates':part,'assets':assets}
        (a.output/f'20261028-review-02-{offset//60+1:02}.json').write_text(json.dumps(batch,ensure_ascii=False,separators=(',',':')))
    (a.output/'compiled.json').write_text(json.dumps(updates,ensure_ascii=False));(a.output/'proof.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2));(a.output/'ledger.json').write_text(json.dumps(ledger,ensure_ascii=False,indent=2))
    print(json.dumps({'updated':len(updates),'preserved':sum(e['action']=='preserve-reviewed-output' for e in ledger),'direct':sum(e['action']=='direct-paste' for e in ledger),'frames':sum(len(e.get('frames',[])) for e in ledger)}))


def special(row,plan,author):
    """Editable captions and non-face image roles use ordinary declarative slots."""
    s=row['spec'];f=(s.get('frames') or [s])[0];im=author.read_asset(f.get('reference_asset') or f['asset'],f.get('source_index',0))
    if plan['action']=='icon-and-text':
        rgb=np.array(im);color=(rgb[:,:,2]>120)&(rgb[:,:,0]<100)&(rgb[:,:,1]>80)
        rgb[color]=255
        # Erase the original lower caption, preserving the character and arm.
        rgb[174:224]=255
        f['asset']=author.png_asset(Image.fromarray(rgb));f['asset_format']='png';f['source_index']=0
        # The hand/arm stays in front of the replaceable icon.
        crop=im.crop((55,77,150,115)).convert('RGBA');arr=np.array(crop);arr[(arr[:,:,2]>120)&(arr[:,:,0]<100)&(arr[:,:,1]>80),3]=0
        f['layers']=[{'type':'subject','box':[28,73,87,101],'fit':'contain','tone':'original'}, {'type':'asset','box':[55,77,95,38],'value':author.png_asset(Image.fromarray(arr))},
                     {'type':'text','box':[28,175,170,45],'slot':0,'value':'IE，你是…\n算了','font_size':17,'align':'center','max_lines':2}]
        s['defaults']=['IE，你是…\n算了'];row['metadata'].update(min_texts=0,max_texts=1,default_texts=s['defaults']);row['metadata']['expression_policy'].update(disposition='paste',supported_regions=0,reasons=['image-role:held-icon-not-background-face'])
    else:
        # Keep existing face output exactly; three authored captions are added.
        defaults=['新人鬼畜','安吉金蛋','张全蛋pk金馆长','哈哈哈'];s['defaults']=defaults
        f['layers']=[l for l in f['layers'] if l['type']!='text']
        definitions=[([19,18,71,24],defaults[0],'#eeeaff',13),([168,23,115,33],defaults[1],'#111111',22),([164,96,119,24],defaults[2],'#f6df45',13),([146,143,37,16],defaults[3],'#eeeeee',10)]
        rgb=np.array(im);erase=np.zeros(rgb.shape[:2],np.uint8)
        for box,text,color,size in definitions:
            x,y,w,h=box;erase[y:y+h,x:x+w]=255
        clean=cv2.inpaint(rgb,erase,4,cv2.INPAINT_TELEA)
        # A finite patch leaves faces, news logo and bottom credits untouched.
        patch=Image.fromarray(clean).convert('RGBA');patch.putalpha(Image.fromarray(erase));f['layers'].insert(0,{'type':'asset','box':[0,0,s['width'],s['height']],'value':author.png_asset(patch)})
        for index,(box,text,color,size) in enumerate(definitions):
            x,y,w,h=box;f['layers'].append({'type':'text','box':box,'slot':index,'value':text,'font_size':size,'color':color,'align':'center','max_lines':1,'original_asset':author.png_asset(im.crop((x,y,x+w,y+h)))})
        row['metadata'].update(min_texts=0,max_texts=4,default_texts=defaults)
    s=TemplateSpec.model_validate(s).model_dump();row['spec']=s


if __name__=='__main__':main()
