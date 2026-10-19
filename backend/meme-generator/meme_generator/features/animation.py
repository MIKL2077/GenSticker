"""Keep animated template results animated; small previews retain timing."""
import math
from io import BytesIO
from PIL import Image,ImageSequence

def gif_frames(original,edge=192,max_frames=40):
    if original.n_frames>240 or original.width*original.height>8_000_000:raise ValueError('animated result too large')
    stride=max(1,math.ceil(original.n_frames/max_frames));frames=[];durations=[]
    for index,frame in enumerate(ImageSequence.Iterator(original)):
        duration=max(20,min(10000,int(frame.info.get('duration',100))))
        if index%stride==0:
            image=frame.convert('RGBA');image.thumbnail((edge,edge),Image.Resampling.LANCZOS)
            background=Image.new('RGBA',image.size,'white');background.alpha_composite(image)
            frames.append(background.convert('RGB').quantize(colors=96));durations.append(duration)
        else:durations[-1]+=duration
    return frames,durations

def save_gif(frames,durations,target,loop=0):
    frames[0].save(target,'GIF',save_all=True,append_images=frames[1:],duration=durations,loop=loop,optimize=True,disposal=2)

def save_result_files(output,directory,slot):
    output.seek(0)
    with Image.open(output) as original:
        if getattr(original,'is_animated',False):
            path=directory/f'{slot}.gif';preview=directory/f'{slot}-preview.gif'
            frames,durations=gif_frames(original)
            save_gif(frames,durations,preview,original.info.get('loop',0))
            output.seek(0);raw=output.read()
            if original.format=='GIF' and len(raw)<=8*1024*1024:path.write_bytes(raw)
            else:
                original.seek(0);frames,durations=gif_frames(original,512,120);save_gif(frames,durations,path,original.info.get('loop',0))
        else:
            frame=original.convert('RGB');frame.thumbnail((1024,1024));path=directory/f'{slot}.jpg';frame.save(path,'JPEG',quality=88)
            frame.thumbnail((256,256));preview=directory/f'{slot}-preview.jpg';frame.save(preview,'JPEG',quality=75)
    return path,preview
