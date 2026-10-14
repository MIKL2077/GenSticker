"""Execute a reviewed visual decomposition; never executes model-authored code."""
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
    with Image.open(BytesIO(raw)) as source:
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
            defaults.append(layer.value);cv2.rectangle(captions,(x,y),(x+w-1,y+h-1),255,-1)
            cv2.rectangle(editable,(x,y),(x+w-1,y+h-1),255,-1)
        else:
            if not layer.erase_polygon:raise ValueError('face slots require a reviewed old-head removal polygon')
            cv2.fillPoly(editable,[np.array([(x+px,y+py) for px,py in layer.erase_polygon],dtype='int32')],255)
    if not defaults or sum(l.type=='face' for l in brief.slots)>1:raise ValueError('adapter requires captions and at most one reviewed face slot')
    for region in brief.protected:
        x,y,w,h=region.box
        if x<0 or y<0 or w<1 or h<1 or x+w>image.width or y+h>image.height:raise ValueError('protected region outside image')
        if np.any(editable[y:y+h,x:x+w]):raise ValueError('editable mask overlaps protected region: '+region.name)
    pixels=np.asarray(image)
    background=Image.fromarray(cv2.inpaint(pixels,captions,3,cv2.INPAINT_TELEA)) if captions.any() else image.copy()
    output=BytesIO();background.save(output,'PNG');data=output.getvalue();digest=hashlib.sha256(data).hexdigest()
    directory=root()/'template_assets';directory.mkdir(exist_ok=True);path=directory/(digest+'.png');existed=path.exists();path.write_bytes(data)
    try:
        spec=TemplateSpec(width=image.width,height=image.height,layers=[Layer(type='asset',box=(0,0,image.width,image.height),value=digest)]+brief.slots,defaults=defaults).model_dump()
        reference=Image.open(render(spec,[],defaults,preview=True)).convert('RGB')
        error=float(np.abs(np.asarray(image.resize((128,128))).astype(float)-np.asarray(reference.resize((128,128))).astype(float)).mean())
        if error>12:raise ValueError('default caption reconstruction failed; review typography')
        face_slots=any(l.type=='face' for l in brief.slots)
        synthesis_error=None
        if face_slots and validation_photo is not None:
            replacement=Image.open(render(spec,[validation_photo],defaults)).convert('RGB')
            synthesis_error=float(np.abs(np.asarray(reference).astype(float)-np.asarray(replacement).astype(float))[editable==0].mean())
            if synthesis_error>2:raise ValueError('replacement changed the protected scene outside editable masks')
        if face_slots and publish and validation_photo is None:raise ValueError('publication requires an actual face test image')
        protected_error=float(np.abs(pixels.astype(float)-np.array(background).astype(float))[captions==0].mean())
        metadata={**meta,'name':meta.get('name') or defaults[0], 'min_images':1 if face_slots else 0,'max_images':1 if face_slots else 0,'min_texts':len(defaults),'max_texts':len(defaults),'default_texts':defaults,'tags':meta.get('tags',['general']),'original_hash':hashlib.sha256(raw).hexdigest(),'conversion':'reviewed-face-slot-v1' if face_slots else 'reviewed-caption-slot-v1','decomposition':brief.model_dump(exclude={'metadata'}),'quality':{'round_trip_mae':round(error,2),'protected_pixel_mae':round(protected_error,3),'synthesis_protected_mae':round(synthesis_error,3) if synthesis_error is not None else None,'face_slot_tested':bool(face_slots and validation_photo is not None),'method':'reviewed-decomposition-v1'}}
        key='auto_'+metadata['original_hash'][:24]
        if publish:publish_template(key,metadata,spec)
        return {'key':key,'metadata':metadata,'spec':spec}
    except Exception:
        if not existed:path.unlink(missing_ok=True)
        raise
