"""CPU portrait framing after segmentation; no downloads or external photo API."""
import threading
import cv2
import numpy as np
from PIL import Image

_local=threading.local()
_foreground_slot=threading.BoundedSemaphore(1)

def detectors():
    if not hasattr(_local,'detectors'):
        _local.detectors=[]
        for name,kind in [('haarcascade_frontalface_default.xml','person'),('haarcascade_profileface.xml','person'),('haarcascade_frontalcatface_extended.xml','animal')]:
            detector=cv2.CascadeClassifier(cv2.data.haarcascades+name)
            if not detector.empty():_local.detectors.append((detector,kind))
    return _local.detectors

def detect_heads(image,*,all_heads=False):
    """Detect on a small neutral-backed image so transparency isn't a black halo."""
    cv2.setNumThreads(2)
    rgba=image.convert('RGBA');background=Image.new('RGBA',rgba.size,'#dddddd');background.alpha_composite(rgba)
    scale=min(1,640/max(image.size));small=background.convert('RGB').resize((max(1,round(image.width*scale)),max(1,round(image.height*scale))))
    gray=cv2.cvtColor(np.asarray(small),cv2.COLOR_RGB2GRAY);gray=cv2.equalizeHist(gray)
    boxes=[]
    for detector,kind in detectors():
        for x,y,w,h in detector.detectMultiScale(gray,1.1,5,minSize=(18,18)):
            boxes.append((kind,tuple(float(v)/scale for v in (x,y,w,h))))
        if boxes and kind=='person' and not all_heads:break
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

def candidate_boxes(image):
    boxes=sorted(detect_heads(image,all_heads=True),key=lambda item:item[1][2]*item[1][3],reverse=True);accepted=[]
    for kind,(x,y,w,h) in boxes:
        if w<=0 or h<=0:continue
        duplicate=False
        for _,(ax,ay,aw,ah) in accepted:
            intersection=max(0,min(x+w,ax+aw)-max(x,ax))*max(0,min(y+h,ay+ah)-max(y,ay))
            if intersection/max(1,min(w*h,aw*ah))>.65:duplicate=True;break
        if not duplicate:accepted.append((kind,(x,y,w,h)))
        if len(accepted)>=12:break
    results=[]
    for index,(kind,(x,y,w,h)) in enumerate(accepted):
        size=min(max(w,h)*(1.85 if kind=='animal' else 1.65),image.width,image.height)
        left=max(0,min(image.width-size,x+w/2-size/2));top=max(0,min(image.height-size,y+h*.45-size/2))
        results.append({'id':str(index),'kind':kind,'box':[left/image.width,top/image.height,size/image.width,size/image.height]})
    return results or foreground_candidates(image)


def foreground_candidates(image):
    """Offer real saliency regions when a small/covered face cannot be detected.

    These are labelled subjects, never claimed to be recognised people. Reuse
    the pinned cutout model at <=320px and admit one such fallback at a time.
    Detection photos/masks are discarded with the request.
    """
    if not _foreground_slot.acquire(False):return []
    try:
        from .subjects import warm_subject_model
        from . import vision
        if not warm_subject_model():return []
        small=image.convert('RGBA');small.thumbnail((320,320))
        mask=(np.asarray(vision.extract(small).getchannel('A'))>100).astype('uint8')
        if not .01<float(mask.mean())<.95:return []
        _,_,stats,_=cv2.connectedComponentsWithStats(mask,8)
        results=[]
        for x,y,w,h,area in sorted(stats[1:],key=lambda row:int(row[4]),reverse=True):
            if area<mask.size*.015:continue
            pad=max(2,round(max(w,h)*.04))
            left=max(0,int(x)-pad);top=max(0,int(y)-pad)
            right=min(small.width,int(x+w)+pad);bottom=min(small.height,int(y+h)+pad)
            results.append({'id':'subject-'+str(len(results)),'kind':'subject','box':[left/small.width,top/small.height,(right-left)/small.width,(bottom-top)/small.height]})
            if len(results)>=6:break
        return results
    except (ValueError,RuntimeError,ImportError):
        return []
    finally:_foreground_slot.release()
