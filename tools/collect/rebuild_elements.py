"""Propose and compile source-element replacements for offline visual review.

No draft produced here is approved or published. Per-template decisions can
override source captions, face polygons and any individual frame before rerun.
"""
import argparse
import hashlib
from collections import Counter
from io import BytesIO
import json
from pathlib import Path
import re

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageOps

from meme_generator.features.declarative import font, render, Layer
from meme_generator.features.element_templates import compile_elements, fingerprint
from meme_generator.features.store import root


def rectangle(points, size, margin=2):
    width,height=size
    xs,ys=zip(*points)
    x=max(0,min(xs)-margin);y=max(0,min(ys)-margin)
    return [x,y,min(width,max(xs)+margin+1)-x,min(height,max(ys)+margin+1)-y]


def union(boxes):
    x=min(b[0] for b in boxes);y=min(b[1] for b in boxes)
    return [x,y,max(b[0]+b[2] for b in boxes)-x,max(b[1]+b[3] for b in boxes)-y]


def intersects(a,b):
    x,y,w,h=a;xx,yy,ww,hh=b
    return max(0,min(x+w,xx+ww)-max(x,xx))*max(0,min(y+h,yy+hh)-max(y,yy))


def ellipse(box):
    _,_,w,h=box
    return [[round((w-1)*(.5+.49*np.cos(t))),round((h-1)*(.5+.49*np.sin(t)))]
            for t in np.linspace(0,2*np.pi,20,endpoint=False)]


def usable_caption(c,size):
    text=c['text'].strip()
    box=rectangle(c['polygon'],size)
    # Credits, clocks, counters and logos stay in the source, with reasons in
    # the inventory. This is a proposal filter, never a visual acceptance gate.
    fixed=(c['confidence']<.7 or len(text)>150 or not text or
           re.search(r'^@|[\w.-]+\.(com|net)|表情娘|表清娘|表洁娘|Na\.?$|GIF|BQB|YOUKU|XFF|MELON|SINESS|SANE',text,re.I) or
           (len(text)==1 and text not in '耶哼喂辣威咸') or
           (not re.search(r'[\u4e00-\u9fffA-Za-z]',text)) or
           (box[3]<max(7,size[1]*.022)))
    return not fixed


def paragraphs(captions,size):
    entries=[{'text':c['text'],'box':rectangle(c['polygon'],size),'confidence':c['confidence']}
             for c in captions if usable_caption(c,size)]
    entries.sort(key=lambda c:(c['box'][1]+c['box'][3]/2,c['box'][0]))
    same_line=[]
    for entry in entries:
        match=None
        for previous in same_line:
            a=previous['box'];b=entry['box']
            if abs((a[1]+a[3]/2)-(b[1]+b[3]/2))<.45*max(a[3],b[3]) and max(b[0]-(a[0]+a[2]),a[0]-(b[0]+b[2]))<.7*max(a[3],b[3]):
                match=previous;break
        if match is None:same_line.append(entry)
        else:
            left,right=sorted([match,entry],key=lambda c:c['box'][0])
            match.update(box=union([match['box'],entry['box']]),text=left['text']+(' ' if re.search('[A-Za-z]$',left['text']) else '')+right['text'],confidence=min(match['confidence'],entry['confidence']))
    entries=sorted(same_line,key=lambda c:(c['box'][1],c['box'][0]))
    output=[]
    for entry in entries:
        if output:
            prev=output[-1];a=prev['box'];b=entry['box']
            overlap=max(0,min(a[0]+a[2],b[0]+b[2])-max(a[0],b[0]))
            gap=b[1]-(a[1]+a[3])
            if -.5*min(a[3],b[3])<=gap<.6*min(a[3],b[3]) and overlap>.35*min(a[2],b[2]):
                prev.update(box=union([a,b]),text=prev['text']+'\n'+entry['text'],confidence=min(prev['confidence'],entry['confidence']))
                continue
        output.append(entry)
    return output


def caption_tracks(analysis,size):
    tracks=[];per_frame=[]
    for frame in analysis['frames']:
        found=[]
        for item in paragraphs(frame['captions'],size):
            box=item['box'];cx=box[0]+box[2]/2;cy=box[1]+box[3]/2
            matches=[]
            for i,track in enumerate(tracks):
                a=track['box'];distance=abs(cy-(a[1]+a[3]/2))/max(a[3],box[3])
                if distance<.85 and abs(cx-(a[0]+a[2]/2))<.6*max(a[2],box[2]):matches.append((distance,i))
            used={s for s,_ in found}
            matches=[m for m in matches if m[1] not in used]
            if matches:index=min(matches)[1]
            else:
                index=len(tracks);tracks.append({'box':box,'variants':[]})
            tracks[index]['variants'].append(item)
            found.append((index,item))
        per_frame.append(found)
    # A wrapped source paragraph can be recognized as two lines in one frame
    # and only its bottom line in another. Merge those overlapping proposals
    # before assigning slots, otherwise one line remains baked into the GIF.
    parent=list(range(len(tracks)))
    def owner(i):
        while parent[i]!=i:parent[i]=parent[parent[i]];i=parent[i]
        return i
    for i,a in enumerate(tracks):
        aa=union([v['box'] for v in a['variants']])
        for j in range(i):
            bb=union([v['box'] for v in tracks[j]['variants']])
            if intersects(aa,bb)>.08*min(aa[2]*aa[3],bb[2]*bb[3]):parent[owner(i)]=owner(j)
    groups={}
    for i,track in enumerate(tracks):groups.setdefault(owner(i),[]).extend(track['variants'])
    ordered=sorted(groups,key=lambda i:(union([v['box'] for v in groups[i]])[1],union([v['box'] for v in groups[i]])[0]))
    remap={old:ordered.index(owner(old)) for old in range(len(tracks))}
    merged=[{'box':union([v['box'] for v in groups[i]]),'variants':groups[i]} for i in ordered]
    mapped=[]
    for items in per_frame:
        frame={}
        for old,item in items:
            slot=remap[old]
            if slot not in frame:frame[slot]=item
            elif len(item['text'])>len(frame[slot]['text']):frame[slot]=item
        mapped.append([(slot,{**item,'box':merged[slot]['box']}) for slot,item in frame.items()])
    return merged,mapped


def track_face(frames,initial):
    """Authoring proposal, with correlation confidence retained for review."""
    height,width=frames[0].shape[:2]
    base=np.array(initial,dtype=float);boxes=[initial];scores=[1.]
    old=cv2.cvtColor(frames[0],cv2.COLOR_RGB2GRAY)
    for pixels in frames[1:]:
        gray=cv2.cvtColor(pixels,cv2.COLOR_RGB2GRAY)
        x,y,w,h=boxes[-1];pad=max(8,round(max(w,h)*.65))
        left=max(0,x-pad);top=max(0,y-pad);right=min(width,x+w+pad);bottom=min(height,y+h+pad)
        patch=old[y:y+h,x:x+w]
        region=gray[top:bottom,left:right]
        if min(patch.shape)<3 or region.shape[0]<h or region.shape[1]<w:
            boxes.append(boxes[-1]);scores.append(0.);old=gray;continue
        result=cv2.matchTemplate(region,patch,cv2.TM_CCOEFF_NORMED)
        _,score,_,location=cv2.minMaxLoc(result)
        nx=left+location[0];ny=top+location[1]
        # A sudden weak match is a shot/occlusion warning, not evidence to
        # publish a portrait onto a background or a person's hand.
        if score<.2:nx,ny=x,y
        boxes.append([nx,ny,w,h]);scores.append(round(float(score),3));old=gray
    return boxes,scores


def propose(row,analysis,decision,frames):
    size=tuple(row['canvas']);width,height=size
    tracks,found=caption_tracks(analysis,size)
    # Match an observed source caption on frames where OCR alone missed it.
    # Empty frames do not match the letter pattern and stay empty.
    for slot,track in enumerate(tracks):
        observations=[i for i,items in enumerate(found) if any(s==slot for s,_ in items)]
        if not observations:continue
        x,y,w,h=track['box'];reference=cv2.cvtColor(frames[observations[0]][y:y+h,x:x+w],cv2.COLOR_RGB2GRAY)
        if np.std(reference)<5:continue
        example=next(item for s,item in found[observations[0]] if s==slot)
        for index,pixels in enumerate(frames):
            if index in observations:continue
            region=cv2.cvtColor(pixels[y:y+h,x:x+w],cv2.COLOR_RGB2GRAY)
            score=float(cv2.matchTemplate(region,reference,cv2.TM_CCOEFF_NORMED)[0,0])
            if score>=.62:found[index].append((slot,{**example,'box':track['box']}))
    plans=[[] for _ in frames];inventory=[];defaults=[]
    text_decisions=decision.get('captions')
    if text_decisions is not None:
        tracks=[];found=[[] for _ in frames]
        for slot,c in enumerate(text_decisions):
            item={'text':c['text'],'box':c['box'],'confidence':1.}
            tracks.append({'box':c['box'],'variants':[item]})
            for index in range(len(frames)):
                if index in c.get('hidden_frames',[]):continue
                item={**item,'box':c.get('frames',{}).get(str(index),c['box'])}
                found[index].append((slot,item))
    selected=[]
    for old_slot,track in enumerate(tracks):
        variants=track['variants'];best=max(variants,key=lambda v:(v['text'].count('\n'),len(v['text']),v['confidence']))
        # Preserve every original line in the selected paragraph.
        if len(defaults)>=5:continue
        slot=len(defaults);defaults.append(best['text']);selected.append(old_slot)
        inventory.append({'slot':slot,'editable':True,'original_text':best['text'],
                          'box':best['box'],'source_variants':sorted(set(v['text'] for v in variants))})
        for index,items in enumerate(found):
            for track_slot,item in items:
                if track_slot!=old_slot:continue
                x,y,w,h=item['box'];region=frames[index][y:y+h,x:x+w]
                brightness=float(np.median(cv2.cvtColor(region,cv2.COLOR_RGB2GRAY)))
                color='#222222' if brightness>205 else '#ffffff'
                style=(text_decisions[old_slot] if text_decisions is not None else {})
                value={
                    'type':'text','box':[x,y,w,h],'slot':slot,'value':best['text'],
                    'font_size':min(64,max(6,round(h/max(1,best['text'].count('\n')+1)*.85))),
                    'color':style.get('color',color),'weight':style.get('weight','bold'),
                    'align':style.get('align','center'),'stroke_width':style.get('stroke_width',0 if color=='#222222' else 1),
                    'max_lines':min(5,max(2,best['text'].count('\n')+1)),
                    'line_spacing':style.get('line_spacing',1 if h<30 else 3),
                    'direction':style.get('direction','vertical' if h>1.8*w and len(best['text'])>1 else 'horizontal')}
                value['text_mask']=style.get('text_mask','box')
                plans[index].append(value)
    for frame in analysis['frames']:
        for c in frame['captions']:
            cbox=rectangle(c['polygon'],size)
            if not any(intersects(cbox,l['box'])>.5*cbox[2]*cbox[3] for l in plans[frame['index']] if l['type']=='text'):
                item={'editable':False,'original_text':c['text'],'box':rectangle(c['polygon'],size),
                      'reason':'本模板保留的原文、来源标识或细小标记'}
                if item not in inventory:inventory.append(item)
    face_plans=decision.get('faces',[])
    if decision.get('human'):
        detected=[f['faces']['person'] for f in analysis['frames']]
        initial=max(detected[0] or [],key=lambda b:b[2]*b[3],default=None)
        if initial:
            x,y,w,h=initial
            if w*h<width*height*.025:initial=None
        if initial:
            x,y,w,h=initial
            # Haar proposals include a strip of hair/neck. Keep the fixed
            # hairstyle and use the actual inner-face region instead.
            initial=[x+round(w*.06),y+round(h*.06),round(w*.88),round(h*.92)]
            face_plans=[{'box':initial,'tone':'original','detector':True}]+face_plans
    confidence=[]
    for face in face_plans:
        box=face['box']
        if face.get('normalized'):box=[round(v*(width if k%2==0 else height)) for k,v in enumerate(box)]
        box=[max(0,int(v)) for v in box];box[2]=min(box[2],width-box[0]);box[3]=min(box[3],height-box[1])
        if min(box[2:])<16:continue
        boxes,scores=track_face(frames,box)
        if face.get('yellow_face'):
            for index,pixels in enumerate(frames):
                hsv=cv2.cvtColor(pixels,cv2.COLOR_RGB2HSV)
                mask=cv2.inRange(hsv,np.array([10,75,100]),np.array([40,255,255]))
                count,_,stats,_=cv2.connectedComponentsWithStats(mask)
                candidates=[list(map(int,s[:4])) for s in stats[1:] if s[4]>30 and .55<s[2]/max(1,s[3])<1.7 and .4*box[2]<s[2]<1.6*box[2] and .4*box[3]<s[3]<1.6*box[3]]
                if candidates:
                    match=max(candidates,key=lambda b:intersects(b,boxes[index]))
                    if intersects(match,boxes[index]):boxes[index]=match;scores[index]=1.
        if face.get('detector'):
            for index,frame in enumerate(analysis['frames']):
                candidates=frame['faces']['person']
                if candidates:
                    match=max(candidates,key=lambda b:intersects(b,boxes[index]))
                    if intersects(match,boxes[index])>.2*boxes[index][2]*boxes[index][3]:
                        x,y,w,h=match;boxes[index]=[x+round(w*.06),y+round(h*.06),round(w*.88),round(h*.92)];scores[index]=1.
        confidence.append(scores)
        for index,box in enumerate(boxes):
            if index in face.get('hidden_frames',[]):continue
            box=face.get('frames',{}).get(str(index),box)
            if any(intersects(box,p['box']) for p in plans[index]):
                raise ValueError(f'frame {index}: face intersects another slot; author an explicit mask or keep only original captions')
            plans[index].insert(0,{'type':'face','box':box,'slot':face.get('slot',0),'fit':'cover',
                    'tone':face.get('tone','grayscale'),'feather':0,
                    'erase_polygon':face.get('polygon',ellipse(box)),
                    'protect_polygons':face.get('protect_polygons',[]),'rotation':face.get('rotation',0)})
    return plans,defaults,inventory,confidence


def build(args):
    inventory=json.loads(args.inventory.read_text());decisions=json.loads(args.decisions.read_text())
    args.output.mkdir(parents=True,exist_ok=True)
    directory=root()/'template_assets';directory.mkdir(parents=True,exist_ok=True)
    photo=Image.open(args.photo).convert('RGBA');results=[]
    for row in inventory:
        if args.only and row['index'] not in args.only:continue
        target=args.output/(row['key']+'.json');decision=decisions.get(str(row['index']),{})
        if target.exists() and not args.redo:
            results.append(json.loads(target.read_text()));continue
        analysis=json.loads((args.elements/(row['key']+'.json')).read_text())
        with Image.open(row['path']) as source:
            frames=[]
            for i in range(getattr(source,'n_frames',1)):
                source.seek(i);frames.append(np.asarray(source.convert('RGB')))
        record={'index':row['index'],'key':row['key'],'name':row['name'],'status':'draft'}
        try:
            if decision and (decision.get('key')!=row['key'] or decision.get('source_sha256')!=hashlib.sha256(Path(row['path']).read_bytes()).hexdigest()):raise ValueError('decision belongs to another source; remeasure its geometry')
            if decision.get('pending'):raise ValueError(decision['pending'])
            plans,defaults,caption_inventory,confidence=propose(row,analysis,decision,frames)
            spec,assets,geometry=compile_elements(Path(row['path']).read_bytes(),plans,defaults)
            for digest,data in assets.items():
                suffix='.gif' if data[:6] in {b'GIF87a',b'GIF89a'} else '.png'
                (directory/(digest+suffix)).write_bytes(data)
            images=max((l['slot']+1 for p in plans for l in p if l['type']=='face'),default=0)
            changed=['新文案' for text in defaults]
            output=render(spec,[photo]*images,changed)
            path=args.output/(row['key']+('.gif' if len(frames)>1 else '.png'));path.write_bytes(output.getvalue())
            with Image.open(BytesIO(output.getvalue())) as generated:
                duration=0
                for i in range(getattr(generated,'n_frames',1)):
                    generated.seek(i);duration+=generated.info.get('duration',100)
                if len(frames)>1 and (getattr(generated,'n_frames',1)<2 or duration!=sum(f['duration_ms'] for f in spec['frames'])):
                    raise ValueError('motion or loop timing changed')
            record.update(spec=spec,caption_inventory=caption_inventory,geometry=geometry,
                          face_tracking_confidence=confidence,image_slots=images,text_slots=len(defaults),
                          draft_output=str(path),source_canvas=row['canvas'],source_frames=len(frames),
                          spec_sha256=fingerprint(spec),asset_hashes=list(assets))
        except Exception as error:
            record.update(status='pending',reason=str(error))
        target.write_text(json.dumps(record,ensure_ascii=False,indent=2));results.append(record)
        if row['index']%25==0:print(json.dumps({'index':row['index'],'states':Counter(r['status'] for r in results)},ensure_ascii=False),flush=True)
    (args.output/'index.json').write_text(json.dumps([{k:v for k,v in r.items() if k not in {'spec','geometry','asset_hashes','caption_inventory','face_tracking_confidence'}} for r in results],ensure_ascii=False,indent=2))
    print(json.dumps({'states':Counter(r['status'] for r in results),'types':Counter('mixed' if r.get('image_slots') and r.get('text_slots') else 'image' if r.get('image_slots') else 'text' for r in results if r['status']=='draft')},ensure_ascii=False),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--inventory',type=Path,required=True);p.add_argument('--elements',type=Path,required=True)
    p.add_argument('--decisions',type=Path,required=True);p.add_argument('--photo',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--only',type=int,nargs='*');p.add_argument('--redo',action='store_true');build(p.parse_args())
