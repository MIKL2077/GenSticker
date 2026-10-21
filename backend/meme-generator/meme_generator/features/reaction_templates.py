"""Offline reaction-story authoring: user context plus an intact fixed reaction.

This adapter never claims to replace a face or transfer a source expression.
Source expressions, captions, props and animation stay in their own panel.
"""
from io import BytesIO
import hashlib
from PIL import Image,ImageDraw,ImageOps
from .declarative import TemplateSpec,font

LAYOUTS={
    'reply':{'size':(480,560),'subject':(24,76,250,202),'reaction':(190,304,266,232),'caption':(24,20,432,42),'labels':[(24,286,'我的反应')],'role':'发来一张图片，引出原梗的表情回应'},
    'contrast':{'size':(640,370),'subject':(16,68,296,286),'reaction':(328,68,296,286),'caption':(16,14,608,40),'labels':[],'role':'把上传图片与原梗的反应并列对照'},
    'after':{'size':(440,680),'subject':(24,72,392,250),'reaction':(40,378,360,278),'caption':(24,16,392,40),'labels':[(24,340,'然后，我的状态变成了…')],'role':'上传图片是前因，原梗的动作和表情是后果'},
    'comment':{'size':(500,568),'subject':(24,76,452,220),'reaction':(150,334,310,210),'caption':(24,18,452,42),'labels':[(24,308,'评论区：')],'role':'上传图片作为帖子，原梗作为评论区回应'},
    'caption':{'size':(440,500),'subject':None,'reaction':(20,106,400,372),'caption':(20,18,400,70),'labels':[],'role':'自定义触发场景，保留原梗的完整回应'},
}


def _hash(raw):return hashlib.sha256(raw).hexdigest()


def make_story(raw,*,kind,layout,context,animated=False):
    if kind not in {'image','mixed','text'}:raise ValueError('unknown story input kind')
    layout='caption' if kind=='text' else layout
    if layout not in LAYOUTS or (kind!='text' and layout=='caption'):raise ValueError('unknown story layout')
    design=LAYOUTS[layout];width,height=design['size'];assets={}
    if animated:
        source_hash=_hash(raw);assets[source_hash]=raw
    else:
        with Image.open(BytesIO(raw)) as im:
            if getattr(im,'n_frames',1)>1:raise ValueError('animation must use the motion adapter')
            image=ImageOps.exif_transpose(im).convert('RGBA');image.thumbnail((512,512),Image.Resampling.LANCZOS)
            output=BytesIO();image.save(output,'PNG');source_raw=output.getvalue()
        source_hash=_hash(source_raw);assets[source_hash]=source_raw
    plate=Image.new('RGBA',(width,height));draw=ImageDraw.Draw(plate)
    for x,y,label in design['labels']:draw.text((x,y),label,font=font(20,True),fill='#5d5148')
    if kind=='image':
        x,y,w,h=design['caption'];draw.text((x,y),context,font=font(26,True),fill='#292623')
    else:
        x,y,w,h=design['caption'];draw.rounded_rectangle((x-5,y-4,x+w+5,y+h+5),radius=12,fill='#f6f2eb')
    if design['subject']:
        x,y,w,h=design['subject'];draw.rounded_rectangle((x-3,y-3,x+w+3,y+h+3),radius=12,outline='#e2d7ca',width=2)
    data=BytesIO();plate.save(data,'PNG');plate_hash=_hash(data.getvalue());assets[plate_hash]=data.getvalue()
    layers=[]
    if not animated:layers.append({'type':'asset','box':list(design['reaction']),'value':source_hash,'fit':'contain'})
    if kind!='text':layers.append({'type':'subject','box':list(design['subject']),'slot':0,'fit':'contain'})
    layers.append({'type':'asset','box':[0,0,width,height],'value':plate_hash})
    if kind!='image':layers.append({'type':'text','box':list(design['caption']),'slot':0,'value':context,'font_size':28,'weight':'bold','align':'left','max_lines':2})
    spec=TemplateSpec(width=width,height=height,layers=layers,defaults=[] if kind=='image' else [context],animation_asset=source_hash if animated else '',animation_box=design['reaction'] if animated else None).model_dump()
    return spec,assets,{'fixed_asset_hash':source_hash,'layout':layout,'role':design['role'],'reaction_box':list(design['reaction'])}


def validate_story(spec,metadata):
    value=TemplateSpec.model_validate(spec);intent=metadata.get('intent',{})
    digest=intent.get('fixed_asset_hash','');box=intent.get('reaction_box')
    if not box or len(digest)!=64:raise ValueError('missing original reaction')
    if metadata.get('animated'):
        if value.animation_asset!=digest or list(value.animation_box or [])!=box:raise ValueError('animation source mismatch')
    elif not any(l.type=='asset' and l.value==digest and list(l.box)==box for l in value.layers):raise ValueError('reaction source missing')
    x,y,w,h=box
    for layer in value.layers:
        if layer.type not in {'subject','text'}:continue
        lx,ly,lw,lh=layer.box
        if max(0,min(x+w,lx+lw)-max(x,lx))*max(0,min(y+h,ly+lh)-max(y,ly)):raise ValueError('editable slot overlaps original reaction')
    photo=int(any(l.type=='subject' for l in value.layers));text=int(any(l.type=='text' for l in value.layers))
    if (metadata.get('min_images'),metadata.get('max_images'),metadata.get('min_texts'),metadata.get('max_texts'))!=(photo,photo,text,text):raise ValueError('input contract does not match layers')
    if not photo and not text:raise ValueError('template has no editable context')
