"""Verify identical recipes using real opaque/cutout inputs, without model calls."""
import argparse
from io import BytesIO
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
from PIL import Image,ImageDraw,ImageSequence
from meme_generator.features.declarative import render
from meme_generator.features.element_templates import compile_elements,fingerprint
from meme_generator.features.minimax_authoring import normalize
from meme_generator.features.scheduled_authoring import staging
from meme_generator.features.storage import asset_refs
from meme_generator.features.subjects import extract_subject


def main():
    p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path,required=True);p.add_argument('--state',type=Path,required=True);p.add_argument('--results',type=Path,required=True);args=p.parse_args()
    rows={r['key']:r for r in json.loads(args.manifest.read_text())}
    photo_path=Path(__import__('meme_generator.features.minimax_authoring',fromlist=['x']).__file__).with_name('authoring')/'validation-cat.jpg'
    photo=Image.open(photo_path).convert('RGBA');cutout=Image.open(BytesIO(extract_subject(photo_path.read_bytes()))).convert('RGBA');cutout.save(args.results/'validation-cutout.png')
    db=sqlite3.connect('file:'+str(args.state/'features/features.sqlite3')+'?mode=ro',uri=True);db.row_factory=sqlite3.Row;report=[]
    try:
        for path in sorted(args.results.glob('*/recipe.json')):
            key=path.parent.name;product=json.loads(path.read_text());baseline=db.execute('SELECT metadata,spec FROM templates WHERE key=?',(key,)).fetchone();oldmeta=json.loads(baseline['metadata']);oldspec=json.loads(baseline['spec']);spec=product['spec'];meta=product['metadata']
            plans=[[l for l in frame['layers'] if l['type'] in {'face','text'}] for frame in spec['frames']]
            rebuilt,assets,_=compile_elements(normalize(Path(rows[key]['path']).read_bytes())[0],plans,spec['defaults'])
            if fingerprint(rebuilt)!=fingerprint(spec):raise ValueError('recompilation changed tested recipe')
            with tempfile.TemporaryDirectory(prefix='qa-input-modes-') as temporary:
                with staging(temporary):
                    destination=Path(temporary)/'features/template_assets';destination.mkdir(parents=True)
                    for ref in asset_refs(oldspec):
                        src=next(p for suffix in ['.png','.gif'] if (p:=args.state/'features/template_assets'/(ref+suffix)).exists());shutil.copy2(src,destination/src.name)
                    for ref,data in assets.items():(destination/(ref+('.gif' if data.startswith(b'GIF') else '.png'))).write_bytes(data)
                    outputs=[];durations=[]
                    for name,recipe,m,avatar in [('Accepted/photo',oldspec,oldmeta,photo),('MiniMax/photo',spec,meta,photo),('Accepted/cutout',oldspec,oldmeta,cutout),('MiniMax/cutout',spec,meta,cutout)]:
                        data=render(recipe,[avatar]*m['max_images'],['新表情' if '\n' not in t else '新表情\n来啦' for t in m['default_texts']]).getvalue()
                        with Image.open(BytesIO(data)) as image:
                            outputs.append([f.convert('RGB').copy() for f in ImageSequence.Iterator(image)]);durations.append([int(f.info.get('duration',100)) for f in ImageSequence.Iterator(image)])
                    if len({len(frames) for frames in outputs})!=1 or len({sum(d) for d in durations})!=1:raise ValueError('input mode changed motion')
                    width,height=outputs[0][0].size
                    for index in range(len(outputs[0])):
                        sheet=Image.new('RGB',(width*4,height+24),'white');draw=ImageDraw.Draw(sheet)
                        for col,label in enumerate(['Accepted/photo','MiniMax/photo','Accepted/cutout','MiniMax/cutout']):draw.text((col*width+3,3),label,fill='black');sheet.paste(outputs[col][index],(col*width,24))
                        sheet.save(path.parent/('input-modes-'+str(index)+'.jpg'),quality=92)
                    report.append({'key':key,'status':'rendered-awaiting-independent-visual-review','recipe_sha256':fingerprint(spec),'real_local_extraction':True,'frames':len(outputs[0]),'durations_ms':durations})
        (args.results/'input-modes-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False))
    finally:db.close()


if __name__=='__main__':main()
