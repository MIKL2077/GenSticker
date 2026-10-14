"""Bounded local face localisation and compositing, without identity inference."""
from functools import lru_cache
from math import atan2, degrees
from threading import RLock
from PIL import Image, ImageOps, ImageDraw, ImageFilter
import numpy as np
from ..exception import MemeGeneratorException
_detector_lock = RLock()


class FaceInputError(MemeGeneratorException):
    status_code = 422


@lru_cache(maxsize=1)
def detectors():
    import cv2
    face = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    eyes = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_eye.xml')
    if face.empty() or eyes.empty():
        raise FaceInputError('人脸检测暂不可用，请稍后重试')
    return face, eyes


def locate(image):
    import cv2
    image = ImageOps.exif_transpose(image).convert('RGB')
    if image.width * image.height > 4_000_000:
        raise FaceInputError('照片过大，请选择压缩后的单人照片')
    image.thumbnail((900, 900))
    gray = cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2GRAY)
    face_detector, eye_detector = detectors()
    with _detector_lock:
        faces = sorted(face_detector.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=6, minSize=(40,40)), key=lambda r: r[2]*r[3], reverse=True)
    if not faces:
        raise FaceInputError('未找到清晰正面人脸，请换一张单人正面照片')
    x,y,w,h = map(int, faces[0])
    if len(faces)>1 and faces[1][2]*faces[1][3] > w*h*.3:
        raise FaceInputError('检测到多张人脸，请选择只包含一张清晰人脸的照片')
    with _detector_lock:
        eyes = eye_detector.detectMultiScale(gray[y:y+int(h*.65), x:x+w], minNeighbors=5, minSize=(max(8,w//10),max(8,h//10)))
    # Optional eye alignment is bounded; absence of eyes doesn't fabricate landmarks.
    eyes = sorted(eyes, key=lambda r:r[2]*r[3], reverse=True)[:2]
    if len(eyes)==2:
        left,right=sorted([(ex+ew/2,ey+eh/2) for ex,ey,ew,eh in eyes])
        angle=degrees(atan2(right[1]-left[1],right[0]-left[0]))
        if right[0]-left[0] > w*.2 and abs(angle)<=20:
            image=image.rotate(angle,resample=Image.Resampling.BICUBIC,center=(x+w/2,y+h/2))
    crop=(max(0,int(x-w*.22)),max(0,int(y-h*.42)),min(image.width,int(x+w*1.22)),min(image.height,int(y+h*1.12)))
    return image.crop(crop)


def composite(canvas, source, layer):
    import cv2
    x,y,w,h=layer.box
    face=locate(source)
    # Conservative GrabCut initialisation retains the central face and removes
    # portrait background around temples / hair without a paid model.
    fw,fh=face.size
    labels=np.full((fh,fw),cv2.GC_PR_BGD,dtype='uint8')
    cv2.ellipse(labels,(fw//2,int(fh*.52)),(int(fw*.40),int(fh*.48)),0,0,360,cv2.GC_PR_FGD,-1)
    labels[int(fh*.40):int(fh*.80),int(fw*.28):int(fw*.72)]=cv2.GC_FGD
    labels[:2,:]=labels[-2:,:]=labels[:,:2]=labels[:,-2:]=cv2.GC_BGD
    cv2.grabCut(np.asarray(face).copy(),labels,None,np.zeros((1,65)),np.zeros((1,65)),3,cv2.GC_INIT_WITH_MASK)
    keep=((labels==cv2.GC_FGD)|(labels==cv2.GC_PR_FGD)).astype('uint8')*255
    keep=cv2.morphologyEx(keep,cv2.MORPH_CLOSE,np.ones((3,3),dtype='uint8'))
    source_alpha=Image.fromarray(keep)
    face=ImageOps.fit(face,(w,h),method=Image.Resampling.LANCZOS)
    source_alpha=ImageOps.fit(source_alpha,(w,h),method=Image.Resampling.LANCZOS)
    if layer.tone=='grayscale':
        face=ImageOps.autocontrast(ImageOps.grayscale(face),cutoff=1).convert('RGB')
    erase=Image.new('L',canvas.size)
    shape=ImageDraw.Draw(erase)
    polygon=[(x+px,y+py) for px,py in layer.erase_polygon]
    if polygon:shape.polygon(polygon,fill=255)
    else:shape.ellipse((x,y,x+w-1,y+h-1),fill=255)
    # Remove the old head before blending, avoiding double eyes and dog ears.
    original=np.asarray(canvas.convert('RGB'))
    cleaned=Image.fromarray(cv2.inpaint(original,np.array(erase),3,cv2.INPAINT_TELEA)).convert('RGBA')
    canvas.paste(cleaned,(0,0),erase)
    alpha=Image.new('L',(w,h));draw=ImageDraw.Draw(alpha)
    draw.ellipse((3,2,w-4,h-3),fill=255)
    from PIL import ImageChops
    alpha=ImageChops.multiply(alpha,source_alpha).filter(ImageFilter.GaussianBlur(layer.feather))
    # The compositor changes pixels only in its declared region.
    local_erase=erase.crop((x,y,x+w,y+h))
    alpha=ImageChops.multiply(alpha,local_erase)
    canvas.paste(face,(x,y),alpha)
