"""Optional one-pass foreground extraction, independent of template/person detection."""
from meme_generator.safe_images import open_input_image
from io import BytesIO
from threading import RLock
from PIL import Image, ImageOps
from ..exception import MemeGeneratorException

_initialisation=RLock()


class SubjectError(MemeGeneratorException):
    status_code=422


def warm_subject_model():
    from . import vision
    with _initialisation:
        return vision._session is not None or vision.warmup(include_emotion=False)


def extract_subject_mask(raw):
    """Return a small, untrimmed alpha mask; the client keeps the original pixels."""
    from . import vision
    with open_input_image(BytesIO(raw)) as original:
        if original.width*original.height>40_000_000:raise SubjectError('图片过大，请先压缩')
        image=ImageOps.exif_transpose(original).convert('RGB').resize((320,320),Image.Resampling.LANCZOS)
    if not warm_subject_model():raise SubjectError('主体提取暂不可用，请稍后再试')
    try:alpha=vision.extract(image).getchannel('A')
    except (ValueError,RuntimeError) as exc:raise SubjectError('这张图边界不太清楚，先框选主体再试试') from exc
    if not alpha.point(lambda v:255 if v>30 else 0).getbbox():raise SubjectError('图片主体为空，请重新框选')
    mask=Image.new('RGBA',(320,320),'white');mask.putalpha(alpha)
    output=BytesIO();mask.save(output,'PNG');return output.getvalue()


def extract_subject(raw):
    import numpy as np
    from . import vision
    with open_input_image(BytesIO(raw)) as original:
        if original.width*original.height>40_000_000:raise SubjectError('图片过大，请先压缩')
        # Static editor works with the first frame of animated formats.
        image=ImageOps.exif_transpose(original).convert('RGBA')
    image.thumbnail((1280,1280))
    alpha=np.array(image.getchannel('A'))
    if not np.any(alpha>20):raise SubjectError('图片主体为空，请换图或关闭主体提取')
    if np.mean(alpha<240)<.02:
        try:
            if not warm_subject_model():
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
