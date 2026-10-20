"""Execute a reviewed visual decomposition; never executes model-authored code."""
from meme_generator.safe_images import open_image, open_input_image
import hashlib
from io import BytesIO
import numpy as np
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field
from .declarative import Layer, TemplateSpec, render
from .store import root


class ProtectedRegion(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1,max_length=80)
    box: tuple[int,int,int,int]


class Brief(BaseModel):
    model_config = ConfigDict(extra='forbid')
    canvas: tuple[int,int]
    intent: str = Field(min_length=5,max_length=800)
    protected: list[ProtectedRegion] = Field(min_length=1,max_length=20)
    slots: list[Layer] = Field(min_length=1,max_length=5)
    metadata: dict


def decompose(raw, brief, *, authorized_local=False, validation_photo=None, publish=False):
    import cv2
    from .ingest import LICENSES
    from .catalog import publish as publish_template
    brief=Brief.model_validate(brief)
    meta=brief.metadata
    local=authorized_local and meta.get('origin')=='user-provided' and meta.get('review',{}).get('explicit_user_request') is True
    if not local and (meta.get('license') not in LICENSES or any(not meta.get(k) for k in ('source_url','author','license_url'))):
        raise ValueError('source attribution or derivative license missing')
    with open_input_image(BytesIO(raw)) as source:
        if getattr(source,'n_frames',1)>1:raise ValueError('animated decomposition needs a frame-aware renderer')
        if source.size!=brief.canvas:raise ValueError('brief coordinates do not match original image dimensions')
        image=source.convert('RGB')
    if max(image.size)>1024:raise ValueError('resize image and review all coordinates before decomposition')
    editable=np.zeros((image.height,image.width),dtype='uint8')
    captions=np.zeros_like(editable)
    defaults=[]
    for layer in brief.slots:
        if layer.type not in ('face','text'):raise ValueError('this reviewed adapter supports face and text slots; other slot types stay pending')
        # Validate all pixel bounds before passing coordinates to OpenCV.
        TemplateSpec(width=image.width,height=image.height,layers=[layer])
        x,y,w,h=layer.box
        if layer.type=='text':
            if layer.slot!=len(defaults) or not layer.value:raise ValueError('caption slots must be consecutive and have original text')
            defaults.append(layer.value)
            if layer.text_mask=='glyph':
                color=np.array([int(layer.color[i:i+2],16) for i in (1,3,5)],dtype='float32')
                region=np.array(image)[y:y+h,x:x+w].astype('float32')
                ink=(np.linalg.norm(region-color,axis=2)<90).astype('uint8')*255
                if np.mean(ink>0)<.005:raise ValueError('caption colour not found; review original typography')
                radius=layer.stroke_width+2;ink=cv2.dilate(ink,np.ones((2*radius+1,2*radius+1),dtype='uint8'))
                captions[y:y+h,x:x+w]=np.maximum(captions[y:y+h,x:x+w],ink)
            else:cv2.rectangle(captions,(x,y),(x+w-1,y+h-1),255,-1)
            cv2.rectangle(editable,(x,y),(x+w-1,y+h-1),255,-1)
        else:
            if not layer.erase_polygon:raise ValueError('face slots require a reviewed old-head removal polygon')
            cv2.fillPoly(editable,[np.array([(x+px,y+py) for px,py in layer.erase_polygon],dtype='int32')],255)
    if sum(l.type=='face' for l in brief.slots)>1:raise ValueError('adapter supports at most one reviewed image slot')
    for region in brief.protected:
        x,y,w,h=region.box
        if x<0 or y<0 or w<1 or h<1 or x+w>image.width or y+h>image.height:raise ValueError('protected region outside image')
        if np.any(editable[y:y+h,x:x+w]):raise ValueError('editable mask overlaps protected region: '+region.name)
    pixels=np.asarray(image)
    background=Image.fromarray(cv2.inpaint(pixels,captions,3,cv2.INPAINT_TELEA)) if captions.any() else image.copy()
    output=BytesIO();background.save(output,'PNG');data=output.getvalue();digest=hashlib.sha256(data).hexdigest()
    directory=root()/'template_assets';directory.mkdir(exist_ok=True);path=directory/(digest+'.png');existed=path.exists();path.write_bytes(data)
    try:
        from .face_slot import prepared_background
        face_slots=any(l.type=='face' for l in brief.slots)
        material=digest
        if face_slots:
            clean=prepared_background(background,brief.slots);buf=BytesIO();clean.save(buf,'PNG');material=hashlib.sha256(buf.getvalue()).hexdigest();(directory/(material+'.png')).write_bytes(buf.getvalue())
        spec=TemplateSpec(width=image.width,height=image.height,layers=[Layer(type='asset',box=(0,0,image.width,image.height),value=material)]+brief.slots,defaults=defaults,background_prepared=face_slots,reference_asset=digest if face_slots else '').model_dump()
        reference=open_image(render(spec,[],defaults,preview=True)).convert('RGB')
        error=float(np.abs(np.asarray(image.resize((128,128))).astype(float)-np.asarray(reference.resize((128,128))).astype(float)).mean())
        if error>12:raise ValueError('default caption reconstruction failed; review typography')
        synthesis_error=None
        if face_slots and validation_photo is not None:
            replacement=open_image(render(spec,[validation_photo],defaults)).convert('RGB')
            synthesis_error=float(np.abs(np.asarray(reference).astype(float)-np.asarray(replacement).astype(float))[editable==0].mean())
            if synthesis_error>2:raise ValueError('replacement changed the protected scene outside editable masks')
        if face_slots and publish and validation_photo is None:raise ValueError('publication requires an actual face test image')
        protected_error=float(np.abs(pixels.astype(float)-np.array(background).astype(float))[captions==0].mean())
        metadata={**meta,'name':meta.get('name') or (defaults[0] if defaults else '主体替换'), 'min_images':1 if face_slots else 0,'max_images':1 if face_slots else 0,'min_texts':len(defaults),'max_texts':len(defaults),'default_texts':defaults,'tags':meta.get('tags',['general']),'original_hash':hashlib.sha256(raw).hexdigest(),'conversion':'reviewed-image-slot-v2' if face_slots else 'reviewed-caption-slot-v1','decomposition':brief.model_dump(exclude={'metadata'}),'quality':{'round_trip_mae':round(error,2),'protected_pixel_mae':round(protected_error,3),'synthesis_protected_mae':round(synthesis_error,3) if synthesis_error is not None else None,'image_slot_tested':bool(face_slots and validation_photo is not None),'background_prepared':face_slots,'method':'reviewed-decomposition-v2'}}
        key='auto_'+metadata['original_hash'][:24]
        if publish:publish_template(key,metadata,spec)
        return {'key':key,'metadata':metadata,'spec':spec}
    except Exception:
        if not existed:path.unlink(missing_ok=True)
        raise
