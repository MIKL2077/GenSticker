"""Cheap intent-preserving conversion gates, without a paid vision model."""
from meme_generator.safe_images import open_image, open_input_image
import hashlib
import json
import re
from io import BytesIO
import numpy as np
from PIL import Image
from .store import connect, root
from .declarative import TemplateSpec, render
from .catalog import publish, emotion_tags

_ocr = None
REACTIONS = re.compile(r'笑|哭|怒|就这|开心|惊|累|困|无语|什么|怎么|人呢|不可能|不好意思|在家办公|晚上好|早上好|早安|晚安|好的|不要|不想|上班|打工|下班|摸鱼|谢谢|好家伙|离谱|没事|懂|为什么|救命|哈哈|\b(?:bruh|why|lol|wtf|when|no|yes)\b|y\s*u\s*no',re.I)


def perceptual_hash(image):
    a=np.asarray(image.convert('L').resize((9,8)))
    value=0
    for bit in (a[:,1:]>a[:,:-1]).flatten():value=(value<<1)|int(bit)
    return f'{value:016x}'


def duplicate(image, captions):
    phash=perceptual_hash(image)
    phrase=re.sub(r'\W+','', '|'.join(captions).lower())
    signature=hashlib.sha256(phrase.encode()).hexdigest()
    db=connect()
    try:
        for row in db.execute("SELECT metadata FROM templates WHERE status='published'"):
            m=json.loads(row['metadata'])
            if m.get('intent_signature')==signature:raise ValueError('duplicate reaction intent')
            old=m.get('perceptual_hash')
            if old and bin(int(old,16)^int(phash,16)).count('1')<=4:raise ValueError('near-duplicate visual')
    finally:db.close()
    return phash,signature


def recognize(image):
    global _ocr
    if _ocr is None:
        from rapidocr_onnxruntime import RapidOCR
        _ocr=RapidOCR(intra_op_num_threads=2,inter_op_num_threads=1)
    recognized,_=_ocr(np.array(image.convert('RGB')))
    return recognized or []


def convert_caption(raw, metadata, *, publish_result=True, allow_draft=False):
    """Keep original expression/action intact; expose only reliable edge captions."""
    import cv2
    with open_input_image(BytesIO(raw)) as original:
        if getattr(original,'n_frames',1)>1:raise ValueError('animated intent requires a dedicated converter')
        if original.width*original.height>16000000:raise ValueError('image too large')
        image=original.convert('RGB');image.thumbnail((768,768))
    if min(image.size)<64:raise ValueError('image too small')
    mask=np.zeros((image.height,image.width),dtype='uint8')
    defaults=[];layers=[];confidences=[]
    threshold=.80 if allow_draft and not publish_result else .95
    for polygon,caption,confidence in recognize(image):
        if confidence<threshold or not 2<=len(caption)<=100:continue
        points=np.asarray(polygon,dtype='int32');x0,y0=points.min(axis=0);x1,y1=points.max(axis=0)
        x0,y0=max(0,int(x0)),max(0,int(y0));x1,y1=min(image.width,int(x1)),min(image.height,int(y1))
        if x1-x0<20 or y1-y0<12:continue
        if not (y1<=image.height*.35 or y0>=image.height*.65):continue
        if abs(int(points[0][1])-int(points[1][1]))>max(3,(y1-y0)*.15):continue
        if len(defaults)>=2:raise ValueError('complex caption layout')
        original_height=y1-y0
        reviewed_mask=metadata.get('review', {}).get('caption_mask', 'box')
        if reviewed_mask in {'light-glyph', 'dark-glyph'}:
            # Explicit author review selects foreground polarity. Remove just
            # caption glyphs and their outlines, retaining scene texture.
            x0,y0=max(0,x0-2),max(0,y0-2);x1,y1=min(image.width,x1+2),min(image.height,y1+2)
            region=np.asarray(image)[y0:y1,x0:x1]
            selected=(region.min(axis=2)>175) if reviewed_mask=='light-glyph' else (region.max(axis=2)<110)
            radius=max(1,min(3,int(metadata.get('review', {}).get('caption_erase_radius',1))))
            glyphs=cv2.dilate(selected.astype('uint8')*255,np.ones((radius*2+1,radius*2+1),dtype='uint8'))
            mask[y0:y1,x0:x1]=np.maximum(mask[y0:y1,x0:x1],glyphs)
        else:
            cv2.rectangle(mask,(x0,y0),(x1-1,y1-1),255,-1)
        layers.append({'type':'text','box':[x0,y0,x1-x0,y1-y0],'slot':len(defaults),'value':caption,'font_size':min(100,max(10,original_height-2))})
        style = metadata.get('review', {}).get('caption_style', {})
        if style:
            # A reviewed style is explicit local input, not inferred model code.
            layers[-1].update({k:style[k] for k in ('color','weight','align','stroke_color','stroke_width','font_size','max_lines') if k in style})
        defaults.append(caption);confidences.append(float(confidence))
    if not defaults or not REACTIONS.search(' '.join(defaults)):raise ValueError('reaction intent not confidently recoverable')
    if np.mean(mask>0)>.22:raise ValueError('caption removal would change too much of the scene')
    phash,signature=duplicate(image,defaults)
    source=np.array(image)
    background=Image.fromarray(cv2.inpaint(source,mask,3,cv2.INPAINT_TELEA))
    output=BytesIO();background.save(output,'PNG');asset=hashlib.sha256(output.getvalue()).hexdigest()
    directory=root()/'template_assets';directory.mkdir(exist_ok=True)
    asset_path=directory/(asset+'.png');existed=asset_path.exists();asset_path.write_bytes(output.getvalue())
    try:
        spec=TemplateSpec.model_validate({'width':image.width,'height':image.height,'layers':[{'type':'asset','box':[0,0,image.width,image.height],'value':asset}]+layers,'defaults':defaults}).model_dump()
        rebuilt=open_image(render(spec,[],defaults)).convert('RGB')
        error=float(np.abs(np.asarray(image.resize((128,128))).astype('float32')-np.asarray(rebuilt.resize((128,128))).astype('float32')).mean())
        if error>12:raise ValueError('caption reconstruction changes source intent layout')
        # All non-caption pixels are preserved in the lossless background asset.
        protected_error=float(np.abs(source.astype('float32')-np.array(background).astype('float32'))[mask==0].mean())
        if protected_error>.1:raise ValueError('protected expression or action changed')
        digest=hashlib.sha256(raw).hexdigest()
        metadata={**metadata,'name':defaults[0][:40], 'min_images':0,'max_images':0,'min_texts':len(defaults),'max_texts':len(defaults),'default_texts':defaults,'tags':metadata.get('tags') or emotion_tags(' '.join(defaults)), 'original_hash':digest,'perceptual_hash':phash,'intent_signature':signature,'conversion':'caption-preserved-v2','intent':{'caption':defaults,'fixed':'original expression, action and scene','replaceable':'edge captions only'},'quality':{'round_trip_mae':round(error,2),'protected_pixel_mae':round(protected_error,3),'ocr_min_confidence':threshold,'observed_min_confidence':min(confidences),'method':'conservative-local-gates'},'quality_score':round(max(0,1-error/12),3)}
        metadata['requires_review']=bool(min(confidences)<.95)
        if publish_result:
            publish('auto_'+digest[:24],metadata,spec)
            return spec
        return spec, metadata
    except Exception:
        if not existed:asset_path.unlink(missing_ok=True)
        raise
