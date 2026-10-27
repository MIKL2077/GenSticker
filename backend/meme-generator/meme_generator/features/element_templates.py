"""Compile reviewed in-place element replacements into bounded frame recipes.

Authoring only: remove old glyphs/faces once, keep original pixels elsewhere,
and record explicit geometry for every frame. Runtime does no OCR or tracking.
"""
import hashlib
from io import BytesIO
import json

import cv2
import numpy as np
from PIL import Image, ImageDraw

from meme_generator.safe_images import open_input_image
from .declarative import Layer, TemplateFrame, TemplateSpec


def fingerprint(spec):
    return hashlib.sha256(json.dumps(spec,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


def compile_elements(raw, plans, defaults):
    """plans contains one list of face/text layers per decoded source frame."""
    assets={}
    def add(image):
        output=BytesIO();image.save(output,'PNG');data=output.getvalue()
        digest=hashlib.sha256(data).hexdigest();assets[digest]=data
        return digest
    with open_input_image(BytesIO(raw)) as source:
        count=getattr(source,'n_frames',1)
        if count!=len(plans) or not 1<=count<=40 or source.width*source.height*count>8_000_000:
            raise ValueError('every bounded source frame needs an explicit plan')
        if min(source.size)<64 or max(source.size)>512:raise ValueError('review source canvas before compiling')
        width,height=source.size
        if count>1:
            digest=hashlib.sha256(raw).hexdigest();assets[digest]=raw;asset_format='gif'
            if source.format!='GIF':raise ValueError('animated source must be a normalized GIF')
        else:
            digest=add(source.convert('RGBA'));asset_format='png'
        frames=[];inventories=[]
        for index,plan in enumerate(plans):
            source.seek(index)
            image=Image.alpha_composite(Image.new('RGBA',source.size,'white'),source.convert('RGBA'))
            pixels=np.asarray(image.convert('RGB'))
            layers=[];occupied=np.zeros((height,width),dtype='uint8');inventory=[]
            for entry in plan:
                layer=Layer.model_validate(entry)
                TemplateSpec(width=width,height=height,layers=[layer])
                x,y,w,h=layer.box
                if layer.type not in {'face','text'}:raise ValueError('author only existing face or caption replacements')
                mask=np.zeros((height,width),dtype='uint8')
                if layer.type=='face':
                    if not layer.erase_polygon:raise ValueError('face requires its own measured polygon')
                    from .face_slot import removal_mask
                    if layer.mask_asset:
                        from .store import root
                        data=(root()/'template_assets'/(layer.mask_asset+'.png')).read_bytes()
                        if hashlib.sha256(data).hexdigest()!=layer.mask_asset:raise ValueError('face mask checksum mismatch')
                        assets[layer.mask_asset]=data
                    mask=np.asarray(removal_mask(image.size,[layer])).copy()
                else:
                    if layer.slot>=len(defaults):raise ValueError('caption default missing')
                    mask[y:y+h,x:x+w]=255
                    if layer.text_mask=='glyph':
                        region=pixels[y:y+h,x:x+w]
                        target=np.array([int(layer.color[k:k+2],16) for k in (1,3,5)])
                        ink=np.linalg.norm(region.astype(float)-target,axis=2)<110
                        local=cv2.dilate(ink.astype('uint8')*255,np.ones((5,5),dtype='uint8'))
                        if np.mean(local>0)<.005:raise ValueError('source caption ink not found; review its color')
                        mask[y:y+h,x:x+w]=local
                    layer=layer.model_copy(update={'original_asset':add(image.crop((x,y,x+w,y+h)))})
                if np.any((occupied>0)&(mask>0)):raise ValueError('replacement slots overlap; author an occlusion mask')
                occupied=np.maximum(occupied,mask)
                # Clean plate patches are alpha-masked; the rest of the original
                # GIF remains compressed and retains pixel-exact source context.
                cleaned=cv2.inpaint(pixels,mask,3,cv2.INPAINT_TELEA)
                if layer.type=='text':
                    region=pixels[y:y+h,x:x+w]
                    bins=(region//16).reshape(-1,3)
                    colors,counts=np.unique(bins,axis=0,return_counts=True)
                    best=int(np.argmax(counts))
                    outer=pixels[max(0,y-3):min(height,y+h+3),max(0,x-3):min(width,x+w+3)]
                    ring=np.ones(outer.shape[:2],dtype=bool)
                    oy=y-max(0,y-3);ox=x-max(0,x-3);ring[oy:oy+h,ox:ox+w]=False
                    border=outer[ring]
                    fill_candidate=np.median(region[np.all(region//16==colors[best],axis=2)],axis=0)
                    matches_border=len(border)>0 and np.linalg.norm(np.median(border,axis=0)-fill_candidate)<35
                    if layer.text_mask!='glyph' and counts[best]>.4*w*h and matches_border:
                        same=np.all(region//16==colors[best],axis=2)
                        fill=np.median(region[same],axis=0).astype('uint8')
                        cleaned[mask>0]=fill
                patch=Image.fromarray(cleaned[y:y+h,x:x+w]).convert('RGBA')
                patch.putalpha(Image.fromarray(mask[y:y+h,x:x+w]))
                patch_hash=add(patch)
                layers.extend([Layer(type='asset',box=layer.box,value=patch_hash),layer])
                inventory.append({'type':layer.type,'slot':layer.slot,'box':list(layer.box),
                                  'original_text':layer.value if layer.type=='text' else '',
                                  'erase_polygon':layer.erase_polygon if layer.type=='face' else []})
            frames.append(TemplateFrame(asset=digest,asset_format=asset_format,source_index=index,
                         duration_ms=max(20,int(source.info.get('duration',100))),layers=layers))
            inventories.append(inventory)
    if not any(f.layers for f in frames):raise ValueError('no original element is replaceable')
    spec=TemplateSpec(width=width,height=height,frames=frames,defaults=defaults).model_dump()
    return spec,assets,inventories


def validate_elements(spec, metadata):
    """Prevent story panels, unbound evidence and incomplete frame plans at restore."""
    value=TemplateSpec.model_validate(spec)
    if not value.frames or metadata.get('conversion')!='element-replacement-v1':raise ValueError('missing authored frames')
    review=metadata.get('review',{});quality=metadata.get('quality',{})
    if review.get('visual_status')!='approved' or quality.get('spec_sha256')!=fingerprint(spec):raise ValueError('element evidence does not match recipe')
    if metadata.get('source_canvas')!=[value.width,value.height]:raise ValueError('source canvas changed')
    if quality.get('analyzed_frames')!=len(value.frames) or quality.get('protected_pixel_mae')!=0:
        raise ValueError('frame/protected-pixel analysis missing')
    fused=[f for f in value.frames if any(l.fusion for l in f.layers)]
    if fused:
        from .face_fusion import MODEL_SHA256, REVISION
        if metadata.get('compositing_method')!=REVISION or quality.get('fusion_model_sha256')!=MODEL_SHA256 or quality.get('fusion_checked_frames')!=len(fused) or quality.get('fusion_fixed_pixel_max_error')!=0:
            raise ValueError('portrait fusion lacks bound frame/model/protected-pixel evidence')
    faces={l.slot for f in value.frames for l in f.layers if l.type=='face'}
    texts={l.slot for f in value.frames for l in f.layers if l.type=='text'}
    if faces!=set(range(metadata.get('max_images',0))) or texts!=set(range(metadata.get('max_texts',0))):
        raise ValueError('input counts differ from original-element slots')
    if metadata.get('min_images')!=metadata.get('max_images') or metadata.get('min_texts')!=metadata.get('max_texts'):
        raise ValueError('replacement inputs must be explicit')
    if value.defaults!=metadata.get('default_texts',[]):raise ValueError('source caption defaults differ')
    if not quality.get('actual_replacement_verified') or not quality.get('caption_inventory_complete'):
        raise ValueError('replacement or complete caption review missing')
    if len(value.frames)>1 and not quality.get('motion_verified'):raise ValueError('animation was not checked')
    inventory=metadata.get('caption_inventory',[])
    if {c['slot'] for c in inventory if c.get('editable')}!=texts:raise ValueError('caption inventory differs from recipe')
