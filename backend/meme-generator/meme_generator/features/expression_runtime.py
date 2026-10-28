"""Request-local A/B adapter for authored slots and native meme functions."""
import hashlib
import logging
import os
from pathlib import Path
import threading
from functools import lru_cache, wraps
from contextlib import contextmanager
from contextvars import ContextVar

import cv2
import numpy as np
from PIL import Image, ImageOps

from . import expression_math as math
from .store import root

SEGMENT_SHA256 = 'c6748b1253a99067ef71f7e26ca71096cd449baefa8f101900ea23016507e0e0'
SEGMENT_URL = 'https://storage.googleapis.com/mediapipe-models/image_segmenter/selfie_multiclass_256x256/float32/latest/selfie_multiclass_256x256.tflite'
_detector = _segmenter = None
_lock = threading.RLock()
_log = logging.getLogger(__name__)
_shared_inputs = ContextVar('expression_inputs', default=None)


@contextmanager
def shared_inputs(cache):
    token=_shared_inputs.set(cache)
    try:yield
    finally:_shared_inputs.reset(token)


def warmup():
    global _detector, _segmenter
    with _lock:
        if _detector is not None and _segmenter is not None:
            return True
        from .face_fusion import MODEL_SHA256
        face = Path(os.getenv('GENSTICKER_FACE_LANDMARK_MODEL', str(root()/'models/face_landmarker-v1.task')))
        segment = Path(os.getenv('GENSTICKER_EXPRESSION_SEGMENT_MODEL', str(root()/'models/selfie_multiclass_256x256.tflite')))
        for path, digest, bound in [(face, MODEL_SHA256, 5_000_000), (segment, SEGMENT_SHA256, 20_000_000)]:
            if not path.is_file():
                return False
            if path.stat().st_size > bound or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError('expression model checksum mismatch')
        if extra := os.getenv('GENSTICKER_FUSION_SITE'):
            import site
            site.addsitedir(extra)
        from mediapipe.tasks import python
        from mediapipe.tasks.python import vision
        detector = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_path=str(face), delegate=python.BaseOptions.Delegate.CPU),
            num_faces=1, output_face_blendshapes=False, min_face_detection_confidence=.4, min_face_presence_confidence=.4))
        try:
            segmenter = vision.ImageSegmenter.create_from_options(vision.ImageSegmenterOptions(
                base_options=python.BaseOptions(model_asset_path=str(segment), delegate=python.BaseOptions.Delegate.CPU),
                output_confidence_masks=True, output_category_mask=False))
        except Exception:
            detector.close()
            raise
        _detector, _segmenter = detector, segmenter
        return True


def close():
    global _detector, _segmenter
    with _lock:
        for model in [_detector, _segmenter]:
            if model is not None:
                model.close()
        _detector = _segmenter = None
    _asset.cache_clear()
    _timeline.cache_clear()
    from .expression_driver import close as close_driver
    close_driver()


def prepare(source):
    """The same source preparation as the frozen experiment, once per request slot."""
    image = ImageOps.exif_transpose(source).convert('RGBA')
    if image.width*image.height > 4_000_000 or image.getchannel('A').getbbox() is None:
        from .face_slot import FaceInputError
        raise FaceInputError('图片过大或为空，请先裁剪或更换图片')
    image.thumbnail((640,640))
    try:
        with _lock:
            if not warmup():
                return None
            import mediapipe as mp
            data = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(np.array(image.convert('RGB'))))
            result = _detector.detect(data)
            if not result.face_landmarks:
                return None
            p = np.array([[p.x*image.width,p.y*image.height] for p in result.face_landmarks[0]],np.float32)
            seg = _segmenter.segment(data)
            conf = np.stack([m.numpy_view().copy().squeeze() for m in seg.confidence_masks],axis=2)
    except (ImportError, OSError, RuntimeError) as exc:
        _log.warning('A/B source preparation unavailable (%s); retaining original slot', type(exc).__name__)
        return None
    face = math.poly((image.height,image.width),p[math.OVAL]).astype('float32')/255
    alpha = np.array(image.getchannel('A'),dtype='float32')/255
    matte = cv2.GaussianBlur(face*np.clip((conf[:,:,1]+conf[:,:,3]+conf[:,:,5])*1.6,0,1)*alpha,(0,0),.6)
    eye_region = math.poly(face.shape,p[[33,70,300,263,425,205]])>0
    accessory = float(np.mean(conf[:,:,5][eye_region])) if eye_region.any() else 0
    return {'supported':True,'image':image,'rgb':np.array(image.convert('RGB')),'p':p,'n':math.normalized(p),
            'matte':matte,'hair':conf[:,:,1]*alpha,'glasses':accessory>.12}


@lru_cache(maxsize=8)
def _asset(directory, digest, mode):
    from meme_generator.safe_images import open_image
    with open_image(Path(directory)/(digest+'.png')) as im:
        return np.array(im.convert(mode))


@lru_cache(maxsize=2)
def _timeline(directory, digest):
    from meme_generator.safe_images import open_image
    frames=[]
    with open_image(Path(directory)/(digest+'.gif')) as im:
        count=getattr(im,'n_frames',1)
        if count>40 or im.width*im.height*count>8_000_000:raise ValueError('expression timeline exceeds budget')
        for i in range(count):
            im.seek(i);frames.append(np.array(im.convert('RGB')))
    return frames


def guide(recipe):
    directory = str(root()/'template_assets')
    original=_timeline(directory,recipe.reference_asset)[recipe.reference_index] if recipe.reference_format=='gif' else _asset(directory,recipe.reference_asset,'RGB')
    patch=_asset(directory,recipe.base_asset,'RGB')
    if recipe.base_box:
        x,y,w,h=recipe.base_box
        if patch.shape[:2]!=(h,w):raise ValueError('expression clean patch size mismatch')
        base=original.copy();base[y:y+h,x:x+w]=patch
    else:base=patch
    authored={'original':original,'base':base,'mask':_asset(directory,recipe.mask_asset,'L'),'p':np.array(recipe.points,np.float32)}
    if recipe.controls:
        authored['components']=[(c,_asset(directory,c.mask_asset,'L')) for c in recipe.controls.components]
        if any(mask.shape!=original.shape[:2] for _,mask in authored['components']):raise ValueError('component guide size mismatch')
    return authored


def composite(canvas, source, recipe, slot, cache):
    key = ('expression',slot)
    if key not in cache:
        cache[key] = prepare(source)
    portrait = cache[key]
    stats = cache.setdefault('expression_stats',[])
    if portrait is None:
        stats.append({'mode':recipe.mode,'applied':False,'reason':'source_face_unavailable'})
        return False
    authored = guide(recipe)
    if authored['base'].shape[:2] != (canvas.height,canvas.width) or authored['mask'].shape != (canvas.height,canvas.width):
        raise ValueError('expression guide size mismatch')
    if recipe.driver:
        from .expression_driver import render_frame
        driven = render_frame(portrait, authored, recipe.driver, cache, slot)
        if driven is None:
            stats.append({'mode': recipe.mode, 'applied': False, 'reason': 'expression_driver_unavailable'})
            return False
        result, metrics = driven
    elif recipe.controls:
        from .expression_controls import render_frame
        result,metrics=render_frame(portrait,authored,.58 if recipe.mode=='A' else .94,recipe.domain,recipe.controls)
    else:
        result, metrics = math.render_frame(portrait,authored,.58 if recipe.mode=='A' else .94,recipe.domain)
    # Restore CURRENT canvas outside support: text/other subjects may already be edited.
    pixels = np.array(canvas)
    allowed = authored['mask']>0
    pixels[allowed,:3] = np.array(result)[allowed]
    pixels[allowed,3] = 255
    canvas.paste(Image.fromarray(pixels))
    stats.append({'mode':recipe.mode,'applied':True,**metrics})
    return True


def native_input(source, recipe, cache, slot):
    """Retarget in the uploaded photo's coordinates before native layout/props run.

    Native scripts retain their own transforms, text, layers, timing and encoders.
    A native template without a measured expression recipe preserves its input.
    """
    if recipe.driver:
        # Reviewed drivers have a declarative-canvas contract only.
        return source
    key = ('expression',slot)
    if key not in cache:
        cache[key] = prepare(source)
    portrait = cache[key]
    if portrait is None:
        cache.setdefault('expression_stats',[]).append({'mode':recipe.mode,'applied':False,'reason':'source_face_unavailable'})
        return source
    authored = guide(recipe)
    target = math.unnormalized(math.normalized(authored['p']),portrait['p']).astype('float32')
    h,w = portrait['rgb'].shape[:2]
    donor, donor_alpha, _ = math.warp(authored['original'],np.ones(authored['mask'].shape,np.float32),
        authored['p'][math.IDS],target[math.IDS],(h,w))
    original = portrait['rgb'].copy()
    original[donor_alpha>.5] = donor[donor_alpha>.5]
    mask = math.poly((h,w),portrait['p'][math.OVAL])
    mask[np.array(portrait['image'].getchannel('A'))==0] = 0
    local = {'original':original,'base':portrait['rgb'],'mask':mask,'p':target}
    if recipe.controls:
        from .expression_controls import render_frame
        local['components']=[]
        for component,component_mask in authored.get('components',[]):
            _,alpha,_=math.warp(authored['original'],component_mask.astype('float32')/255,authored['p'][math.IDS],target[math.IDS],(h,w))
            local['components'].append((component,(np.clip(alpha,0,1)*255).astype('uint8')))
        out,metrics=render_frame(portrait,local,.58 if recipe.mode=='A' else .94,recipe.domain,recipe.controls)
    else:
        out, metrics = math.render_frame(portrait,local,.58 if recipe.mode=='A' else .94,recipe.domain)
    pixels = np.array(portrait['image']);allowed = mask>0
    pixels[allowed,:3] = np.array(out)[allowed]
    cache.setdefault('expression_stats',[]).append({'mode':recipe.mode,'applied':True,**metrics})
    return Image.fromarray(pixels)


def wrap_native(function, policy):
    from .declarative import ExpressionRecipe
    recipe = ExpressionRecipe.model_validate(policy['recipe']) if policy.get('recipe') else None
    @wraps(function)
    def generate(images,texts,args):
        if recipe is None:
            return function(images,texts,args)
        from pil_utils import BuildImage
        shared=_shared_inputs.get()
        cache = {} if shared is None else shared
        adjusted = [BuildImage(native_input(image.image,recipe,cache,i)) for i,image in enumerate(images)]
        return function(adjusted,texts,args)
    return generate
