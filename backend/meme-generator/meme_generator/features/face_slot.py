"""Composite an input in an authored slot, optionally with portrait geometry."""
from PIL import Image, ImageOps, ImageDraw, ImageFilter, ImageChops
from ..exception import MemeGeneratorException

class FaceInputError(MemeGeneratorException):
    status_code=422

def removal_mask(size, layers):
    mask=Image.new('L',size);draw=ImageDraw.Draw(mask)
    for layer in layers:
        if layer.type!='face':continue
        x,y,w,h=layer.box
        if layer.mask_asset:
            from meme_generator.safe_images import open_image
            from .store import root
            with open_image(root()/'template_assets'/(layer.mask_asset+'.png')) as source:
                if source.size!=(w,h):raise FaceInputError('模板头像遮罩尺寸不匹配')
                local=source.convert('L')
                if local.getbbox() is None:raise FaceInputError('模板头像遮罩为空')
                mask.paste(local,(x,y))
        elif layer.erase_polygon:draw.polygon([(x+px,y+py) for px,py in layer.erase_polygon],fill=255)
        else:draw.ellipse((x,y,x+w-1,y+h-1),fill=255)
        for polygon in layer.protect_polygons:
            draw.polygon([(x+px,y+py) for px,py in polygon],fill=0)
    return mask

def prepared_background(reference, layers):
    import cv2
    import numpy as np
    mask=removal_mask(reference.size,layers)
    cleaned=Image.fromarray(cv2.inpaint(np.asarray(reference.convert('RGB')),np.array(mask),3,cv2.INPAINT_TELEA))
    return cleaned

def composite(canvas, source, layer, *, background_prepared=False, mode='replace', reference=None, fusion_inputs=None):
    if mode not in {'replace','color','seamless','expression'}:raise FaceInputError('请选择有效的融合方式')
    if layer.fusion and mode=='replace':
        from . import face_fusion
        cache={} if fusion_inputs is None else fusion_inputs
        if layer.slot not in cache:cache[layer.slot]=face_fusion.prepare(source)
        if face_fusion.composite(canvas,cache[layer.slot],layer,reference):return
    x,y,w,h=layer.box
    image=ImageOps.exif_transpose(source).convert('RGBA')
    if image.width*image.height>4_000_000:raise FaceInputError('图片过大，请先裁剪或压缩')
    if image.getchannel('A').getbbox() is None:raise FaceInputError('图片为空，请换一张图片')
    # Uploaded photos are not required to contain a detectable frontal face.
    # Transparent input is already processed; preserve its foreground alpha.
    box=image.getchannel('A').getbbox();image=image.crop(box)
    if layer.rotation:image=image.rotate(layer.rotation,resample=Image.Resampling.BICUBIC,expand=True)
    fx,fy,fw,fh=layer.fusion.fallback_box if layer.fusion and layer.fusion.fallback_box else (0,0,w,h)
    image=ImageOps.fit(image,(fw,fh),method=Image.Resampling.LANCZOS) if layer.fit=='cover' else ImageOps.contain(image,(fw,fh),method=Image.Resampling.LANCZOS)
    if layer.tone=='grayscale':
        alpha=image.getchannel('A');image=ImageOps.autocontrast(image.convert('L'),cutoff=1).convert('RGBA');image.putalpha(alpha)
    mask=removal_mask(canvas.size,[layer]);local=mask.crop((x,y,x+w,y+h))
    if not background_prepared:
        # Compatibility only. Newly authored templates repair this offline.
        canvas.paste(prepared_background(canvas,[layer]),(0,0),mask)
    foreground=Image.new('RGBA',(w,h));foreground.alpha_composite(image,(fx+(fw-image.width)//2,fy+(fh-image.height)//2))
    original_alpha=foreground.getchannel('A')
    alpha=ImageChops.multiply(original_alpha,original_alpha.filter(ImageFilter.GaussianBlur(layer.feather)))
    alpha=ImageChops.multiply(alpha,local)
    if mode!='replace':
        import cv2
        import numpy as np
        target=(reference or canvas).convert('RGB').crop((x,y,x+w,y+h))
        pixels=np.asarray(foreground.convert('RGB')).copy()
        original=np.asarray(target).copy()
        valid=np.asarray(alpha)>180
        if valid.sum()>8:
            # Match local lighting without changing the supplied facial geometry.
            src=cv2.cvtColor(pixels,cv2.COLOR_RGB2LAB).astype(np.float32)
            dst=cv2.cvtColor(original,cv2.COLOR_RGB2LAB).astype(np.float32)
            for channel in range(3):
                a=src[:,:,channel][valid];b=dst[:,:,channel][valid]
                gain=np.clip(b.std()/max(a.std(),8),.65,1.4)
                src[:,:,channel]=(src[:,:,channel]-a.mean())*gain+b.mean()
            pixels=cv2.cvtColor(np.clip(src,0,255).astype('uint8'),cv2.COLOR_LAB2RGB)
            if layer.tone=='grayscale':pixels=np.repeat(cv2.cvtColor(pixels,cv2.COLOR_RGB2GRAY)[:,:,None],3,axis=2)
            if mode in {'seamless','expression'} and min(w,h)>=8:
                mask=np.asarray(alpha).copy();mask[mask<32]=0
                # Padding makes slots touching the canvas safe. Place by the
                # mask's bounding rectangle rather than moving an off-centre ROI.
                mask=cv2.copyMakeBorder(mask,2,2,2,2,cv2.BORDER_CONSTANT,value=0)
                src=cv2.copyMakeBorder(pixels,2,2,2,2,cv2.BORDER_REFLECT)
                dst=cv2.copyMakeBorder(original,2,2,2,2,cv2.BORDER_REFLECT)
                bx,by,bw,bh=cv2.boundingRect(mask)
                if bw>2 and bh>2:
                    flag=cv2.MIXED_CLONE if mode=='expression' else cv2.NORMAL_CLONE
                    try:pixels=cv2.seamlessClone(src,dst,mask,(bx+bw//2,by+bh//2),flag)[2:-2,2:-2]
                    except cv2.error:raise FaceInputError('此区域无法融合，请改用自然融合或原图替换')
                if mode=='expression':
                    # An explicit experimental blend, not neural expression
                    # transfer. The original expression retains priority.
                    pixels=cv2.addWeighted(pixels,.58,original,.42,0)
            foreground=Image.fromarray(pixels).convert('RGBA')
        # Feather the slot boundary *inside* the authored mask. Protected hands
        # and props remain bit-for-bit untouched before final GIF quantization.
        radius=max(1,min(5,round(min(w,h)*.035)))
        soft=local.filter(ImageFilter.GaussianBlur(radius))
        alpha=ImageChops.multiply(alpha,soft)
    canvas.paste(foreground,(x,y),alpha)
