"""Frozen A/B expression math from the evaluated 2026-10-27 lab.

A: identity weighted geometry (.58); B: template mouth component (.94).
Only local CPU landmarks/segmentation, no image synthesis or persistent photos.
Template rigs and clean plates are authored offline. See expression_runtime.py.
"""
import cv2
import numpy as np
from PIL import Image

REVISION = 'cpu-expression-ab-v1'
EXPERIMENT_SHA256 = '6cf3e02a5912b4b1bbce11121f9780cf6a5043700e93947c49e6be94cf286314'

OVAL=[10,338,297,332,284,251,389,356,454,323,361,288,397,365,379,378,400,377,152,148,176,149,150,136,172,58,132,93,234,127,162,21,54,103,67,109]


OUTER=[61,185,40,39,37,0,267,269,270,409,291,375,321,405,314,17,84,181,91,146]


INNER=[78,191,80,81,82,13,312,311,310,415,308,324,318,402,317,14,87,178,88,95]


L_EYE=[33,246,161,160,159,158,157,173,133,155,154,153,145,144,163,7]


R_EYE=[362,398,384,385,386,387,388,466,263,249,390,373,374,380,381,382]


L_BROW=[70,63,105,66,107,55,65,52,53,46]


R_BROW=[336,296,334,293,300,276,283,282,295,285]


NOSE=[1,2,4,5,6,19,94,97,98,168,195,197,326,327]


IDS=list(dict.fromkeys(OVAL+OUTER+INNER+L_EYE+R_EYE+L_BROW+R_BROW+NOSE+[9,8,151,200,201,421,116,345,50,280,101,330,205,425,123,352]))


MODES={'balanced':.58,'expression':.94}


def basis(p):
 a=(p[33]+p[133])/2;b=(p[362]+p[263])/2;delta=b-a;scale=float(np.linalg.norm(delta));u=delta/max(scale,.001);v=np.array([-u[1],u[0]],np.float32)
 return (a+b)/2,scale,np.stack([u,v],1)


def normalized(p):
 center,scale,axes=basis(p);return (p-center)@axes/scale


def unnormalized(p,ref):
 center,scale,axes=basis(ref);return (p*scale)@axes.T+center


def poly(shape,p):
 mask=np.zeros(shape,np.uint8);cv2.fillPoly(mask,[np.rint(p).astype('int32')],255);return mask


def triangles(p,w,h):
 p=np.clip(p,[.1,.1],[w-1.1,h-1.1]).astype('float32');sub=cv2.Subdiv2D((0,0,w,h))
 active=[]
 for i,pt in enumerate(p):
  if all(np.linalg.norm(pt-p[j])>.15 for j in active):sub.insert(tuple(map(float,pt)));active.append(i)
 out=[]
 for t in sub.getTriangleList().reshape(-1,3,2):
  ids=[int(np.argmin(np.linalg.norm(p-q,axis=1))) for q in t]
  if len(set(ids))==3 and all(np.linalg.norm(p[i]-q)<.5 for i,q in zip(ids,t)):out.append(ids)
 return p,out


def warp(rgb,matte,src,dst,shape):
 h,w=shape;_,tris=triangles(src,rgb.shape[1],rgb.shape[0]);dst=np.clip(dst,[.1,.1],[w-1.1,h-1.1]).astype('float32');out=np.zeros((h,w,3),np.uint8);alpha=np.zeros((h,w),np.float32);folds=0
 for ids in tris:
  a=src[ids].astype('float32');b=dst[ids].astype('float32')
  crossa=float((a[1,0]-a[0,0])*(a[2,1]-a[0,1])-(a[1,1]-a[0,1])*(a[2,0]-a[0,0]));crossb=float((b[1,0]-b[0,0])*(b[2,1]-b[0,1])-(b[1,1]-b[0,1])*(b[2,0]-b[0,0]));folds+=crossa*crossb<0 and abs(crossa)>.5 and abs(crossb)>.5
  x,y,bw,bh=cv2.boundingRect(b);x=max(0,x);y=max(0,y);bw=min(bw,w-x);bh=min(bh,h-y)
  if bw<1 or bh<1:continue
  local=b-np.array([x,y],np.float32);M=cv2.getAffineTransform(a,local)
  colors=cv2.warpAffine(rgb,M,(bw,bh),flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT_101)
  ma=cv2.warpAffine(matte,M,(bw,bh),flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
  cover=poly((bh,bw),local)>0;out[y:y+bh,x:x+bw][cover]=colors[cover];alpha[y:y+bh,x:x+bw][cover]=ma[cover]
 return out,alpha,folds


def retarget(source,tp,strength,domain):
 s=source['n'];t=normalized(tp);anatomy_mix=.35 if domain=='human' else .62;q=s*(1-anatomy_mix)+t*anatomy_mix
 # Target contour carries head pose and silhouette; source carries inner identity.
 contour_mix=.82 if domain=='human' else .88
 q[OVAL]=s[OVAL]*(1-contour_mix)+t[OVAL]*contour_mix
 # Eye centers and the nose stay stable. Eyelid expression is weak under glasses.
 for group,a,b in [(L_EYE,33,133),(R_EYE,362,263)]:
  sc=(s[a]+s[b])/2;tc=(t[a]+t[b])/2
  sv=s[group]-sc;tv=t[group]-tc
  sw=np.linalg.norm(s[b]-s[a]);tw=max(np.linalg.norm(t[b]-t[a]),.01)
  mix=strength*(.08 if source['glasses'] else .55)
  q[group]=sv*(1-mix)+tv*(sw/tw)*mix+sc
 for brow,eye in [(L_BROW,L_EYE),(R_BROW,R_EYE)]:
  sc=s[eye].mean(0);tc=t[eye].mean(0)
  q[brow]=(s[brow]-sc)*(1-strength*.68)+(t[brow]-tc)*strength*.68+sc
 # Relative mouth contour/aperture transfers; absolute skull/face dimensions do not.
 sm=(s[61]+s[291])/2;tm=(t[61]+t[291])/2;sw=np.linalg.norm(s[291]-s[61]);tw=max(np.linalg.norm(t[291]-t[61]),.03)
 dest_width=sw*(1-strength*.42)+np.clip(tw,.42,1.2)*strength*.42
 center=sm*(1-anatomy_mix)+tm*anatomy_mix
 for group in [OUTER,INNER]:
  source_rel=(s[group]-sm)/max(sw,.02);target_rel=(t[group]-tm)/tw
  q[group]=(source_rel*(1-strength)+target_rel*strength)*dest_width+center
 # Bound jaw stretch; positive image topology is inspected separately.
 open_delta=float(np.linalg.norm(q[13]-q[14])-np.linalg.norm(s[13]-s[14]))
 for i in OVAL:
  lower=np.clip((s[i,1]-sm[1])/.55,0,1);q[i,1]+=open_delta*.32*lower
 return unnormalized(q,tp).astype('float32')


def render_frame(source,guide,strength,domain):
 rgb=source['rgb'];sp=source['p'];tp=guide['p'];base=guide['base'];h,w=base.shape[:2]
 # A bounded working canvas avoids quantized triangle seams on tiny GIFs.
 scale=max(1,min(3,300/min(w,h)));W,H=round(w*scale),round(h*scale)
 desired=retarget(source,tp,strength,domain);expression_points=desired.copy();full_mouth=strength>.8
 if full_mouth:
  # Compare a second general strategy: keep the person's inner face relatively
  # stable and transplant the original expression-bearing mouth component.
  identity_mouth=retarget(source,tp,.16,domain);desired[OUTER+INNER]=identity_mouth[OUTER+INNER]
 ids=IDS
 fg,a,folds=warp(rgb,source['matte'],sp[ids],desired[ids]*scale,(H,W))
 original=cv2.resize(guide['original'],(W,H),interpolation=cv2.INTER_CUBIC);bg=cv2.resize(base,(W,H),interpolation=cv2.INTER_CUBIC)
 allowed=cv2.resize(guide['mask'].astype('float32')/255,(W,H),interpolation=cv2.INTER_NEAREST)
 # Mouth interior texture is explicitly borrowed from the template, not invented.
 mouth_gap=float(np.linalg.norm(normalized(tp)[13]-normalized(tp)[14]))
 srcgap=float(np.linalg.norm(source['n'][13]-source['n'][14]))
 transferred_interior=False
 if not full_mouth and mouth_gap>.055 and (mouth_gap>srcgap*1.35 or domain=='anime'):
  donor,donor_a,_=warp(guide['original'],np.ones((h,w),np.float32),tp[OUTER+INNER],desired[OUTER+INNER]*scale,(H,W))
  cavity=poly((H,W),desired[INNER]*scale).astype('float32')/255;cavity=cv2.GaussianBlur(cavity,(0,0),max(.5,scale*.35));cavity*=strength
  fg=np.clip(fg*(1-cavity[...,None])+donor*cavity[...,None],0,255).astype('uint8');transferred_interior=True
 # Grayscale ink templates keep white paper and photograph-derived features.
 if domain=='ink':
  gray=cv2.cvtColor(fg,cv2.COLOR_RGB2GRAY).astype('float32');valid=a>.7
  if valid.any():
   lo,hi=np.percentile(gray[valid],[5,80]);gray=np.clip((gray-lo)*255/max(hi-lo,45),0,255)
  fg=np.repeat(gray.astype('uint8')[...,None],3,2)
 else:
  # Match luminance/color gently; full skin-to-fur matching erases facial detail.
  valid=(a>.9)&(allowed>.5)
  if valid.sum()>20:
   shift=np.clip(np.median(bg[valid],0)-np.median(fg[valid],0),-36,36)*(.32 if domain=='human' else .12)
   fg=np.clip(fg.astype('float32')+shift,0,255).astype('uint8')
 # Only the boundary transitions. Core eye/nose/mouth detail is not averaged away.
 hard=(a>.35).astype('uint8');distance=cv2.distanceTransform(hard,cv2.DIST_L2,3)
 edge=max(1.5,scale*(1.7 if domain=='ink' else 2.8));a=np.clip(a,0,1)*np.minimum(1,distance/edge)*allowed
 a=cv2.GaussianBlur(a,(0,0),max(.45,scale*.45))*allowed
 result=np.clip(fg*a[...,None]+bg*(1-a[...,None]),0,255).astype('uint8')
 if full_mouth:
  sc=tp[OUTER].mean(0);dc=expression_points[OUTER].mean(0)
  msrc=np.concatenate([tp[OUTER],tp[INNER],sc+(tp[OUTER]-sc)*1.6])
  mdst=np.concatenate([expression_points[OUTER],expression_points[INNER],dc+(expression_points[OUTER]-dc)*1.6])*scale
  donor,_,_=warp(guide['original'],np.ones((h,w),np.float32),msrc,mdst,(H,W))
  new_mask=poly((H,W),expression_points[OUTER]*scale);new_mask=cv2.dilate(new_mask,np.ones((max(1,round(scale)),max(1,round(scale))),np.uint8));new_mask=(new_mask*allowed).astype('uint8')
  old_mask=poly((H,W),desired[OUTER]*scale);erase=np.maximum(old_mask,new_mask);erase=(erase*allowed).astype('uint8');erase=cv2.dilate(erase,np.ones((3,3),np.uint8));erase=(erase*allowed).astype('uint8')
  foundation=cv2.inpaint(result,erase,3,cv2.INPAINT_TELEA)
  if domain=='ink':donor=cv2.cvtColor(cv2.cvtColor(donor,cv2.COLOR_RGB2GRAY),cv2.COLOR_GRAY2RGB)
  # Poisson integration can wash a flat cartoon mouth into skin color. Preserve
  # its low-frequency interior and soften only the narrow component boundary.
  mouth_a=np.minimum(1,cv2.distanceTransform((new_mask>0).astype('uint8'),cv2.DIST_L2,3)/max(1,scale*.7))
  mouth_a=cv2.GaussianBlur(mouth_a,(0,0),max(.4,scale*.28))*allowed
  result=np.clip(donor*mouth_a[...,None]+foundation*(1-mouth_a[...,None]),0,255).astype('uint8')
  transferred_interior=True
 # All fixed pixels, props, lettering and silhouette are exact before encoding.
 result=cv2.resize(result,(w,h),interpolation=cv2.INTER_AREA);fixed=guide['mask']==0;result[fixed]=guide['original'][fixed]
 return Image.fromarray(result),{'folded_triangles':int(folds),'borrowed_template_mouth_interior':transferred_interior,'fixed_pixel_max_error':int(np.abs(result.astype(int)-guide['original'].astype(int))[fixed].max()) if fixed.any() else 0}

