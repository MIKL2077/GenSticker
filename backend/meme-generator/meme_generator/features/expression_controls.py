"""Opt-in, bounded source-pixel expression controls for reviewed templates.

The original A/B renderer remains unchanged. Identity geometry has a positive
triangle guard; cartoon eyes/nose/mouth use independent local affine patches.
No template detection, model generation or portrait storage occurs here.
"""
import cv2
import numpy as np
from PIL import Image
from . import expression_math as m


def controlled_points(source,target,strength,domain,controls):
    s=source['n'];t=m.normalized(target);q=s.copy()
    # A single cartoon contour must not drag unrelated inner identity points.
    contour=.15+.20*controls.pose_weight
    q[m.OVAL]=s[m.OVAL]*(1-contour)+t[m.OVAL]*contour
    for group in [m.L_EYE,m.R_EYE]:
        center=s[group].mean(0);local=s[group]-center
        if controls.eye_aperture:
            index=0 if group==m.L_EYE else 1;width=max(np.ptp(local[:,0]),.02)
            ratio=np.clip(controls.eye_aperture[index]*width/max(np.ptp(local[:,1]),.01),.12,2.2)
            local[:,1]*=1-controls.eye_strength+ratio*controls.eye_strength
        q[group]=local+center
    # Keep the person's lips when requested; otherwise transfer opening/curvature
    # at bounded width. Large drawn cavities are a separate disclosed component.
    if controls.mouth!='source':
        sm=s[m.OUTER].mean(0);tm=t[m.OUTER].mean(0)
        sw=max(np.ptp(s[m.OUTER,0]),.05);tw=max(np.ptp(t[m.OUTER,0]),.05)
        for group in [m.OUTER,m.INNER]:
            local=(t[group]-tm)*sw/tw;local[:,1]=np.clip(local[:,1],-.42,.42)
            q[group]=s[group]*(1-strength*.65)+(sm+local)*strength*.65
    if controls.profile:
        # Bounded 2D foreshortening, never synthesize the hidden side.
        q[:,0]*=1-.30*abs(controls.profile)
        q[:,0]+=controls.profile*.12*(q[:,1]-.2)
    # Positive topology matters more than matching impossible cartoon anatomy.
    ids=m.IDS;_,tri=m.triangles(source['p'][ids],source['rgb'].shape[1],source['rgb'].shape[0])
    original=s[ids]
    def signed(points):
        a=points[np.array(tri)];u=a[:,1]-a[:,0];v=a[:,2]-a[:,0];return u[:,0]*v[:,1]-u[:,1]*v[:,0]
    before=signed(original)
    fraction=1.
    for _ in range(12):
        candidate=s+(q-s)*fraction;after=signed(candidate[ids])
        if np.all((np.abs(before)<1e-5)|(after*before>0)):break
        fraction*=.5
    return m.unnormalized(candidate,target).astype('float32')


def transfer_component(original,source_mask,points,destination,group,size,allowed,strength):
    """One local similarity transform, avoiding cross-feature triangulation."""
    sc=points[group].mean(0);dc=destination[group].mean(0)
    a=points[group];b=destination[group]
    # Similarity preserves source expression aspect (wide eyes, tongue, snout).
    width=max(float(np.ptp(a[:,0])),1);target_width=max(float(np.ptp(b[:,0])),1)
    scale=np.clip(target_width/width,.08,8)
    # Eye-line angle is shared across all independently transformed components.
    _,_,sa=m.basis(points);_,_,da=m.basis(destination);rotation=da@sa.T
    linear=rotation*scale;matrix=np.column_stack([linear,dc-linear@sc]).astype('float32')
    color=cv2.warpAffine(original,matrix,size,flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_REFLECT_101)
    alpha=cv2.warpAffine(source_mask.astype('float32')/255,matrix,size,flags=cv2.INTER_LINEAR)
    alpha=cv2.GaussianBlur(alpha,(0,0),.45)*allowed*strength
    return color,np.clip(alpha,0,1)


def render_frame(source,guide,strength,domain,controls):
    tp=guide['p'];base=guide['base'];h,w=base.shape[:2]
    scale=max(1,min(3,300/min(w,h)));W,H=round(w*scale),round(h*scale)
    desired=controlled_points(source,tp,strength,domain,controls)
    matte=source['matte'].copy()
    if controls.lower_face_only:
        yy=np.indices(matte.shape)[0];matte[yy<source['p'][1,1]]=0
    fg,a,folds=m.warp(source['rgb'],matte,source['p'][m.IDS],desired[m.IDS]*scale,(H,W))
    bg=cv2.resize(base,(W,H),interpolation=cv2.INTER_CUBIC)
    allowed=cv2.resize(guide['mask'].astype('float32')/255,(W,H),interpolation=cv2.INTER_NEAREST)
    if domain=='ink':
        gray=cv2.cvtColor(fg,cv2.COLOR_RGB2GRAY).astype('float32');valid=a>.7
        if valid.any():
            lo,hi=np.percentile(gray[valid],[4,85]);contrast=np.clip((gray-lo)*255/max(hi-lo,70),0,255);gray=gray*(1-controls.ink_contrast)+contrast*controls.ink_contrast
        fg=np.repeat(gray.astype('uint8')[...,None],3,2)
    else:
        valid=(a>.9)&(allowed>.5)
        if valid.sum()>20:
            shift=np.clip(np.median(bg[valid],0)-np.median(fg[valid],0),-30,30)*(.25 if domain=='human' else .10)
            fg=np.clip(fg.astype('float32')+shift,0,255).astype('uint8')
    distance=cv2.distanceTransform((a>.35).astype('uint8'),cv2.DIST_L2,3)
    a=np.clip(a,0,1)*np.minimum(1,distance/max(1.5,scale*1.8))*allowed
    a=cv2.GaussianBlur(a,(0,0),max(.4,scale*.35))*allowed
    result=np.clip(fg*a[...,None]+bg*(1-a[...,None]),0,255).astype('uint8')
    components=list(guide.get('components',[]));transferred=[];borrowed=False
    if controls.mouth=='template' or (controls.mouth=='ab' and strength>.8):
        from types import SimpleNamespace
        mask=m.poly((h,w),tp[m.OUTER]);components.append((SimpleNamespace(name='mouth',strength=1),mask))
    groups={'left-eye':m.L_EYE,'right-eye':m.R_EYE,'nose':m.NOSE,'mouth':m.OUTER,'accessory':m.L_EYE+m.R_EYE}
    for component,mask in components:
        if component.strength<=0:continue
        donor,alpha=transfer_component(guide['original'],mask,tp,desired*scale,groups[component.name],(W,H),allowed,component.strength)
        if domain=='ink':donor=cv2.cvtColor(cv2.cvtColor(donor,cv2.COLOR_RGB2GRAY),cv2.COLOR_GRAY2RGB)
        result=np.clip(donor*alpha[...,None]+result*(1-alpha[...,None]),0,255).astype('uint8');transferred.append(component.name);borrowed|=component.name=='mouth'
    if controls.blur:result=cv2.GaussianBlur(result,(0,0),controls.blur*scale)
    if controls.opacity<1:result=np.clip(result*controls.opacity+bg*(1-controls.opacity),0,255).astype('uint8')
    result=cv2.resize(result,(w,h),interpolation=cv2.INTER_AREA);fixed=guide['mask']==0;result[fixed]=guide['original'][fixed]
    error=int(np.abs(result.astype(int)-guide['original'].astype(int))[fixed].max()) if fixed.any() else 0
    return Image.fromarray(result),{'folded_triangles':int(folds),'borrowed_template_mouth_interior':borrowed,'fixed_pixel_max_error':error,'controlled_features':True,'components':transferred,'eye_aperture':controls.eye_aperture,'mouth_control':controls.mouth,'opacity':controls.opacity,'blur':controls.blur}
