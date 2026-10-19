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
        if original.width*original.height>40_000_000:raise SubjectError('图片过大，请先压缩')
        # Static editor works with the first frame of animated formats.
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
    if not np.any(alpha>30):raise SubjectError('这张图边界不太清楚，先框选主体再试试，原图仍保留')
    # Preserve multiple people, pets and detached details; no largest-person veto.
    box=image.getchannel('A').getbbox()
    if box:image=image.crop(box)
    output=BytesIO();image.save(output,'PNG');return output.getvalue()
