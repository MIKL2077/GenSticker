#!/usr/bin/env python3
"""Build a versioned full-library gallery; retain every case and prior label."""
import argparse, copy, json, math, shutil
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps


def first_image(path, size):
    with Image.open(path) as image:return ImageOps.contain(image.convert('RGB'),size)


def main():
    p=argparse.ArgumentParser()
    for name in ['evaluation','updates','annotations','inputs','assets','output','review-file']:
        p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();report=json.loads((a.evaluation/'report.json').read_text())
    if report['status']!='completed':raise ValueError('evaluation still running')
    updates={i['key']:i for i in json.loads((a.updates/'compiled.json').read_text())}
    annotations=json.loads(a.annotations.read_text());old_templates={t['id']:t for t in annotations['templates']}
    a.output.mkdir(parents=True,exist_ok=True)
    for name in ['sources','thumbs','contacts','regions']:(a.output/name).mkdir(exist_ok=True)
    if not (a.output/'media').exists():(a.output/'media').symlink_to((a.evaluation/'media').resolve(),target_is_directory=True)
    for sample in report['samples']:shutil.copy2(a.inputs/(sample+'.png'),a.output/'sources'/(sample+'.png'))
    font=ImageFont.truetype(str(Path(__file__).resolve().parents[2]/'backend/meme-generator/resources/fonts/NotoSansSC-Regular.ttf'),13)
    cases={c['key']:c for c in report['cases']};loop_mismatches=0
    for t in report['templates']:
        c=cases[t['key']]
        if int(t['id'][1:])>100:t['previous_rating']='新增测试'
        if t.get('preview'):first_image(a.evaluation/'media'/t['preview'],(350,270)).save(a.output/'thumbs'/(t['id']+'-template.jpg'),quality=86)
        else:
            empty=Image.new('RGB',(320,240),'#eef2f6');ImageDraw.Draw(empty).text((20,100),'无原生示例',font=font,fill='#71849a');empty.save(a.output/'thumbs'/(t['id']+'-template.jpg'))
        for variant,suffix in [('baseline','before'),('result','after')]:
            if c.get(variant):
                path=a.evaluation/'media'/c[variant]['file'];first_image(path,(350,270)).save(a.output/'thumbs'/(t['id']+'-'+suffix+'.jpg'),quality=88)
                with Image.open(path) as image:c[variant]['loop']=image.info.get('loop')
        if c.get('baseline') and c.get('result'):
            c['loop_matches_baseline']=c['baseline']['loop']==c['result']['loop'];loop_mismatches+=not c['loop_matches_baseline']
        count=c.get('result',{}).get('frames',1)
        if count>1:
            columns=6;cell=114;rows=math.ceil(count/columns)
            sheet=Image.new('RGB',(columns*cell*3,rows*(cell+22)+30),'#eef2f6');draw=ImageDraw.Draw(sheet)
            draw.text((8,5),t['id']+' · 每组：原模板 / 调整前 / 当前 · 完整输出帧',font=font,fill='#20384f')
            for variant,col,file in [('source',0,t.get('preview')),('baseline',1,c.get('baseline',{}).get('file')),('result',2,c.get('result',{}).get('file'))]:
                if not file:continue
                with Image.open(a.evaluation/'media'/file) as im:
                    for index in range(count):
                        im.seek(min(index,getattr(im,'n_frames',1)-1));small=ImageOps.contain(im.convert('RGB'),(cell-4,cell-4));x=(index%columns)*cell*3+col*cell;y=(index//columns)*(cell+22)+30
                        sheet.paste(small,(x+(cell-small.width)//2,y+20+(cell-small.height)//2));draw.text((x+4,y),str(index+1),font=font,fill='#20384f')
            sheet.save(a.output/'contacts'/(t['id']+'.jpg'),quality=87)
        item=updates.get(t['key'])
        if item and item['metadata']['expression_policy'].get('calibration',{}).get('action')=='region-repair':
            frames=item['spec'].get('frames') or [item['spec']];cols=6;cell=180
            sheet=Image.new('RGB',(cols*cell,math.ceil(len(frames)/cols)*210+30),'#eef2f6');draw=ImageDraw.Draw(sheet)
            draw.text((8,5),t['id']+' · 绿色为可替换范围；其余区域保持原图',font=font,fill='#20384f')
            for index,frame in enumerate(frames):
                layer=next(l for l in frame['layers'] if l['type']=='face');recipe=layer['expression']
                ext='.'+recipe.get('reference_format','png');path=a.assets/(recipe['reference_asset']+ext)
                with Image.open(path) as im:im.seek(recipe.get('reference_index',0));source=im.convert('RGB')
                with Image.open(a.assets/(recipe['mask_asset']+'.png')) as mask:
                    overlay=Image.new('RGB',source.size,'#22ca7a');opacity=mask.convert('L').point(lambda x:round(x*.35));source=Image.composite(overlay,source,opacity)
                source=ImageOps.contain(source,(174,174));x=(index%cols)*cell;y=(index//cols)*210+30
                sheet.paste(source,(x+(cell-source.width)//2,y+24));draw.text((x+5,y),f'帧 {index+1} / 源 {frame.get("source_index",0)}',font=font,fill='#20384f')
            t['region_sheet']=t['id']+'.jpg';sheet.save(a.output/'regions'/t['region_sheet'],quality=90)
            t['change_note']='已重新测量替换范围与五官位置，保留原场景、道具和文字。请复核完整脸部与动画。'
        elif item and t['previous_rating']=='需调整':t['change_note']='上传图位于标志牌内，已恢复直接贴图，不再借用背景人物的表情。'
        else:t['change_note']='本轮实际生成结果；可点击大图查看完整动画。'
    report['loop_mismatches']=loop_mismatches
    (a.evaluation/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    browser=copy.deepcopy(report)
    for c in browser['cases']:
        for name in ['baseline','result']:
            if c.get(name):c[name].pop('frame_hashes',None)
    (a.output/'data.json').write_text(json.dumps(browser,ensure_ascii=False))
    shutil.copy2(Path(__file__).with_name('template_review_gallery.html'),a.output/'index.html')
    if not a.review_file.exists():
        records={}
        for oldkey,label in annotations['ratings'].items():
            tid,sample=oldkey.rsplit('-',1);t=old_templates[tid]
            key=f"{t['key']}@{t['version']}:{sample}"
            records[key]={'key':t['key'],'version':t['version'],'sample':sample,'rating':label,'note':'','origin':'previous-round','updated_at':0}
        for t in report['templates']:
            if t['changed'] and t['previous_rating']=='不需要':
                key=f"{t['key']}@{t['version']}:S03"
                records[key]={'key':t['key'],'version':t['version'],'sample':'S03','rating':'不需要','note':'','origin':'direct-paste-request-applied','updated_at':0}
        a.review_file.write_text(json.dumps({'format':'gensticker-template-review-v2','records':records},ensure_ascii=False,indent=2))
    print(json.dumps({'templates':len(report['templates']),'cases':len(report['cases']),'counts':report['counts'],'loops':loop_mismatches,'gallery':str(a.output)},ensure_ascii=False))


if __name__=='__main__':main()
