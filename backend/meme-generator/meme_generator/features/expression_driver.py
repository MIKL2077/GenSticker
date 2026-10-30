"""Frozen v1 drivers plus opt-in, per-template v2/v3 review candidates.

GANimation performs 128px ONNX CPU inference with a pinned local model. A single
process-wide lock serializes inference; portrait/crop/state caches belong to the
request or nine-result job, never a global cache. No downloading or photo files.
"""
import hashlib
import logging
import math
import os
from pathlib import Path
import threading

import cv2
import numpy as np
from PIL import Image

from . import expression_math as m
from .store import root

MODEL_FILENAME = 'ganimation-emotionnet-v1.onnx'
MODEL_SHA256 = 'e4ceefd1c354a1e13a1d46e322108aeb5024d846ee7536468d19aca3f51b6f46'
MODEL_MAX_BYTES = 36_000_000
AU_ORDER = (1, 2, 4, 5, 6, 7, 9, 10, 12, 14, 15, 17, 20, 23, 25, 26, 45)
_lock = threading.RLock()
_session = None
_log = logging.getLogger(__name__)


def warmup():
    global _session
    with _lock:
        if _session is not None:
            return True
        path = Path(os.getenv('GENSTICKER_EXPRESSION_DRIVER_MODEL', str(root() / 'models' / MODEL_FILENAME)))
        if not path.is_file():
            return False
        if path.stat().st_size > MODEL_MAX_BYTES or hashlib.sha256(path.read_bytes()).hexdigest() != MODEL_SHA256:
            raise ValueError('expression driver model checksum mismatch')
        if extra := os.getenv('GENSTICKER_EXPRESSION_DRIVER_SITE'):
            import site
            site.addsitedir(extra)
        import onnxruntime as ort
        options = ort.SessionOptions()
        options.intra_op_num_threads = options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        options.add_session_config_entry('session.intra_op.allow_spinning', '0')
        _session = ort.InferenceSession(str(path), options, providers=['CPUExecutionProvider'])
        return True


def close():
    global _session
    with _lock:
        _session = None


def align(source):
    points = source['p']
    anchors = np.array([points[m.L_EYE].mean(0), points[m.R_EYE].mean(0), points[m.OUTER].mean(0)], np.float32)
    matrix = cv2.getAffineTransform(anchors, np.array([[42, 46], [86, 46], [64, 85]], np.float32))
    rgb = cv2.warpAffine(source['rgb'], matrix, (128, 128), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT_101)
    points = points @ matrix[:, :2].T + matrix[:, 2]
    matte = cv2.warpAffine(source['matte'], matrix, (128, 128), flags=cv2.INTER_LINEAR)
    return {'rgb': rgb, 'p': points.astype('float32'), 'matte': matte}


def geometric(points, values):
    aus = dict(zip(AU_ORDER, values))
    desired = points.copy()
    for eye in [m.L_EYE, m.R_EYE]:
        center = points[eye].mean(0)
        aperture = np.clip(1 - aus[45] * .90 + aus[5] * .22 - aus[7] * .15, .10, 1.2)
        desired[eye, 1] = center[1] + (points[eye, 1] - center[1]) * aperture
    for brow in [m.L_BROW, m.R_BROW]:
        desired[brow, 1] -= (aus[1] + aus[2]) * 1.6
        desired[brow, 1] += aus[4] * 1.2
    center = points[m.OUTER].mean(0)
    for group in [m.OUTER, m.INNER]:
        desired[group, 1] = center[1] + (points[group, 1] - center[1]) * (1 + .7 * aus[26] + .35 * aus[25])
    desired[[61, 291], 1] -= aus[12] * 2
    desired[[61, 291], 1] += aus[15] * 1.5
    return desired


def deform(rgb, points, desired):
    anchors = np.array([[0, 0], [64, 0], [127, 0], [0, 64], [127, 64], [0, 127], [64, 127], [127, 127]], np.float32)
    before = np.vstack([points[m.IDS], anchors]).astype('float32')
    after = np.vstack([desired[m.IDS], anchors]).astype('float32')
    out, alpha, folds = m.warp(rgb, np.ones(rgb.shape[:2], np.float32), before, after, rgb.shape[:2])
    if folds:
        raise ValueError('expression driver mesh folded')
    out[alpha < .5] = rgb[alpha < .5]
    return out


def eye_geometry(rgb, points, values, gaze_x=0):
    """Opt-in v2: monotone eyelid remap of the person's own texture.

    Each vertical scanline maps a narrow eyelid band into a bounded aperture,
    then joins the unchanged surrounding face. No template feature pixels or
    generated eye/teeth texture. Gaze is a small interior texture displacement,
    not a reconstructed eyeball or a guarantee for obscured eyes/glasses.
    """
    aus=dict(zip(AU_ORDER,values))
    # Preserve the frozen v1 math. Stronger inner-brow slant is v2-only.
    desired=geometric(points,values)
    for group in [m.L_EYE,m.R_EYE]:desired[group]=points[group]
    for brow in [m.L_BROW,m.R_BROW]:
        center=points[brow].mean(0)
        inner=1-np.clip(np.abs(points[brow,0]-64)/28,0,1)
        desired[brow,1]+=aus[4]*(inner*3.5-1.0)
        desired[brow,0]+=(64-center[0])*aus[4]*.025
    out=deform(rgb,points,desired) if np.any(desired!=points) else rgb.copy()
    height,width=out.shape[:2]
    yy,xx=np.mgrid[:height,:width].astype('float32')
    for group in [m.L_EYE,m.R_EYE]:
        eye=points[group];cx,cy=eye.mean(0)
        half_width=max(3,float(np.ptp(eye[:,0]))*.6)
        radius=max(1.8,float(np.ptp(eye[:,1]))*.65)
        outside=max(radius*3.2,8)
        taper=np.maximum(0,1-((xx-cx)/half_width)**2)**2
        aperture=np.clip(1-aus[45]*.97+aus[5]*.8-aus[7]*.45,.035,1.8)
        scale=1+(aperture-1)*taper
        band=radius*scale;dy=yy-cy;distance=np.abs(dy)
        mapped=np.where(distance<band,distance/scale,
            radius+(distance-band)*(outside-radius)/np.maximum(outside-band,.1))
        map_y=np.where(distance<outside,cy+np.sign(dy)*mapped,yy).astype('float32')
        before_eye=out.copy()
        edited=cv2.remap(out,xx,map_y,cv2.INTER_CUBIC,borderMode=cv2.BORDER_REFLECT_101)
        # Restrict the warp to the eyelid socket. Dark frame/eyelash pixels
        # outside the original eyelid are protected, rather than stretching
        # an entire pair of glasses with the eye aperture.
        eye_polygon=m.poly((height,width),eye)
        protected=cv2.dilate(eye_polygon,np.ones((3,3),np.uint8))==0
        protected&=cv2.cvtColor(before_eye,cv2.COLOR_RGB2GRAY)<125
        blend=np.clip(1-((xx-cx)/half_width)**2-((yy-cy)/max(radius*2,4))**2,0,1)
        blend=np.minimum(1,blend*3);blend[protected]=0
        out=np.clip(edited*blend[...,None]+before_eye*(1-blend[...,None]),0,255).astype('uint8')
        if gaze_x:
            inside=m.poly((height,width),eye).astype('float32')/255
            inside=cv2.GaussianBlur(inside,(0,0),.65)
            shift=gaze_x*float(np.ptp(eye[:,0]))
            out=cv2.remap(out,xx-shift*inside,yy,cv2.INTER_CUBIC,borderMode=cv2.BORDER_REFLECT_101)
    return out


def paste(rgb, portrait, guide):
    points, target = portrait['p'], guide['p']
    eyes = np.array([points[m.L_EYE].mean(0), points[m.R_EYE].mean(0)], np.float32)
    target_eyes = np.array([target[m.L_EYE].mean(0), target[m.R_EYE].mean(0)], np.float32)
    before, after = eyes[1] - eyes[0], target_eyes[1] - target_eyes[0]
    scale = float(np.linalg.norm(after) / max(np.linalg.norm(before), .01))
    angle = math.atan2(after[1], after[0]) - math.atan2(before[1], before[0])
    rotation = np.array([[math.cos(angle), -math.sin(angle)], [math.sin(angle), math.cos(angle)]]) * scale
    matrix = np.column_stack([rotation, target_eyes.mean(0) - rotation @ eyes.mean(0)])
    h, w = guide['original'].shape[:2]
    foreground = cv2.warpAffine(rgb, matrix, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT_101)
    matte = cv2.warpAffine(portrait['matte'], matrix, (w, h), flags=cv2.INTER_LINEAR)
    allowed = guide['mask'].astype('float32') / 255
    edge = cv2.distanceTransform(((matte > .2) & (allowed > .5)).astype('uint8'), cv2.DIST_L2, 3)
    alpha = np.clip(matte, 0, 1) * np.minimum(1, edge / max(1.5, scale * 2)) * allowed
    alpha = cv2.GaussianBlur(alpha, (0, 0), max(.5, scale * .4)) * allowed
    valid = alpha > .85
    if valid.sum() > 30:
        shift = np.clip(np.median(guide['base'][valid], 0) - np.median(foreground[valid], 0), -30, 30) * .15
        foreground = np.clip(foreground.astype('float32') + shift, 0, 255)
    out = np.clip(foreground * alpha[..., None] + guide['base'] * (1 - alpha[..., None]), 0, 255).astype('uint8')
    fixed = guide['mask'] == 0
    out[fixed] = guide['original'][fixed]
    return out


def local_mouth(generated, portrait, values):
    """Restrict learned editing to the person's mouth; keep upper-face texture."""
    points=portrait['p'];base=eye_geometry(portrait['rgb'],points,values)
    center=points[m.OUTER].mean(0);width=max(18,float(np.ptp(points[m.OUTER,0]))*.9)
    height=max(10,float(np.ptp(points[m.OUTER,1]))*.8+float(values[15])*8)
    yy,xx=np.mgrid[:128,:128].astype('float32')
    center_y=center[1]+float(values[15])*4
    distance=((xx-center[0])/width)**2+((yy-center_y)/height)**2
    blend=np.clip((1-distance)*4,0,1)
    # Keep the nose and glasses, including their learned reconstruction errors,
    # outside the permitted edit instead of accepting a full-face GAN result.
    blend[yy<center[1]-max(5,float(np.ptp(points[m.OUTER,1]))*.65)]=0
    return np.clip(generated*blend[...,None]+base*(1-blend[...,None]),0,255).astype('uint8')


def render_frame(source, guide, driver, cache, slot):
    """Return None for missing optional infrastructure; use the normal slot fallback."""
    with _lock:
        if driver.method in {'ganimation-emotionnet-v1','ganimation-mouth-eye-v3'}:
            try:
                if not warmup():
                    return None
            except (ImportError, OSError, RuntimeError) as exc:
                _log.warning('reviewed expression model unavailable (%s)', type(exc).__name__)
                return None
        key = ('expression-driver-portrait', slot)
        if key not in cache:
            cache[key] = align(source)
        portrait = cache[key]
        values = np.array(driver.aus, np.float32)
        key = ('expression-driver-state', slot, driver.method, values.tobytes(), driver.gaze_x)
        generated = key not in cache
        if generated:
            if driver.method == 'geometry-v1':
                rgb = deform(portrait['rgb'], portrait['p'], geometric(portrait['p'], values))
            elif driver.method == 'geometry-eye-v2':
                rgb = eye_geometry(portrait['rgb'], portrait['p'], values, driver.gaze_x)
            else:
                tensor = (portrait['rgb'].astype('float32') / 127.5 - 1).transpose(2, 0, 1)[None].copy()
                rgb = _session.run(None, {'image': tensor, 'aus': values[None]})[0]
                if rgb.shape != (1, 3, 128, 128) or not np.isfinite(rgb).all():
                    raise ValueError('invalid expression model output')
                rgb = np.clip((rgb[0].transpose(1, 2, 0) + 1) * 127.5, 0, 255).astype('uint8')
                if driver.method=='ganimation-mouth-eye-v3':rgb=local_mouth(rgb,portrait,values)
            cache[key] = rgb
        out = paste(cache[key], portrait, guide)
        return Image.fromarray(out), {'driver': driver.method, 'driver_state_generated': generated,
                                     'folded_triangles': 0, 'borrowed_template_mouth_interior': False,
                                     'fixed_pixel_max_error': 0}
