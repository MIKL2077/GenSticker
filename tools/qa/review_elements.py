"""Audit actual frame replacements and export only separately reviewed recipes."""
import argparse
import base64
from collections import Counter
import hashlib
from io import BytesIO
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageOps

from meme_generator.features.declarative import TemplateSpec, render, font
from meme_generator.features.element_templates import fingerprint, validate_elements
from meme_generator.features.face_slot import removal_mask
from meme_generator.features.storage import asset_refs
from meme_generator.features.store import root


def audit(args):
    inventory=json.loads(args.inventory.read_text());by_key={r['key']:r for r in inventory}
    drafts=json.loads((args.drafts/'index.json').read_text());photo=Image.open(args.photo).convert('RGBA')
    transparent=photo.copy();alpha=Image.new('L',photo.size);ImageDraw.Draw(alpha).ellipse((0,0,photo.width-1,photo.height-1),fill=255);transparent.putalpha(alpha)
    reports=[]
    for summary in drafts:
        if summary['status']!='draft':continue
        draft=json.loads((args.drafts/(summary['key']+'.json')).read_text());spec=TemplateSpec.model_validate(draft['spec'])
        report={'index':draft['index'],'key':draft['key'],'spec_sha256':fingerprint(draft['spec']),'status':'passed','frames':[]}
        try:
            with Image.open(by_key[draft['key']]['path']) as source:
                for index,frame in enumerate(spec.frames):
                    source.seek(index);original=Image.alpha_composite(Image.new('RGBA',source.size,'white'),source.convert('RGBA'))
                    if not frame.layers:
                        report['frames'].append({'index':index,'image_slots':[],'text_slots':[],'fixed_pixels_mae':0});continue
                    static=TemplateSpec(width=spec.width,height=spec.height,defaults=spec.defaults,layers=frame.layers,background_prepared=True)
                    a=Image.open(render(static,[photo]*draft['image_slots'],['新文案']*draft['text_slots'],_transparent=True,_base=original)).convert('RGB')
                    b=Image.open(render(static,[transparent]*draft['image_slots'],['']*draft['text_slots'],_transparent=True,_base=original)).convert('RGB')
                    mask=removal_mask(original.size,frame.layers)
                    draw=ImageDraw.Draw(mask)
                    for layer in frame.layers:
                        if layer.type=='text':
                            x,y,w,h=layer.box;draw.rectangle((x,y,x+w-1,y+h-1),fill=255)
                    fixed=np.asarray(mask)==0;ref=np.asarray(original.convert('RGB')).astype(int)
                    mae=max(float(np.abs(np.asarray(im).astype(int)-ref)[fixed].mean()) if np.any(fixed) else 0 for im in [a,b])
                    if mae!=0:raise ValueError(f'frame {index}: fixed pixels changed ({mae})')
                    for layer in frame.layers:
                        if layer.type=='face':
                            local=np.asarray(removal_mask(original.size,[layer]))>0
                            if not np.any(local) or float(np.abs(np.asarray(a).astype(int)-ref)[local].mean())<1:
                                raise ValueError(f'frame {index}: supplied avatar was not visible')
                    report['frames'].append({'index':index,'image_slots':sorted({l.slot for l in frame.layers if l.type=='face'}),
                                             'text_slots':sorted({l.slot for l in frame.layers if l.type=='text'}),'fixed_pixels_mae':mae})
            for digest in asset_refs(draft['spec']):
                paths=[root()/'template_assets'/(digest+suffix) for suffix in ['.png','.gif']]
                if not any(p.exists() and hashlib.sha256(p.read_bytes()).hexdigest()==digest for p in paths):raise ValueError('missing/corrupt asset '+digest)
            if draft['image_slots']:
                try:render(spec,[],spec.defaults)
                except Exception:pass
                else:raise ValueError('missing photo did not fail')
            with Image.open(draft['draft_output']) as output:
                count=getattr(output,'n_frames',1);duration=0
                for index in range(count):output.seek(index);duration+=output.info.get('duration',100)
                if len(spec.frames)>1 and (count<2 or duration!=sum(f.duration_ms for f in spec.frames)):raise ValueError('motion/timing mismatch')
                report.update(output_frames=count,duration_ms=duration,output_bytes=Path(draft['draft_output']).stat().st_size)
            report.update(analyzed_frames=len(spec.frames),protected_pixel_mae=0,actual_replacement_verified=True,
                          transparent_input_verified=True,motion_verified=len(spec.frames)>1)
        except Exception as error:report.update(status='failed',reason=str(error))
        reports.append(report)
        if len(reports)%25==0:print(json.dumps({'audited':len(reports),'states':Counter(r['status'] for r in reports)}),flush=True)
    args.output.write_text(json.dumps(reports,ensure_ascii=False,indent=2))
    print(json.dumps({'states':Counter(r['status'] for r in reports)},ensure_ascii=False))


def sheets(args):
    inventory=json.loads(args.inventory.read_text());drafts=json.loads((args.drafts/'index.json').read_text())
    args.output.mkdir(parents=True,exist_ok=True)
    rows=[r for r in drafts if r['status']=='draft'];label=font(14)
    for offset in range(0,len(rows),30):
        sheet=Image.new('RGB',(1500,1200),'#eeeeee');draw=ImageDraw.Draw(sheet)
        for cell,row in enumerate(rows[offset:offset+30]):
            x=(cell%6)*250;y=(cell//6)*240
            with Image.open(row['draft_output']) as source:
                frame=ImageOps.contain(source.convert('RGB'),(240,190));sheet.paste(frame,(x+(250-frame.width)//2,y+24))
            draw.text((x+4,y+2),f"{row['index']:03d} {row['name'][:14]}",font=label,fill='black')
            draw.text((x+4,y+219),f"头像 {row['image_slots']} / 原文 {row['text_slots']}",font=label,fill='black')
        sheet.save(args.output/f'outputs-{offset//30:02d}.jpg',quality=94)
    motion=[r for r in rows if r['source_frames']>1]
    for offset in range(0,len(motion),6):
        sheet=Image.new('RGB',(1560,1080),'#eeeeee');draw=ImageDraw.Draw(sheet)
        for cell,row in enumerate(motion[offset:offset+6]):
            y=cell*180;draw.text((3,y),f"{row['index']:03d} {row['name']}  上：原图  下：实际替换",font=label,fill='black')
            source=Image.open(inventory[row['index']]['path']);spec=json.loads((args.drafts/(row['key']+'.json')).read_text())['spec']
            # Decode every output timepoint; GIF may consolidate identical
            # adjacent frames, so use the authored source-frame recipe below.
            photo=Image.open(args.photo).convert('RGBA')
            for i,frame in enumerate(spec['frames']):
                source.seek(i);base=Image.alpha_composite(Image.new('RGBA',source.size,'white'),source.convert('RGBA'))
                if frame['layers']:
                    static={'width':spec['width'],'height':spec['height'],'layers':frame['layers'],'defaults':spec['defaults'],'background_prepared':True}
                    output=Image.open(render(static,[photo]*row['image_slots'],['新文案']*row['text_slots'],_transparent=True,_base=base)).convert('RGB')
                else:output=base.convert('RGB')
                for line,image in enumerate([base.convert('RGB'),output]):
                    small=ImageOps.contain(image,(64,68));sheet.paste(small,(i*65+(64-small.width)//2,y+23+line*73))
        sheet.save(args.output/f'motion-{offset//6:02d}.jpg',quality=95)
    print(json.dumps({'outputs_sheets':(len(rows)+29)//30,'motion_sheets':(len(motion)+5)//6,'motion_cases':len(motion)}))


def export(args):
    inventory=json.loads(args.inventory.read_text());drafts=json.loads((args.drafts/'index.json').read_text())
    audits={r['key']:r for r in json.loads(args.audit.read_text())}
    review=json.loads(args.decisions.read_text());decisions=json.loads(args.authoring.read_text())
    approved=review['approved'];items=[];assets={};pending=[];by_key={r['key']:r for r in inventory}
    for summary in drafts:
        source=by_key[summary['key']];key=source['key']
        if key not in approved:
            pending.append({'key':key,'original_hash':source['metadata']['original_hash'],'reason':review.get('pending',{}).get(key,summary.get('reason','未通过替换效果审阅')),
                            'source_url':source['metadata']['source_url'],'name':source['name']});continue
        if summary['status']!='draft' or audits[key]['status']!='passed':raise ValueError('approved item failed execution audit: '+key)
        draft=json.loads((args.drafts/(key+'.json')).read_text());spec=draft['spec'];a=audits[key]
        if a['spec_sha256']!=fingerprint(spec) or approved[key].get('spec_sha256')!=fingerprint(spec):raise ValueError('review no longer matches recipe: '+key)
        old=source['metadata'];decision=decisions.get(str(source['index']),{});im=draft['image_slots'];tx=draft['text_slots']
        tags=[t for t in old['tags'] if t not in {'reply','contrast','after','comment','caption','图片回应','图文互动','配文回应'}]
        tags+=['头像替换'] if im else []
        tags+=['原字替换'] if tx else []
        hint=('先框选头像，替换原图中的脸；发型、动作和道具保留。' if im else '')+('在原有位置替换完整配文，可换行。' if tx else '原文字保留。')
        if decision.get('fixed_note'):hint=decision['fixed_note']
        metadata={**old,'tags':list(dict.fromkeys(tags)),'min_images':im,'max_images':im,'min_texts':tx,'max_texts':tx,'default_texts':spec['defaults'],
                  'input_hint':hint,'conversion':'element-replacement-v1','source_canvas':source['canvas'],'animated':source['frames']>1,
                  'caption_inventory':draft['caption_inventory'],
                  'intent':{'fixed':'原场景、动作、道具及注明固定的原字','replaceable':'原图内的头像和/或原始配文','reference_reaction':source['name']},
                  'review':{'visual_status':'approved','method':'source elements and actual replacement outputs reviewed; per-frame authored motion reviewed','review_revision':hashlib.sha256(args.decisions.read_bytes()).hexdigest()},
                  'quality':{k:v for k,v in a.items() if k not in {'frames','key','index','reason'}}}
        metadata['quality']['caption_inventory_complete']=True
        validate_elements(spec,metadata)
        for digest in asset_refs(spec):
            path=next(p for suffix in ['.png','.gif'] if (p:=root()/'template_assets'/(digest+suffix)).is_file())
            raw=path.read_bytes()
            if hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('asset mismatch')
            assets[digest]=base64.b64encode(raw).decode()
        items.append({'key':key,'version':2,'metadata':metadata,'spec':spec})
    if set(approved)!={i['key'] for i in items}:raise ValueError('review includes unknown keys')
    args.output.mkdir(parents=True,exist_ok=True)
    batch=[];needed=set();number=0
    def flush():
        nonlocal batch,needed,number
        if not batch:return
        number+=1;payload={'version':1,'templates':batch,'assets':{d:assets[d] for d in sorted(needed)}}
        data=json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode()
        if len(data)>32*1024*1024:raise ValueError('batch too large')
        (args.output/f'20261022-elements-{number:02d}.json').write_bytes(data+b'\n');batch=[];needed=set()
    for item in items:
        hashes=asset_refs(item['spec'])
        if batch and (len(batch)>=80 or sum(len(assets[d]) for d in needed|hashes)>8*1024*1024):flush()
        batch.append(item);needed.update(hashes)
    flush()
    (args.output/'20261022-elements-pending.json').write_text(json.dumps({'version':1,'templates':[],'assets':{},'withdrawals':pending},ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'published':len(items),'pending':len(pending),'animated':sum(i['metadata']['animated'] for i in items),'types':Counter('mixed' if i['metadata']['max_images'] and i['metadata']['max_texts'] else 'image' if i['metadata']['max_images'] else 'text' for i in items),'batches':number},ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
    for name in ['audit','sheets','export']:
        s=sub.add_parser(name);s.add_argument('--inventory',type=Path,required=True);s.add_argument('--drafts',type=Path,required=True);s.add_argument('--output',type=Path,required=True)
        if name in {'audit','sheets'}:s.add_argument('--photo',type=Path,required=True)
        if name=='export':
            s.add_argument('--audit',type=Path,required=True);s.add_argument('--decisions',type=Path,required=True);s.add_argument('--authoring',type=Path,required=True)
    args=p.parse_args();{'audit':audit,'sheets':sheets,'export':export}[args.command](args)
