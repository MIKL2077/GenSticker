"""Small public previews, cached by recipe version; never caches user photos."""
from io import BytesIO
import hashlib
import threading
import time
from PIL import Image, ImageOps
from fastapi import Response
from .store import root
from meme_generator.safe_images import open_image

REVISION = 'motion-192-v4'
_locks = [threading.Lock() for _ in range(16)]
_prune_lock = threading.Lock()
_last_prune = 0


def prune(directory, current):
    global _last_prune
    if not _prune_lock.acquire(blocking=False):return
    try:
        if time.monotonic()-_last_prune<60:return
        _last_prune=time.monotonic()
        cached=sorted(directory.glob('*.preview'),key=lambda p:p.stat().st_mtime)
        total=sum(p.stat().st_size for p in cached);count=len(cached)
        for old in cached:
            if count<=2048 and total<=128*1024*1024:break
            if old==current:continue
            size=old.stat().st_size;old.unlink(missing_ok=True);total-=size;count-=1
    finally:_prune_lock.release()


def encode(source):
    """Keep the whole loop and timing; bound both dimensions and frame count."""
    frames, durations = [], []
    with open_image(source) as image:
        count = getattr(image, 'n_frames', 1)
        if image.format=='GIF' and count>1 and count<=32 and max(image.size)<=192:
            raw=source.getvalue() if hasattr(source,'getvalue') else source.read_bytes()
            if len(raw)<=64*1024:return raw,'image/gif'
        stride = max(1, (count + 31) // 32)
        for index in range(count):
            image.seek(index)
            duration = max(20, int(image.info.get('duration', 100)))
            if index % stride:
                durations[-1] += duration
                continue
            rgba = image.convert('RGBA');rgba.thumbnail((192,192),Image.Resampling.LANCZOS)
            base = Image.new('RGBA', rgba.size, 'white'); base.alpha_composite(rgba)
            frames.append(base.convert('RGB')); durations.append(duration)
    output = BytesIO()
    if len(frames) == 1:
        frames[0].save(output, 'JPEG', quality=76, optimize=True)
        return output.getvalue(), 'image/jpeg'
    def gif(colors):
        # Shared palette keeps unmoving faces and text stable across frames.
        swatch = Image.new('RGB', (96 * len(frames), 96), 'white')
        for i, frame in enumerate(frames):swatch.paste(ImageOps.fit(frame, (96,96)), (96*i,0))
        palette = swatch.quantize(colors=colors)
        indexed = [f.quantize(palette=palette, dither=Image.Dither.NONE) for f in frames]
        result = BytesIO()
        indexed[0].save(result,'GIF',save_all=True,append_images=indexed[1:],duration=durations,
                        loop=0,disposal=1,optimize=True)
        return result.getvalue()
    raw = gif(128)
    if len(raw)>96*1024:
        frames = [ImageOps.contain(f,(128,128)) for f in frames]
        raw = gif(64)
    if len(raw)>96*1024:
        frames = [ImageOps.contain(f,(96,96)) for f in frames]
        raw = gif(48)
    return raw, 'image/gif'


def response(key, version, loader, requested_version=None):
    digest=hashlib.sha256(f'{REVISION}:{key}:{version}'.encode()).hexdigest()
    directory=root()/'public_previews';directory.mkdir(exist_ok=True)
    with _locks[int(digest[:2],16)%len(_locks)]:
        path=directory/(digest+'.preview')
        if path.is_file():raw=path.read_bytes()
        else:
            raw,_=encode(loader())
            temporary=path.with_suffix('.tmp');temporary.write_bytes(raw);temporary.replace(path)
            # One current preview per key; maintenance also bounds the total cache.
            prune(directory,path)
    immutable=str(requested_version)==str(version)
    return Response(raw,media_type='image/gif' if raw.startswith(b'GIF') else 'image/jpeg',
                    headers={'Cache-Control':'public, max-age=31536000, immutable' if immutable else 'public, max-age=300',
                             'ETag':'"'+digest+'"','X-Preview-Revision':REVISION})


def declared_source(row):
    import json
    from .declarative import TemplateSpec, render
    spec=TemplateSpec.model_validate_json(row['spec'])
    if spec.frames:
        # Reuse an already small, complete source timeline without a lossy
        # decode/re-encode cycle. Authored resampling still uses the frame path.
        first=spec.frames[0]
        if first.asset_format=='gif' and all((f.reference_asset or f.asset)==(first.reference_asset or first.asset) and f.source_index==i for i,f in enumerate(spec.frames)):
            path=root()/'template_assets'/((first.reference_asset or first.asset)+'.gif')
            with open_image(path) as original:
                if getattr(original,'n_frames',1)==len(spec.frames) and max(original.size)<=192:
                    timing=[]
                    for i in range(original.n_frames):original.seek(i);timing.append(max(20,int(original.info.get('duration',100))))
                    if timing==[f.duration_ms for f in spec.frames]:return path
        frames=[];durations=[];decoded={}
        for frame in spec.frames:
            digest=frame.reference_asset or frame.asset
            identity=(digest,frame.asset_format)
            if identity not in decoded:
                with open_image(root()/'template_assets'/(digest+'.'+frame.asset_format)) as source:
                    decoded[identity]=[]
                    for i in range(getattr(source,'n_frames',1)):
                        source.seek(i);decoded[identity].append(source.convert('RGB'))
            frames.append(decoded[identity][frame.source_index]);durations.append(frame.duration_ms)
        result=BytesIO()
        frames[0].save(result,'GIF' if len(frames)>1 else 'PNG',save_all=len(frames)>1,
                       append_images=frames[1:],duration=durations,loop=0)
        result.seek(0);return result
    # Legacy reaction animations need their complete source loop too.
    return render(spec,[Image.new('RGBA',(256,256),'#ffcbad')]*5,preview=not bool(spec.animation_asset))
