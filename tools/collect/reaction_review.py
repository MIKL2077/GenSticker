"""Build review sheets and export explicitly approved reaction-story batches.

Run with PYTHONPATH=backend/meme-generator and the project's Python runtime.
Cached source images remain outside Git; only selected templates are exported.
"""
import argparse,base64,collections,hashlib,json,os,re,time
from pathlib import Path
from io import BytesIO
from PIL import Image,ImageDraw,ImageOps
import numpy as np
from meme_generator.features.declarative import font,render
from meme_generator.features.reaction_templates import make_story,validate_story
from meme_generator.features.quality import perceptual_hash
from meme_generator.features.store import root


def source_frames(path):
    with Image.open(path) as source:
        n=getattr(source,'n_frames',1);frames=[]
        if source.width*source.height>2_000_000 or n>120:raise ValueError('source bounds')
        for index in sorted(set([0,n//2,n-1])):
            source.seek(index);frames.append(source.convert('RGB'))
        return frames


def inventory(args):
    output=Path(args.output);output.mkdir(parents=True,exist_ok=True)
    candidates=[]
    manifest=json.loads(Path(args.static_manifest).read_text())
    for item in manifest['candidates']:
        path=Path(args.static_cache)/(item['id']+'.image')
        if path.is_file() and not item.get('animated'):candidates.append({**item,'path':str(path),'animated':False})
    for p in sorted(Path(args.gif_cache).glob('*.json')):
        item=json.loads(p.read_text());path=p.with_suffix('.gif')
        if item.get('status')=='ready' and path.is_file():candidates.append({**item,'path':str(path),'animated':True})
    existing=[];used_hashes=set()
    for p in Path('backend/meme-generator/meme_generator/features/template_batches').glob('*.json'):
        for item in json.loads(p.read_text())['templates']:
            m=item['metadata'];used_hashes.add(m.get('original_hash'));h=m.get('perceptual_hash')
            if h:existing.append((int(h,16),)*3)
    groups=collections.defaultdict(list);seen=set()
    banned=re.compile(r'WhatToWear|穿什么|Green_Hat|Trump|特朗普|香港|乳|性暗示|EvilGirl|Sexy',re.I)
    for item in sorted(candidates,key=lambda i:(not i['animated'],i['id'])):
        if banned.search(item['category']):continue
        raw=Path(item['path']).read_bytes();digest=hashlib.sha256(raw).hexdigest()
        if digest in seen or digest in used_hashes:continue
        try:
            frames=source_frames(item['path'])
            # Some upstream .jpg/.png URLs contain a GIF payload. Trust the
            # decoded format and timeline, never the filename alone.
            if not item['animated'] and len(frames)>1:
                with Image.open(item['path']) as source:
                    if source.format!='GIF' or source.n_frames>40 or max(source.size)>512 or source.width*source.height*source.n_frames>8_000_000:continue
                    duration=0
                    for frame in range(source.n_frames):source.seek(frame);duration+=max(20,int(source.info.get('duration',100)))
                    if duration>8000:continue
                item={**item,'animated':True}
            if item['animated'] and len(frames)<2:continue
            if min(frames[0].size)<64 or max(frames[0].size)/min(frames[0].size)>3:continue
            hashes=[int(perceptual_hash(f),16) for f in frames]
            while len(hashes)<3:hashes.append(hashes[-1])
            if any(all((a^b).bit_count()<=4 for a,b in zip(hashes,old)) for old in existing):continue
            existing.append(tuple(hashes));seen.add(digest)
            groups[(item['animated'],item['category'])].append({**item,'raw_hash':digest,'review_hashes':[f'{h:016x}' for h in hashes]})
        except (OSError,ValueError,Image.DecompressionBombError):continue
    selected=[]
    for animated,limit in [(True,args.gif_limit),(False,args.static_limit)]:
        queues=[collections.deque(items[:30]) for (motion,_),items in sorted(groups.items()) if motion==animated]
        while queues and sum(i['animated']==animated for i in selected)<limit:
            for q in queues:
                if q and sum(i['animated']==animated for i in selected)<limit:selected.append(q.popleft())
            queues=[q for q in queues if q]
    seen_ids={item['id'] for path in (args.exclude_seen or []) for item in json.loads(Path(path).read_text())}
    selected=[item for item in selected if item['id'] not in seen_ids]
    for index,item in enumerate(selected):item['index']=index
    (output/'candidates.json').write_text(json.dumps(selected,ensure_ascii=False,indent=2))
    for offset in range(0,len(selected),20):
        sheet=Image.new('RGB',(1200,1000),'#f3f0e9');draw=ImageDraw.Draw(sheet)
        for cell,item in enumerate(selected[offset:offset+20]):
            x=(cell%5)*240;y=(cell//5)*250;frames=source_frames(item['path'])
            frame=ImageOps.contain(frames[0],(226,152));sheet.paste(frame,(x+(240-frame.width)//2,y+23))
            if item['animated']:
                for k,frame in enumerate(frames[1:]):
                    frame=ImageOps.contain(frame,(90,47));sheet.paste(frame,(x+15+k*110,y+177))
            draw.text((x+5,y+2),f"{item['index']:03d}  {'GIF' if item['animated'] else 'PNG'}",font=font(15,True),fill='black')
            category=re.sub(r'^\d+[A-Za-z_]*','',item['category']).replace('BQB','').strip('_')
            draw.text((x+5,y+226),category[:13],font=font(12),fill='black')
        sheet.save(output/f'review-{offset//20:02d}.jpg',quality=90)
    print(json.dumps({'candidates':len(selected),'animated':sum(i['animated'] for i in selected),'sheets':(len(selected)+19)//20},ensure_ascii=False))


def export(args):
    candidates=json.loads(Path(args.candidates).read_text());review=json.loads(Path(args.decisions).read_text());approved=review['approved']
    if not approved or len(approved)>1000:raise ValueError('invalid approved list')
    by_index={i['index']:i for i in candidates};by_id={i['id']:i for i in candidates};items=[];assets={};seen=set();counts=collections.Counter();frames_report=[]
    directory=root()/'template_assets';directory.mkdir(parents=True,exist_ok=True)
    sample=Image.new('RGBA',(320,240),'#fff0d8');draw=ImageDraw.Draw(sample);draw.ellipse((90,15,230,155),fill='#e9b689');draw.rounded_rectangle((65,145,255,235),radius=25,fill='#6196a8')
    for decision in approved:
        row=by_id[decision['source_id']] if decision.get('source_id') else by_index[decision['index']];index=row['index']
        if index in seen or decision.get('visual_status')!='approved' or not decision.get('label'):raise ValueError('unreviewed/duplicate decision')
        seen.add(index);kind=decision['kind'];layout=decision.get('layout','reply');context=decision.get('context','看到这张图时的我')
        raw=Path(row['path']).read_bytes();spec,new_assets,intent=make_story(raw,kind=kind,layout=layout,context=context,animated=row['animated'])
        for digest,data in new_assets.items():(directory/(digest+('.gif' if digest==spec['animation_asset'] else '.png'))).write_bytes(data)
        metadata={'name':decision['label'][:40],'tags':list(dict.fromkeys([decision.get('category','反应'), '动图' if row['animated'] else '静图', {'image':'图片回应','mixed':'图文互动','text':'配文回应'}[kind],layout])),'min_images':int(kind!='text'),'max_images':int(kind!='text'),'min_texts':int(kind!='image'),'max_texts':int(kind!='image'),'default_texts':spec['defaults'],'origin':row['origin'],'source_url':row['source_url'],'source_image_url':row['image_url'],'source_revision':row.get('source_revision',''),'author':'原作者未核实','license':'unverified','license_url':'','source_use':'explicit-user-request-with-attribution','original_hash':row['raw_hash'],'perceptual_hash':row['review_hashes'][0],'animated':row['animated'],'conversion':'reaction-story-v1','intent':{**intent,'fixed':'原梗的表情、动作、道具与原有文字完整保留','replaceable':'新增的情境图片和/或触发场景文字','reference_reaction':decision['label']},'subject_types':['person','animal','object','unknown'],'input_hint':('原梗文案保留；可替换情境图片' if kind=='image' else '原梗文案保留；可改情境图片和配文' if kind=='mixed' else '原梗文案保留；可改上方情境配文'),'review':{'visual_status':'approved','sheet':decision.get('review_sheet',f'review-{index//20:02d}.jpg'),'index':index,'review_method':'source and key poses visually inspected; full output timeline validated'},'quality':{'reference_preserved':True,'replacement_verified':True,'slot_overlap_pixels':0,'motion_verified':bool(row['animated']),'multiline_context_verified':kind!='image'},'collected_at':time.time()}
        metadata['created_at']=metadata['collected_at']
        metadata['caption_inventory']=[{'region':'original reaction panel','box':intent['reaction_box'],'editable':False,'coverage':'all original caption lines, labels and credits remain fixed'}]+([{'region':'context caption','slot':0,'editable':True,'max_lines':2,'coverage':'complete new context paragraph, including both lines'}] if kind!='image' else [])
        validate_story(spec,metadata)
        if kind!='image':
            with Image.open(render(spec,[sample] if kind!='text' else [],['第一行情境\n第二行补充'])) as multiline:
                if row['animated'] and getattr(multiline,'n_frames',1)<2:raise ValueError('multiline output lost animation')
        output=render(spec,[sample] if kind!='text' else [],[] if kind=='image' else [context])
        with Image.open(output) as generated:
            n=getattr(generated,'n_frames',1);duration=0
            if row['animated']:
                if n<2:raise ValueError('animated output lost motion')
                for i in range(n):generated.seek(i);duration+=generated.info.get('duration',100)
                with Image.open(BytesIO(raw)) as source:
                    expected=0
                    for i in range(source.n_frames):source.seek(i);expected+=max(20,int(source.info.get('duration',100)))
                if duration!=expected:raise ValueError('animation timing changed')
            frames_report.append({'key':'auto_story_'+row['raw_hash'][:24],'frames':n,'duration_ms':duration,'bytes':len(output.getvalue()),'kind':kind})
        counts[kind]+=1;items.append({'key':'auto_story_'+row['raw_hash'][:24],'version':1,'metadata':metadata,'spec':spec});assets.update(new_assets)
        if len(items)%50==0:print(json.dumps({'validated':len(items),'types':counts}),flush=True)
    target=Path(args.output);target.mkdir(parents=True,exist_ok=True)
    batch=[];needed=set();byte_count=0;number=0
    encoded={d:base64.b64encode(raw).decode() for d,raw in assets.items()}
    def flush():
        nonlocal number,batch,needed,byte_count
        if not batch:return
        number+=1
        payload={'version':1,'templates':batch,'assets':{d:encoded[d] for d in sorted(needed)}}
        data=json.dumps(payload,ensure_ascii=False,separators=(',',':'))
        if len(data.encode())>32*1024*1024:raise ValueError('batch exceeds 32MiB')
        (target/f'20261021-reactions-{number:02d}.json').write_text(data+'\n')
        batch=[];needed=set();byte_count=0
    for item in items:
        hashes={l['value'] for l in item['spec']['layers'] if l['type']=='asset'}
        if item['spec']['animation_asset']:hashes.add(item['spec']['animation_asset'])
        added=sum(len(encoded[d])+70 for d in hashes-needed)+len(json.dumps(item,ensure_ascii=False).encode())
        if batch and (len(batch)>=100 or byte_count+added>8*1024*1024):
            flush();added=sum(len(encoded[d])+70 for d in hashes)+len(json.dumps(item,ensure_ascii=False).encode())
        batch.append(item);needed.update(hashes);byte_count+=added
    flush()
    (target/'validation.json').write_text(json.dumps({'counts':counts,'animated':sum(i['metadata']['animated'] for i in items),'templates':frames_report},ensure_ascii=False,indent=2))
    print(json.dumps({'templates':len(items),'types':counts,'animated':sum(i['metadata']['animated'] for i in items)},ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('inventory');p.add_argument('--static-manifest',required=True);p.add_argument('--static-cache',required=True);p.add_argument('--gif-cache',required=True);p.add_argument('--output',required=True);p.add_argument('--gif-limit',type=int,default=550);p.add_argument('--static-limit',type=int,default=350);p.add_argument('--exclude-seen',nargs='*')
    p=sub.add_parser('export');p.add_argument('--candidates',required=True);p.add_argument('--decisions',required=True);p.add_argument('--output',required=True)
    args=parser.parse_args();inventory(args) if args.command=='inventory' else export(args)
