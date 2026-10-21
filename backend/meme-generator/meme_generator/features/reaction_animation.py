"""Composite a fixed reaction loop with one reusable photo/text overlay."""
from io import BytesIO
from PIL import Image,ImageOps,ImageSequence
from meme_generator.safe_images import open_image
from .store import root


def render_animation(spec,images,texts=None,*,preview=False):
    from .declarative import render
    static=spec.model_copy(update={'animation_asset':'','animation_box':None})
    with open_image(render(static,images,texts,_transparent=True)) as source:
        overlay=source.convert('RGBA')
    x,y,w,h=spec.animation_box
    frames=[];durations=[]
    path=root()/'template_assets'/(spec.animation_asset+'.gif')
    with open_image(path) as animation:
        if not 2<=getattr(animation,'n_frames',1)<=40 or animation.width*animation.height>512*512 or animation.width*animation.height*animation.n_frames>8_000_000:
            raise ValueError('reaction animation exceeds frame budget')
        for frame in ImageSequence.Iterator(animation):
            duration=max(20,min(8000,int(frame.info.get('duration',100))))
            canvas=Image.new('RGBA',(spec.width,spec.height),spec.background)
            reaction=ImageOps.contain(frame.convert('RGBA'),(w,h),Image.Resampling.LANCZOS)
            canvas.alpha_composite(reaction,(x+(w-reaction.width)//2,y+(h-reaction.height)//2))
            canvas.alpha_composite(overlay)
            frames.append(canvas.convert('RGB'));durations.append(duration)
            if preview:break
    output=BytesIO()
    if preview:frames[0].save(output,'JPEG',quality=90)
    else:
        if sum(durations)>8000:raise ValueError('reaction loop too long')
        # One shared palette keeps the user's photo stable across frames and
        # allows GIF delta rectangles to encode only the moving reaction.
        columns=min(8,len(frames));rows=(len(frames)+columns-1)//columns
        swatch=Image.new('RGB',(128*columns,128*rows),'white')
        for index,frame in enumerate(frames):swatch.paste(ImageOps.contain(frame,(128,128)),((index%columns)*128,(index//columns)*128))
        palette=swatch.quantize(colors=256)
        indexed=[frame.quantize(palette=palette,dither=Image.Dither.NONE) for frame in frames]
        indexed[0].save(output,'GIF',save_all=True,append_images=indexed[1:],duration=durations,loop=0,optimize=False,disposal=1,palette=bytes(palette.getpalette()))
        if output.tell()>4*1024*1024:raise ValueError('reaction output too large')
    output.seek(0);return output
