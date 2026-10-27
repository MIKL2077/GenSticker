#!/usr/bin/env python3
"""Offline A/B rig compiler. No portraits, private IDs, or runtime template inference.

Read an exported public library snapshot (image_templates), author guides from
its original artwork, preserve keys/versions, and emit reviewable delta batches.
The random assignment and 100-template selection precede detection/rendering.
"""
import argparse,base64,copy,hashlib,io,json,os,random,time
from pathlib import Path
import cv2
import numpy as np
from PIL import Image,ImageDraw,ImageOps
from meme_generator.features import expression_math as m, expression_runtime as rt
from meme_generator.features.declarative import TemplateSpec
from meme_generator.features.store import root

SEED='GenSticker-expression-AB-20261027-v1'


def png_asset(image):
    out=io.BytesIO();image.save(out,'PNG');raw=out.getvalue();digest=hashlib.sha256(raw).hexdigest()
    path=root()/'template_assets'/(digest+'.png')
    if not path.exists():path.write_bytes(raw)
    return digest


def read_asset(digest,index=0,mode="RGB"):
    path=next((root()/'template_assets'/(digest+ext) for ext in ['.png','.gif'] if (root()/'template_assets'/(digest+ext)).is_file()))
    with Image.open(path) as im:
        im.seek(index);return im.convert(mode)


def detect(image):
    import mediapipe as mp
    result=rt._detector.detect(mp.Image(image_format=mp.ImageFormat.SRGB,data=np.ascontiguousarray(np.array(image.convert('RGB')))))
    if not result.face_landmarks:return None
    return np.array([[p.x*image.width,p.y*image.height] for p in result.face_landmarks[0]],np.float32)


def canonical(path):
    if hashlib.sha256(path.read_bytes()).hexdigest()!='8bac80443397e113f41a8b565ea72c59390bc031d9defab289dba7bc0c54e618':raise ValueError('canonical face checksum mismatch')
    vertices=np.array([[float(x) for x in line.split()[1:4]] for line in path.read_text().splitlines() if line.startswith('v ')],np.float32)
    p=m.normalized(vertices[:,:2]*np.array([1,-1],np.float32))
    return np.vstack([p,np.repeat(p[1:2],10,axis=0)])


def semantic_rig(layer,neutral):
    f=layer.get('fusion')
    if not f:return None
    x,y,w,h=layer['box'];a,b=np.array(f['eyes'],np.float32)+[x,y];delta=b-a;distance=np.linalg.norm(delta)
    u=delta/distance;v=np.array([-u[1],u[0]],np.float32)
    p=neutral*distance@np.stack([u,v],1).T+(a+b)/2
    if f.get('mouth'):
        center=np.array(f['mouth'])+[x,y];old=(p[61]+p[291])/2
        p[m.OUTER+m.INNER]+=center-old
    if f.get('chin'):p[152]=np.array(f['chin'])+[x,y]
    return p.astype('float32')


def domain_for(image,layer,metadata):
    if layer and (layer.get('tone')=='grayscale' or (layer.get('fusion') or {}).get('style')=='photocopy'):return 'ink'
    name=metadata.get('name','')
    if any(t in name for t in ['猫','狗','熊','兔','猪','猩猩','鸟','鸭','老虎','dog','cat']):return 'animal'
    if any(t in name for t in ['阿库娅','动漫','二次元','琪','蕾姆','初音','千反田','派蒙','胡桃','anime']):return 'anime'
    return 'human'


def layer_mask(image,layer):
    x,y,w,h=layer['box'];mask=Image.new('L',image.size);d=ImageDraw.Draw(mask)
    if layer.get('mask_asset'):mask.paste(read_asset(layer['mask_asset']).convert('L'),(x,y))
    elif layer.get('erase_polygon'):d.polygon([(x+a,y+b) for a,b in layer['erase_polygon']],fill=255)
    else:d.ellipse((x,y,x+w-1,y+h-1),fill=255)
    for points in layer.get('protect_polygons',[]):d.polygon([(x+a,y+b) for a,b in points],fill=0)
    return np.array(mask)


def make_recipe(image,layer,layers,metadata,mode,neutral,base=None,points_override=None):
    domain=domain_for(image,layer,metadata);p=detect(image) if points_override is None else points_override.copy()
    if p is not None and layer:
        x,y,w,h=layer['box'];center=p[m.OVAL].mean(0)
        if not (x<=center[0]<x+w and y<=center[1]<y+h):p=None
    cropped=False
    if p is None and layer and points_override is None:
        x,y,w,h=layer['box'];mx,my=round(w*.2),round(h*.2);left,top=max(0,x-mx),max(0,y-my)
        region=image.crop((left,top,min(image.width,x+w+mx),min(image.height,y+h+my)))
        candidate=detect(region)
        if candidate is not None:
            candidate+=np.array([left,top],np.float32);center=candidate[m.OVAL].mean(0)
            if x<=center[0]<x+w and y<=center[1]<y+h:p=candidate;cropped=True
    origin='landmarks-on-source-artwork' if points_override is None else 'offline-timeline-interpolation'
    if cropped:origin='landmarks-on-source-slot-crop'
    if p is None and layer:
        p=semantic_rig(layer,neutral);origin='existing-measured-semantic-anchors'
    if p is None:return None,'template_face_unavailable'
    if m.basis(p)[1]<6:return None,'template_face_too_small'
    mask=layer_mask(image,layer) if layer else m.poly((image.height,image.width),p[m.OVAL])
    if domain=='human' and layer:
        import mediapipe as mp
        parsed=rt._segmenter.segment(mp.Image(image_format=mp.ImageFormat.SRGB,data=np.ascontiguousarray(np.array(image))))
        face=parsed.confidence_masks[3].numpy_view().copy().squeeze();hand=parsed.confidence_masks[2].numpy_view().copy().squeeze()
        mask[(face>.4)&(hand<.35)&(m.poly(mask.shape,p[m.OVAL])>0)]=255
    if domain=='anime':
        pix=np.array(image).astype('int16');yy,xx=np.indices(mask.shape);center=p[m.OUTER].mean(0);distance=m.basis(p)[1]
        region=(yy>p[1,1])&(yy<p[152,1])&(np.abs(xx-center[0])<distance*.62)&(m.poly(mask.shape,p[m.OVAL])>0)
        ink=region&(pix[:,:,0]>pix[:,:,1]*1.12)&(pix.max(2)-pix.min(2)>35)
        contours,_=cv2.findContours(ink.astype('uint8'),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
        viable=[c for c in contours if cv2.contourArea(c)>distance**2*.018]
        if viable:
            mx,my,mw,mh=cv2.boundingRect(max(viable,key=cv2.contourArea));angles=np.linspace(-np.pi,np.pi,20,endpoint=False)
            ellipse=np.stack([mx+mw/2+mw*.51*np.cos(angles),my+mh/2+mh*.51*np.sin(angles)],axis=1).astype('float32')
            p[m.OUTER]=ellipse;p[m.INNER]=ellipse.mean(0)+(ellipse-ellipse.mean(0))*.87
        outer=p[m.OUTER];width=np.linalg.norm(p[61]-p[291]);height=np.ptp(outer[:,1]);gap=np.linalg.norm(p[13]-p[14])
        if height/max(width,1)>.48 and gap<height*.2:
            center=outer.mean(0);p[m.INNER]=center+(outer-center)*np.array([.86,.78])
    if domain=='ink':
        pix=np.array(image).astype('int16');colorful=(pix.max(2)-pix.min(2)>38)&(pix.max(2)>80)
        mask[cv2.dilate(colorful.astype('uint8'),np.ones((3,3),np.uint8))>0]=0
    # Reapply authored prop protection after any mask expansion; protect text too.
    draw=ImageDraw.Draw(image_mask:=Image.fromarray(mask))
    if layer:
        x,y,_,_=layer['box']
        for points in layer.get('protect_polygons',[]):draw.polygon([(x+a,y+b) for a,b in points],fill=0)
    for l in layers:
        if l['type']=='text':
            x,y,w,h=l['box'];draw.rectangle((x,y,x+w-1,y+h-1),fill=0)
    mask=np.array(image_mask)
    feature=np.zeros(mask.shape,np.uint8)
    for group in [m.L_EYE,m.R_EYE,m.L_BROW,m.R_BROW,m.NOSE,m.OUTER]:
        cv2.fillConvexPoly(feature,cv2.convexHull(np.rint(p[group]).astype('int32')),255)
    radius=max(2,round(m.basis(p)[1]*.07));feature=cv2.dilate(feature,cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(radius*2+1,radius*2+1)))
    rgb=np.array(base.convert('RGB')) if base is not None and domain=='animal' else np.array(image)
    clean=cv2.inpaint(rgb,np.minimum(feature,mask),3,cv2.INPAINT_TELEA)
    if not np.any(mask):return None,'empty_protected_support'
    recipe={'method':m.REVISION,'mode':mode,'domain':domain,'points':p.tolist(),
        'reference_asset':png_asset(image),'base_asset':png_asset(Image.fromarray(clean)),'mask_asset':png_asset(Image.fromarray(mask))}
    return recipe,origin


def compile_row(row,mode,neutral,native_root):
    item=copy.deepcopy(row);metadata=item['metadata'];spec=item['spec'];reasons=[];supported=0;total=0
    policy={'method':m.REVISION,'mode':mode,'seed':SEED,'visual_status':'pending-user-review','adapter':'declarative' if spec else 'native-input'}
    if spec:
        for frame in spec.get('frames') or [spec]:
            digest=frame.get('reference_asset') or frame.get('asset') or spec.get('reference_asset')
            if not digest:
                reasons.append('subject_layout_has_no_expression_source');continue
            image=read_asset(digest,frame.get('source_index',0));base=image.convert('RGBA')
            for l in frame['layers']:
                if l['type']=='face':break
                if l['type']=='asset':
                    x,y,w,h=l['box'];base.alpha_composite(ImageOps.contain(read_asset(l['value'],mode='RGBA'),(w,h)),(x,y))
            for layer in frame['layers']:
                if layer['type']!='face':continue
                total+=1;recipe,reason=make_recipe(image,layer,frame['layers'],metadata,mode,neutral,base)
                if recipe:layer['expression']=recipe;supported+=1
                reasons.append(reason)
        item['spec']=TemplateSpec.model_validate(spec).model_dump()
    else:
        folder=native_root/row['key'];paths=sorted((folder/'images').glob('*.png'))[:6]
        # Use original drawing assets, never the example's dummy user avatar.
        for path in paths:
            with Image.open(path) as raw:
                if raw.width*raw.height>4_000_000:continue
                image=Image.alpha_composite(Image.new('RGBA',raw.size,'white'),raw.convert('RGBA')).convert('RGB')
                image.thumbnail((768,768))
            recipe,reason=make_recipe(image,None,[],metadata,mode,neutral)
            if recipe:
                policy['recipe']=recipe;supported=1;reasons.append('native-source:'+path.name+':'+reason);break
        total=1
        if not supported:reasons.append('native_layout_has_no_detectable_expression_source')
    policy.update(supported_regions=supported,regions=total,reasons=sorted(set(reasons)))
    metadata['expression_policy']=policy
    return {'key':row['key'],'base_version':row['version'],'base_fingerprint':row['fingerprint'],'version':row['version']+1,'metadata':metadata,'spec':item['spec']}


def main():
    p=argparse.ArgumentParser();p.add_argument('--snapshot',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--canonical',type=Path,required=True);p.add_argument('--native-root',type=Path,required=True);a=p.parse_args()
    rows=json.loads(a.snapshot.read_text())['image_templates'];rows=sorted(rows,key=lambda r:r['key']);rng=random.Random(SEED)
    modes=['A']*((len(rows)+1)//2)+['B']*(len(rows)//2);rng.shuffle(modes)
    assigned=dict(zip([r['key'] for r in rows],modes));sample=[]
    for mode in ['A','B']:
        pool=[r['key'] for r in rows if assigned[r['key']]==mode];rng.shuffle(pool);sample.extend(pool[:50])
    a.output.mkdir(parents=True,exist_ok=True)
    selection={'seed':SEED,'assignment':assigned,'sample_keys':sample,'selection':'50 uniformly sampled per assigned mode before authoring; no failure filtering'}
    (a.output/'selection.json').write_text(json.dumps(selection,ensure_ascii=False,indent=2))
    if not rt.warmup():raise RuntimeError('offline authoring models unavailable')
    neutral=canonical(a.canonical);items=[];assets={};batches=[];batchitems=[];batchbytes=0
    inventory=a.output/'original-assets.json'
    if not inventory.exists():inventory.write_text(json.dumps([p.stem for p in (root()/'template_assets').iterdir()]))
    from meme_generator.features.storage import asset_refs
    oldrefs=set().union(*(asset_refs(r['spec'])|asset_refs(r['metadata']) for r in rows))
    for i,row in enumerate(rows):
        item=compile_row(row,assigned[row['key']],neutral,a.native_root);items.append(item)
        refs=(asset_refs(item['spec'])|asset_refs(item['metadata']))-oldrefs
        fresh={d:base64.b64encode((root()/'template_assets'/(d+'.png')).read_bytes()).decode() for d in refs if d not in assets}
        size=len(json.dumps(item).encode())+sum(len(v) for v in fresh.values())
        if batchitems and (len(batchitems)>=100 or batchbytes+size>30*1024**2):
            batches.append({'format':'gensticker-expression-ab-v1','templates':batchitems,'assets':assets});batchitems=[];assets={};batchbytes=0
            fresh={d:base64.b64encode((root()/'template_assets'/(d+'.png')).read_bytes()).decode() for d in refs}
        batchitems.append(item);assets.update(fresh);batchbytes+=size
        policy=item['metadata']['expression_policy'];print(i+1,row['key'],policy['mode'],str(policy['supported_regions'])+'/'+str(policy['regions']),flush=True)
        (a.output/'compiled.json').write_text(json.dumps(items,ensure_ascii=False))
    if batchitems:batches.append({'format':'gensticker-expression-ab-v1','templates':batchitems,'assets':assets})
    for i,batch in enumerate(batches):
        (a.output/f'20261027-ab-{i+1:02}.json').write_text(json.dumps(batch,ensure_ascii=False,separators=(',',':')))
    rt.close();print('DONE',len(items),len(batches),flush=True)

if __name__=='__main__':main()
