"""Execute offline-authored frame plates and replacement slots; no runtime tracking."""
from io import BytesIO

from PIL import Image, ImageOps

from meme_generator.safe_images import open_image
from .store import root


def render_frames(spec, images, texts=None, *, preview=False, face_blend="replace"):
    from .declarative import TemplateSpec, render
    frames, durations = [], []
    decoded = {}
    for frame in spec.frames:
        digest=frame.reference_asset if preview and frame.reference_asset else frame.asset
        cache_key=(digest,frame.asset_format)
        if cache_key not in decoded:
            timeline=[]
            with open_image(root()/'template_assets'/(digest+'.'+frame.asset_format)) as source:
                count=getattr(source,'n_frames',1)
                if count>40 or source.width*source.height*count>8_000_000:raise ValueError('source timeline exceeds frame budget')
                for index in range(frame.source_index+1 if preview else count):
                    source.seek(index)
                    if source.size!=(spec.width,spec.height):raise ValueError('source frame size mismatch')
                    timeline.append(Image.alpha_composite(Image.new('RGBA',source.size,spec.background),source.convert('RGBA')))
            decoded[cache_key]=timeline
        if frame.source_index>=len(decoded[cache_key]):raise ValueError('source frame index missing')
        base=decoded[cache_key][frame.source_index]
        if preview or not frame.layers:
            result=base.convert('RGB')
        else:
            static = TemplateSpec(width=spec.width,height=spec.height,defaults=spec.defaults,
                background_prepared=True,layers=frame.layers)
            # Keep plates lossless until the final image/GIF encoding.
            with open_image(render(static,images,texts,_transparent=True,_base=base,_reference=base,face_blend=face_blend)) as source:
                result=source.convert('RGB')
        frames.append(result)
        durations.append(frame.duration_ms)
        if preview:break
    output=BytesIO()
    if len(spec.frames)==1 or preview:
        frames[0].save(output,'PNG')
    else:
        columns=min(8,len(frames));rows=(len(frames)+columns-1)//columns
        swatch=Image.new('RGB',(128*columns,128*rows),'white')
        for index,frame in enumerate(frames):
            swatch.paste(ImageOps.contain(frame,(128,128)),((index%columns)*128,(index//columns)*128))
        palette=swatch.quantize(colors=256)
        indexed=[frame.quantize(palette=palette,dither=Image.Dither.NONE) for frame in frames]
        indexed[0].save(output,'GIF',save_all=True,append_images=indexed[1:],duration=durations,
                        loop=0,optimize=False,disposal=1,palette=bytes(palette.getpalette()))
        if output.tell()>4*1024*1024:raise ValueError('authored animation output too large')
    output.seek(0)
    return output
