"""Composite a supplied image/cutout in a pre-authored slot; no face detector."""
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

def composite(canvas, source, layer, *, background_prepared=False):
    x,y,w,h=layer.box
    image=ImageOps.exif_transpose(source).convert('RGBA')
    if image.width*image.height>4_000_000:raise FaceInputError('图片过大，请先裁剪或压缩')
    if image.getchannel('A').getbbox() is None:raise FaceInputError('图片为空，请换一张图片')
    # Uploaded photos are not required to contain a detectable frontal face.
    # Transparent input is already processed; preserve its foreground alpha.
    box=image.getchannel('A').getbbox();image=image.crop(box)
    if layer.rotation:image=image.rotate(layer.rotation,resample=Image.Resampling.BICUBIC,expand=True)
    image=ImageOps.fit(image,(w,h),method=Image.Resampling.LANCZOS) if layer.fit=='cover' else ImageOps.contain(image,(w,h),method=Image.Resampling.LANCZOS)
    if layer.tone=='grayscale':
        alpha=image.getchannel('A');image=ImageOps.autocontrast(image.convert('L'),cutoff=1).convert('RGBA');image.putalpha(alpha)
    mask=removal_mask(canvas.size,[layer]);local=mask.crop((x,y,x+w,y+h))
    if not background_prepared:
        # Compatibility only. Newly authored templates repair this offline.
        canvas.paste(prepared_background(canvas,[layer]),(0,0),mask)
    foreground=Image.new('RGBA',(w,h));foreground.alpha_composite(image,((w-image.width)//2,(h-image.height)//2))
    alpha=foreground.getchannel('A').filter(ImageFilter.GaussianBlur(layer.feather))
    alpha=ImageChops.multiply(alpha,local);canvas.paste(foreground,(x,y),alpha)
