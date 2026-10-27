"""CPU portrait-to-character fusion. Model inference is once per input, not frame.

The tiny public landmark model locates geometry only. Identity pixels come from
our input; scene/fur/occlusion comes from reviewed local template recipes. No
image synthesis, expression invention, network access or persistent photo cache.
"""
from dataclasses import dataclass
import hashlib
import logging
import os
from pathlib import Path
import threading

import cv2
import numpy as np
from PIL import Image, ImageOps

MODEL_SHA256 = '64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff'
MODEL_URL = 'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task'
REVISION = 'cpu-character-v1'
_detector = None
_lock = threading.RLock()
_log = logging.getLogger(__name__)
# Clockwise face oval, including the real chin; never include the shirt.
OVAL = [10,338,297,332,284,251,389,356,454,323,361,288,397,365,379,378,400,377,
        152,148,176,149,150,136,172,58,132,93,234,127,162,21,54,103,67,109]


@dataclass
class Portrait:
    pixels: np.ndarray
    alpha: np.ndarray
    points: np.ndarray
    face_alpha: np.ndarray | None = None


def warmup():
    global _detector
    with _lock:
        if _detector is not None:
            return True
        from .store import root
        path = Path(os.getenv('GENSTICKER_FACE_LANDMARK_MODEL', str(root()/'models/face_landmarker-v1.task')))
        if not path.is_file():
            return False
        if path.stat().st_size > 5_000_000 or hashlib.sha256(path.read_bytes()).hexdigest() != MODEL_SHA256:
            raise ValueError('face landmark model checksum mismatch')
        # Optional dependency overlay keeps the existing API/worker OpenCV and
        # NumPy installations intact on the CPU host. New installations can
        # simply install deploy/requirements-fusion.txt in their main venv.
        extra=os.getenv('GENSTICKER_FUSION_SITE')
        if extra:
            import site
            site.addsitedir(extra)
        from mediapipe.tasks import python
        from mediapipe.tasks.python import vision
        _detector = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
            base_options=python.BaseOptions(model_asset_path=str(path),delegate=python.BaseOptions.Delegate.CPU),
            num_faces=1, output_face_blendshapes=False, output_facial_transformation_matrixes=False))
        return True


def close():
    global _detector
    with _lock:
        if _detector is not None:
            _detector.close()
            _detector=None


def prepare(source):
    """Private request-local portrait. Unsupported inputs use existing paste mode."""
    image = ImageOps.exif_transpose(source).convert('RGBA')
    if image.width*image.height > 4_000_000 or image.getchannel('A').getbbox() is None:
        from .face_slot import FaceInputError
        raise FaceInputError('图片过大或为空，请先裁剪或更换图片')
    image.thumbnail((512,512),Image.Resampling.LANCZOS)
    try:
        with _lock:
            if not warmup():
                return None
            import mediapipe as mp
            result = _detector.detect(mp.Image(image_format=mp.ImageFormat.SRGB,
                data=np.ascontiguousarray(np.asarray(image.convert('RGB')))))
    except (ImportError, OSError, RuntimeError):
        _log.warning('portrait locator unavailable; retaining authored image slot')
        return None
    if not result.face_landmarks:
        return None
    width,height = image.size
    points = np.array([[p.x*width,p.y*height] for p in result.face_landmarks[0]],np.float32)
    left=(points[33]+points[133])/2;right=(points[263]+points[362])/2
    distance=float(np.linalg.norm(right-left))
    if distance < 8:
        return None
    u=(right-left)/distance;v=np.array([-u[1],u[0]],np.float32);mid=(left+right)/2
    def at(x,y): return mid+distance*(x*u+y*v)
    anchors=np.array([left,right,points[1],(points[13]+points[14])/2,points[152],
        points[234],points[454],points[10],at(0,-2),at(-1.25,-1.3),at(1.9,-1.3),
        points[172],points[397],at(-1.05,.1),at(1.9,.1)],np.float32)
    matte=np.zeros((height,width),np.uint8)
    cv2.fillPoly(matte,[np.rint(points[OVAL]).astype('int32')],255)
    face_matte=matte.copy()
    hair=np.array([at(-1.05,.1),at(-1.25,-1.3),at(-.65,-1.9),at(0,-2),at(.8,-1.85),
        at(1.9,-1.3),at(1.9,.1),points[454],points[10],points[234]])
    cv2.fillPoly(matte,[np.rint(hair).astype('int32')],255)
    # Glasses can extend beyond the face oval. Keep them intact inside the head.
    glasses=np.array([at(-1.2,-.45),at(1.25,-.45),at(1.25,.5),at(-1.2,.5)])
    cv2.fillPoly(matte,[np.rint(glasses).astype('int32')],255)
    cv2.fillPoly(face_matte,[np.rint(glasses).astype('int32')],255)
    yy,xx=np.indices((height,width))
    below_chin=(xx-points[152,0])*v[0]+(yy-points[152,1])*v[1] > -distance*.06
    matte[below_chin]=0;face_matte[below_chin]=0
    matte=cv2.GaussianBlur(matte,(0,0),max(.5,distance*.015)).astype('float32')/255
    matte*=np.asarray(image.getchannel('A'),dtype='float32')/255
    face_matte=cv2.GaussianBlur(face_matte,(0,0),max(.5,distance*.015)).astype('float32')/255
    face_matte*=np.asarray(image.getchannel('A'),dtype='float32')/255
    return Portrait(np.asarray(image.convert('RGB')).copy(),matte,anchors,face_matte)


def triangulate(points, width, height):
    subdiv=cv2.Subdiv2D((0,0,width,height))
    for point in points:
        subdiv.insert(tuple(map(float,point)))
    triangles=[]
    for triangle in subdiv.getTriangleList().reshape(-1,3,2):
        ids=[int(np.argmin(np.linalg.norm(points-p,axis=1))) for p in triangle]
        if len(set(ids))==3 and all(np.linalg.norm(points[i]-p)<.5 for i,p in zip(ids,triangle)):
            triangles.append(ids)
    return triangles


def multiband(foreground, background, alpha, levels=3):
    ga=[foreground.astype('float32')];gb=[background.astype('float32')];gm=[alpha.astype('float32')]
    levels=min(levels,max(0,int(np.log2(min(alpha.shape)))-3))
    for _ in range(levels):
        ga.append(cv2.pyrDown(ga[-1]));gb.append(cv2.pyrDown(gb[-1]));gm.append(cv2.pyrDown(gm[-1]))
    out=ga[-1]*gm[-1][...,None]+gb[-1]*(1-gm[-1][...,None])
    for i in range(levels-1,-1,-1):
        h,w=ga[i].shape[:2]
        a=ga[i]-cv2.pyrUp(ga[i+1],dstsize=(w,h));b=gb[i]-cv2.pyrUp(gb[i+1],dstsize=(w,h))
        out=cv2.pyrUp(out,dstsize=(w,h))+a*gm[i][...,None]+b*(1-gm[i][...,None])
    return np.clip(out,0,255).astype('uint8')


def composite(canvas, portrait, layer, reference=None):
    """Warp identity pixels into a measured character head, then restore props."""
    if portrait is None:
        return False
    from .face_slot import removal_mask
    recipe=layer.fusion
    x,y,w,h=layer.box
    # Work at >=256px internally: small 120px memes otherwise lose features at
    # triangle boundaries. One bounded ROI, independent of upload resolution.
    scale=max(1,min(3,256/min(w,h)))
    width,height=round(w*scale),round(h*scale)
    left,right=np.array(recipe.eyes,np.float32)*scale
    src=portrait.points
    mid=(src[0]+src[1])/2;delta=src[1]-src[0]
    upright=np.array([-delta[1],delta[0]])
    target_delta=right-left;target_up=np.array([-target_delta[1],target_delta[0]])
    matrix=cv2.getAffineTransform(np.array([src[0],src[1],mid+upright],np.float32),
        np.array([left,right,(left+right)/2+target_up],np.float32))
    points=cv2.transform(src[None],matrix)[0]
    # Hair fits between the character's ears; real lower-face geometry is kept.
    if recipe.hair:
        for index,point in zip([7,8,9,10,13,14],recipe.hair):points[index]=np.array(point)*scale
    # Optional authored mouth/chin anchors reproduce motion without framewise
    # face detection. Do not blend old eyes into the donor (double-eye ghosting).
    if recipe.mouth is not None:points[3]=np.array(recipe.mouth)*scale
    if recipe.chin is not None:points[4]=np.array(recipe.chin)*scale
    points[:,0]=np.clip(points[:,0],.1,width-1.1);points[:,1]=np.clip(points[:,1],.1,height-1.1)
    if min(np.linalg.norm(points[a]-points[b]) for a in range(len(points)) for b in range(a)) < .1:
        return False
    warped=np.zeros((height,width,3),np.uint8);alpha=np.zeros((height,width),np.float32)
    source_alpha=portrait.alpha if recipe.include_hair or portrait.face_alpha is None else portrait.face_alpha
    # Affine only the triangle ROI, instead of repeatedly allocating a full
    # canvas for every triangle. Also prevents reflected clothing/background.
    for ids in triangulate(points,width,height):
        a=src[ids].astype('float32');b=points[ids].astype('float32')
        bx,by,bw,bh=cv2.boundingRect(b);bx=max(0,bx);by=max(0,by);bw=min(bw,width-bx);bh=min(bh,height-by)
        if bw<1 or bh<1:continue
        local=b-np.array([bx,by],np.float32)
        transform=cv2.getAffineTransform(a,local)
        rgb=cv2.warpAffine(portrait.pixels,transform,(bw,bh),flags=cv2.INTER_CUBIC,borderMode=cv2.BORDER_REFLECT_101)
        matte=cv2.warpAffine(source_alpha,transform,(bw,bh),flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
        mask=np.zeros((bh,bw),np.uint8);cv2.fillConvexPoly(mask,np.rint(local).astype('int32'),1)
        select=mask>0;warped[by:by+bh,bx:bx+bw][select]=rgb[select];alpha[by:by+bh,bx:bx+bw][select]=matte[select]
    if not np.any(alpha>.5):return False
    # Extend color into empty margins before pyramids so black padding cannot
    # contaminate hair/skin edges. No reconstruction of template occurs here.
    outside=(alpha<.1).astype('uint8')
    _,labels=cv2.distanceTransformWithLabels(outside,cv2.DIST_L2,5,labelType=cv2.DIST_LABEL_PIXEL)
    colors=warped[outside==0]
    warped[outside>0]=colors[np.clip(labels[outside>0]-1,0,len(colors)-1)]
    radius=max(1,recipe.edge*scale)
    alpha*=np.minimum(1,cv2.distanceTransform((alpha>.5).astype('uint8'),cv2.DIST_L2,3)/radius)
    alpha=cv2.GaussianBlur(alpha,(0,0),max(.5,scale*.65))
    local_mask=removal_mask(canvas.size,[layer]).crop((x,y,x+w,y+h))
    allowed=np.asarray(local_mask.resize((width,height),Image.Resampling.NEAREST),dtype='float32')/255
    alpha*=allowed
    base=np.asarray(canvas.convert('RGB').crop((x,y,x+w,y+h)).resize((width,height),Image.Resampling.LANCZOS))
    if layer.tone=='grayscale' or recipe.style=='photocopy':
        gray=cv2.cvtColor(warped,cv2.COLOR_RGB2GRAY)
        if recipe.style=='photocopy':
            region=gray[alpha>.8]
            if region.size:
                lo,hi=np.percentile(region,[8,68])
                gray=np.clip((gray.astype('float32')-lo)*255/max(hi-lo,25),0,255).astype('uint8')
        warped=cv2.cvtColor(gray,cv2.COLOR_GRAY2RGB)
    # Match only part of the lighting. Full Poisson/color matching washes out
    # skin and sunglasses against white fur, making identity less recognizable.
    if recipe.color_match:
        valid=alpha>.9
        if valid.sum()>8:
            offset=np.clip(base[valid].mean(0)-warped[valid].mean(0),-45,45)*recipe.color_match
            warped=np.clip(warped.astype('float32')+offset,0,255).astype('uint8')
    result=multiband(warped,base,alpha,recipe.pyramid_levels)
    result[alpha<.001]=base[alpha<.001]
    output=Image.fromarray(result).resize((w,h),Image.Resampling.LANCZOS)
    # A hard final support gate restores *all* authored fixed pixels, even after
    # pyramid filtering/resampling; paws and captions cannot be painted over.
    support=Image.fromarray((alpha*255).astype('uint8')).resize((w,h),Image.Resampling.LANCZOS)
    support=np.minimum(np.asarray(support),np.asarray(local_mask))
    exact=np.asarray(canvas.convert('RGB').crop((x,y,x+w,y+h))).copy()
    changed=np.asarray(output);select=support>0;exact[select]=changed[select]
    canvas.paste(Image.fromarray(exact).convert('RGBA'),(x,y))
    return True
