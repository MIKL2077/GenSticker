"""CPU portrait framing after segmentation; no downloads or external photo API."""
import threading
import cv2
import numpy as np
from PIL import Image

_local=threading.local()

def detectors():
    if not hasattr(_local,'detectors'):
        _local.detectors=[]
        for name,kind in [('haarcascade_frontalface_default.xml','person'),('haarcascade_profileface.xml','person'),('haarcascade_frontalcatface_extended.xml','animal')]:
            detector=cv2.CascadeClassifier(cv2.data.haarcascades+name)
            if not detector.empty():_local.detectors.append((detector,kind))
    return _local.detectors

def detect_heads(image):
    """Detect on a small neutral-backed image so transparency isn't a black halo."""
    rgba=image.convert('RGBA');background=Image.new('RGBA',rgba.size,'#dddddd');background.alpha_composite(rgba)
    scale=min(1,640/max(image.size));small=background.convert('RGB').resize((max(1,round(image.width*scale)),max(1,round(image.height*scale))))
    gray=cv2.cvtColor(np.asarray(small),cv2.COLOR_RGB2GRAY);gray=cv2.equalizeHist(gray)
    boxes=[]
    for detector,kind in detectors():
        for x,y,w,h in detector.detectMultiScale(gray,1.1,5,minSize=(28,28)):
            boxes.append((kind,tuple(float(v)/scale for v in (x,y,w,h))))
        if boxes and kind=='person':break
    return boxes

def focus_portrait(image,heads=None):
    """Pad around the largest head, preserving hair/ears/chin; otherwise tight subject."""
    heads=detect_heads(image) if heads is None else heads
    if heads:
        kind,(x,y,w,h)=max(heads,key=lambda item:item[1][2]*item[1][3])
        # More space above animal faces retains ears. Clamp without changing center unnecessarily.
        size=max(1,min(round(max(w,h)*(1.85 if kind=='animal' else 1.65)),min(image.size)))
        cx=x+w/2;cy=y+h*(.42 if kind=='animal' else .45)
        left=round(max(0,min(image.width-size,cx-size/2)));top=round(max(0,min(image.height-size,cy-size/2)))
        box=(left,top,left+size,top+size)
        return image.crop(box),{'subject':kind,'framing':'head','focus_box':list(box)}
    alpha=image.getchannel('A') if image.mode=='RGBA' else None
    if alpha is not None and alpha.getextrema()[0]<255:
        bbox=alpha.point(lambda v:255 if v>60 else 0).getbbox()
        if bbox:
            x,y,right,bottom=bbox;pad=max(4,round(max(right-x,bottom-y)*.04))
            box=(max(0,x-pad),max(0,y-pad),min(image.width,right+pad),min(image.height,bottom+pad))
            return image.crop(box),{'framing':'subject','focus_box':list(box)}
    return image,{'framing':'original'}
