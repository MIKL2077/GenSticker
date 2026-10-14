"""Repeat private multi-layout tests from the maintained, image-free briefs."""
import argparse,json
from io import BytesIO
from pathlib import Path
from PIL import Image
from meme_generator.features.decomposition import decompose
from meme_generator.features.declarative import render
from meme_generator.features.subjects import extract_subject

parser=argparse.ArgumentParser()
parser.add_argument('--sample-dir',required=True)
parser.add_argument('--validation-photo',required=True)
parser.add_argument('--output-dir',required=True)
parser.add_argument('--extract-subject',action='store_true')
args=parser.parse_args();samples=Path(args.sample_dir);out=Path(args.output_dir);out.mkdir(parents=True,exist_ok=True)
with Image.open(args.validation_photo) as image:photo=image.convert('RGBA')
if args.extract_subject:
    buf=BytesIO();photo.save(buf,'PNG');photo=Image.open(BytesIO(extract_subject(buf.getvalue()))).copy()
briefs=Path(__file__).resolve().parents[1]/'references/regression-cases'
replacements={'cat':['BUILD OK','BUT THE USERS FIND A BUG'],'doge':['such tired'],'farmer':[]};reports=[]
for name,words in replacements.items():
    try:
        with Image.open(samples/(name+'.jpg')) as original:
            image=original.convert('RGB');image.thumbnail((750,750));buf=BytesIO();image.save(buf,'PNG')
        brief=json.loads((briefs/(name+'.json')).read_text())
        item=decompose(buf.getvalue(),brief,validation_photo=photo if name=='farmer' else None)
        (out/(name+'-reference.jpg')).write_bytes(render(item['spec'],[],preview=True).getvalue())
        (out/(name+'-replacement.jpg')).write_bytes(render(item['spec'],[photo] if name=='farmer' else [],words).getvalue())
        reports.append({'case':name,'status':'rendered-for-visual-review','visual_review':brief['metadata'].get('review',{}),'quality':item['metadata']['quality'],'source':brief['metadata']['source_url']})
    except Exception as exc:reports.append({'case':name,'status':'pending','reason':str(exc)})
(out/'report.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2)+'\n');print(json.dumps(reports,ensure_ascii=False))
