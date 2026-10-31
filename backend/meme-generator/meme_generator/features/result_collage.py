"""Private GIF collages of existing, account-owned recommendation results.

No photo upload, remote URL fetching, persistent file or model inference.
One compositor runs at a time; decoding, memory, duration and output are bounded.
"""
import asyncio
from bisect import bisect_right
from contextlib import ExitStack
from io import BytesIO
import math
from pathlib import Path
import time
import threading
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from PIL import Image, ImageOps

from meme_generator.account import current_user
from meme_generator.safe_images import open_image
from .store import connect, root

router=APIRouter()
slots=threading.BoundedSemaphore(1)
MAX_BYTES=2*1024*1024
PAPER=(255,250,244)


class CollageSelection(BaseModel):
    model_config=ConfigDict(extra='forbid')
    slots:list[Annotated[int,Field(strict=True,ge=0,le=8)]]=Field(min_length=1,max_length=9)


def compose_serial(paths):
    # Held by the worker thread even if the HTTP client disconnects.
    if not slots.acquire(timeout=25):raise HTTPException(503,'动态拼图正在排队，请稍后重试')
    try:return compose(paths)
    finally:slots.release()


def compose(paths):
    """Pillow handles GIF patch disposal; every tile keeps its own loop timing."""
    started=time.monotonic()
    def check():
        if time.monotonic()-started>40:raise ValueError('动态拼图处理繁忙，请稍后重试')
    with ExitStack() as stack:
        sources=[];decoded=0;total_bytes=0
        for path in paths:
            check();size=path.stat().st_size;total_bytes+=size
            if size>8*1024*1024 or total_bytes>24*1024*1024:raise ValueError('所选原图体积过大')
            image=stack.enter_context(open_image(path,max_pixels=1500000,max_frames=300,max_total_pixels=150000000))
            delays=[]
            for i in range(image.n_frames):
                image.seek(i);delay=int(image.info.get('duration',100));delays.append(delay if delay>=20 else 100)
            duration=sum(delays)
            if len(delays)>1 and duration>15000:raise ValueError('单张动图最长支持 15 秒')
            decoded+=image.width*image.height*len(delays)
            if decoded>150000000:raise ValueError('所选动图解码量过大')
            ends=[];end=0
            for delay in delays:end+=delay;ends.append(end)
            sources.append(dict(image=image,delays=delays,ends=ends,duration=duration,last=-1,tile=None))
        duration=max((s['duration'] for s in sources if len(s['delays'])>1),default=100)
        # Preserve all change times when affordable; dense timelines are sampled.
        times={0,duration}
        for s in sources:
            if len(s['delays'])<2:continue
            for base in range(0,duration,s['duration']):
                times.update(base+t for t in s['ends'] if base+t<duration)
        times=sorted(times)
        def playable(ordered):
            result=[0]
            for t in ordered[1:-1]:
                if t-result[-1]>=20 and duration-t>=20:result.append(t)
            return result+[duration]
        times=playable(times)
        count=len(sources);columns=1 if count==1 else 2 if count<=4 else 3;rows=math.ceil(count/columns);gap=12
        for edge,colors,limit in [(160,128,150),(128,96,120),(96,64,90),(64,32,60),(48,16,40)]:
            check();step=max(100,math.ceil(duration/limit/10)*10)
            timeline=times if len(times)<=limit+1 else playable(list(range(0,duration,step))+[duration])
            width=columns*edge+(columns+1)*gap;height=rows*edge+(rows+1)*gap
            frames=[]
            for s in sources:s['last']=-1;s['tile']=None
            for t in timeline[:-1]:
                check();frame=Image.new('RGB',(width,height),PAPER)
                for i,s in enumerate(sources):
                    index=min(len(s['delays'])-1,bisect_right(s['ends'],t%s['duration']))
                    if s['last']!=index:
                        s['image'].seek(index)
                        s['tile']=ImageOps.contain(s['image'].convert('RGBA'),(edge,edge),Image.Resampling.BILINEAR)
                        s['last']=index
                    tile=s['tile'];x=gap+(i%columns)*(edge+gap)+(edge-tile.width)//2;y=gap+(i//columns)*(edge+gap)+(edge-tile.height)//2
                    frame.paste(tile,(x,y),tile)
                frames.append(frame)
            # One palette for the whole animation, including later scene colors.
            sample=Image.new('RGB',(192,576),PAPER)
            for i,index in enumerate([0,len(frames)//2,len(frames)-1]):
                sample.paste(ImageOps.contain(frames[index],(192,192)),(0,i*192))
            palette=sample.quantize(colors=colors,method=Image.Quantize.MEDIANCUT)
            indexed=[f.quantize(palette=palette,dither=Image.Dither.NONE) for f in frames]
            delays=[b-a for a,b in zip(timeline,timeline[1:])]
            output=BytesIO();indexed[0].save(output,'GIF',save_all=True,append_images=indexed[1:],duration=delays,loop=0,disposal=1,optimize=False)
            raw=output.getvalue()
            if len(raw)<=MAX_BYTES:return raw
        raise ValueError('动态拼图暂时无法完成，请重试')


@router.post('/jobs/{identifier}/collage')
async def create_collage(identifier:str,selection:CollageSelection,user=Depends(current_user)):
    if len(set(selection.slots))!=len(selection.slots):raise HTTPException(422,'不能重复选择同一张表情')
    def owned_paths():
        from .recommend import owned,admit_generation
        db=connect()
        try:
            job=owned(db,identifier,user)
            if job['created']<time.time()-7*86400:raise HTTPException(410,'这组表情已过期')
            results={r['slot']:r for r in db.execute('SELECT slot,path FROM results WHERE job_id=?',(identifier,))}
            if any(i not in results for i in selection.slots):raise HTTPException(404,'所选表情尚未生成')
            private=(root()/'private'/user['id']).resolve();paths=[]
            for i in selection.slots:
                path=Path(results[i]['path']).resolve()
                if not path.is_relative_to(private) or not path.is_file():raise HTTPException(410,'所选表情已过期')
                paths.append(path)
            with db:
                db.execute('BEGIN IMMEDIATE')
                import uuid
                admit_generation(db,user['id'],'collage:'+uuid.uuid4().hex,time.time())
            return paths
        finally:db.close()
    paths=await asyncio.to_thread(owned_paths)
    try:
        raw=await asyncio.to_thread(compose_serial,paths)
        # Recheck ownership after rendering: deletion/account changes cannot
        # deliver a previously authorized private result after access was lost.
        db=connect()
        try:
            from .recommend import owned
            owned(db,identifier,user)
        finally:db.close()
        return Response(raw,media_type='image/gif',headers={'Cache-Control':'private, no-store'})
    except (OSError,ValueError,Image.DecompressionBombError) as error:
        raise HTTPException(422,str(error) or '这组动图暂时无法读取')
