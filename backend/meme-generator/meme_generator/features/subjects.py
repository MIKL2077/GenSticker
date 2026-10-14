"""Optional one-pass foreground extraction, independent of template/person detection."""
from io import BytesIO
from threading import RLock
from PIL import Image, ImageOps
from ..exception import MemeGeneratorException

_initialisation=RLock()


class SubjectError(MemeGeneratorException):
    status_code=422


def extract_subject(raw):
    import numpy as np
    import cv2
    from . import vision
    with Image.open(BytesIO(raw)) as original:
        if original.width*original.height>24_000_000:raise SubjectError('图片过大，请先压缩')
        if getattr(original,'n_frames',1)>1:raise SubjectError('动图请关闭主体提取，或选择一张静态图片')
        image=ImageOps.exif_transpose(original).convert('RGBA')
    image.thumbnail((1280,1280))
    alpha=np.array(image.getchannel('A'))
    if not np.any(alpha>20):raise SubjectError('图片主体为空，请换图或关闭主体提取')
    if np.mean(alpha<240)<.02:
        try:
            with _initialisation:
                if vision._session is None and not vision.warmup(include_emotion=False):
                    raise RuntimeError('local model unavailable')
            image=vision.extract(image)
        except Exception as exc:
            raise SubjectError('主体提取暂不可用；可关闭提取直接使用图片') from exc
    alpha=np.array(image.getchannel('A'))
    mask=(alpha>80).astype('uint8')
    count,labels,stats,_=cv2.connectedComponentsWithStats(mask,connectivity=8)
    if count<=1:raise SubjectError('没有提取到清晰主体，请换图或关闭主体提取')
    largest=1+int(stats[1:,cv2.CC_STAT_AREA].argmax())
    if stats[largest,cv2.CC_STAT_AREA]<image.width*image.height*.01:
        raise SubjectError('主体过小，请先裁剪或关闭主体提取')
    keep=cv2.dilate((labels==largest).astype('uint8'),np.ones((5,5),dtype='uint8'))
    alpha=(alpha*keep).astype('uint8');image.putalpha(Image.fromarray(alpha))
    box=image.getchannel('A').getbbox()
    image=image.crop(box)
    output=BytesIO();image.save(output,'PNG');return output.getvalue()
