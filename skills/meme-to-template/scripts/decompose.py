"""Run a reviewed face/text brief in the GenSticker Python environment."""
import argparse
import json
from io import BytesIO
from pathlib import Path
from PIL import Image
from meme_generator.features.decomposition import decompose
from meme_generator.features.declarative import render

parser=argparse.ArgumentParser()
parser.add_argument('image')
parser.add_argument('brief_json')
parser.add_argument('--output-json',required=True)
parser.add_argument('--authorized-local',action='store_true')
parser.add_argument('--validation-photo')
parser.add_argument('--extract-subject',action='store_true')
parser.add_argument('--preview-dir')
parser.add_argument('--publish',action='store_true')
args=parser.parse_args()
photo=None
if args.validation_photo:
    if args.extract_subject:
        from meme_generator.features.subjects import extract_subject
        with Image.open(BytesIO(extract_subject(Path(args.validation_photo).read_bytes()))) as source:photo=source.copy()
    else:
        with Image.open(args.validation_photo) as source:photo=source.copy()
elif args.extract_subject:
    parser.error('--extract-subject requires --validation-photo')
result=decompose(Path(args.image).read_bytes(),json.loads(Path(args.brief_json).read_text()),authorized_local=args.authorized_local,validation_photo=photo,publish=args.publish)
Path(args.output_json).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
if args.preview_dir:
    directory=Path(args.preview_dir);directory.mkdir(parents=True,exist_ok=True)
    (directory/'reconstruction.jpg').write_bytes(render(result['spec'],[],preview=True).getvalue())
    if photo is not None:(directory/'replacement.jpg').write_bytes(render(result['spec'],[photo]).getvalue())
print(json.dumps({'key':result['key'],'quality':result['metadata']['quality'],'published':args.publish},ensure_ascii=False))
