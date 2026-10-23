"""Compare a newly authored recipe against the last accepted recipe on identical
source bytes, avatar and captions. Run against an isolated state, never publish.
"""
import argparse
from io import BytesIO
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
from PIL import Image,ImageDraw,ImageSequence
from meme_generator.features.minimax_authoring import MiniMax,author
from meme_generator.features.declarative import render
from meme_generator.features.storage import asset_refs
from meme_generator.features.scheduled_authoring import staging


def main():
 p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path,required=True);p.add_argument('--state',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--model',choices=['MiniMax-M3','MiniMax-M3.1-Flash']);args=p.parse_args()
 if args.model:os.environ['GENSTICKER_MINIMAX_MODEL']=args.model
 args.output.mkdir(parents=True,exist_ok=True);rows=json.loads(args.manifest.read_text());db=sqlite3.connect('file:'+str(args.state/'features/features.sqlite3')+'?mode=ro',uri=True);db.row_factory=sqlite3.Row
 records=[];client=MiniMax(limit=30)
 photo=Image.open(Path(__import__('meme_generator.features.minimax_authoring',fromlist=['x']).__file__).with_name('authoring')/'validation-cat.jpg').convert('RGBA')
 try:
  for item in rows:
   baseline=db.execute('SELECT * FROM templates WHERE key=?',(item['key'],)).fetchone()
   if not baseline:raise ValueError('accepted baseline missing')
   meta=json.loads(baseline['metadata']);spec=json.loads(baseline['spec']);folder=args.output/item['key'];folder.mkdir(exist_ok=True)
   record={'key':item['key'],'name':meta['name'],'baseline_version':baseline['version'],'status':'pending'}
   with tempfile.TemporaryDirectory(prefix='qa-authoring-') as temp:
    with staging(temp):
     destination=Path(temp)/'features/template_assets';destination.mkdir(parents=True)
     for digest in asset_refs(spec):
      source=next(p for suffix in ['.png','.gif'] if (p:=args.state/'features/template_assets'/(digest+suffix)).exists());shutil.copy2(source,destination/source.name)
     baseline_image=render(spec,[photo]*meta['max_images'],['新表情' if '\n' not in t else '新表情\n来啦' for t in meta['default_texts']]).getvalue()
     (folder/('baseline.gif' if meta.get('animated') else 'baseline.png')).write_bytes(baseline_image)
     try:
      product=author(client,Path(item['path']).read_bytes(),meta,photo,max_repairs=2)
      output=render(product['spec'],[photo]*product['metadata']['max_images'],['新表情' if '\n' not in t else '新表情\n来啦' for t in product['metadata']['default_texts']]).getvalue()
      suffix='.gif' if product['metadata']['animated'] else '.png';(folder/('minimax'+suffix)).write_bytes(output)
      (folder/'recipe.json').write_text(json.dumps({'metadata':product['metadata'],'spec':product['spec'],'review':product['review']},ensure_ascii=False,indent=2))
      for index,(_,board) in enumerate(product['boards']):board.save(folder/('review-'+str(index)+'.jpg'),quality=90)
      with Image.open(BytesIO(baseline_image)) as b,Image.open(BytesIO(output)) as m:
       baseline_frames=[f.convert('RGB').copy() for f in ImageSequence.Iterator(b)];model_frames=[f.convert('RGB').copy() for f in ImageSequence.Iterator(m)]
       record.update(status='model-and-local-passed-awaiting-independent-review',baseline_frames=len(baseline_frames),minimax_frames=len(model_frames),baseline_image_slots=meta['max_images'],minimax_image_slots=product['metadata']['max_images'],baseline_text_slots=meta['max_texts'],minimax_text_slots=product['metadata']['max_texts'],score=product['metadata']['quality']['score'])
       # Every source frame appears in the comparison strip, not just key poses.
       width=max(baseline_frames[0].width,model_frames[0].width);height=max(baseline_frames[0].height,model_frames[0].height)
       sheet=Image.new('RGB',(width*2,(height+24)*len(model_frames)),'white');draw=ImageDraw.Draw(sheet)
       for i,frame in enumerate(model_frames):
        y=i*(height+24);draw.text((4,y+3),'Accepted baseline / MiniMax | frame '+str(i),fill='black');sheet.paste(baseline_frames[min(i,len(baseline_frames)-1)],(0,y+24));sheet.paste(frame,(width,y+24))
       sheet.save(folder/'all-frames-comparison.jpg',quality=90)
     except Exception as error:
      record.update(status='rejected',reason=str(error)[:400])
      if client.last_json:(folder/'last-model-result.json').write_text(json.dumps(client.last_json,ensure_ascii=False,indent=2))
      if getattr(client,'last_plan',None):(folder/'last-plan.json').write_text(json.dumps(client.last_plan,ensure_ascii=False,indent=2))
      for i,(_,board) in enumerate(getattr(client,'last_boards',[])):board.save(folder/('rejected-review-'+str(i)+'.jpg'),quality=90)
      client.last_boards=[];client.last_plan=None
   records.append(record);(args.output/'report.json').write_text(json.dumps({'model':client.model,'cases':records,'model_calls':client.calls,'model_tokens':client.tokens,'published':0},ensure_ascii=False,indent=2));print(json.dumps(record,ensure_ascii=False),flush=True)
 finally:db.close();client.close()


if __name__=='__main__':main()
