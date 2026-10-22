"""Compile a measured source-frame plan and real replacement previews, as drafts.

The plan contains frames (one list of Layer objects per source frame), defaults,
metadata and an optional stable key. It never publishes or confers approval.
"""
import argparse
from io import BytesIO
import json
from pathlib import Path

from PIL import Image

from meme_generator.features.declarative import render
from meme_generator.features.element_templates import compile_elements, fingerprint
from meme_generator.features.store import root


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('source',type=Path)
    parser.add_argument('plan',type=Path)
    parser.add_argument('--validation-photo',type=Path)
    parser.add_argument('--output-json',required=True,type=Path)
    parser.add_argument('--preview-dir',required=True,type=Path)
    args=parser.parse_args()
    plan=json.loads(args.plan.read_text())
    spec,assets,geometry=compile_elements(args.source.read_bytes(),plan['frames'],plan.get('defaults',[]))
    faces=max((layer['slot']+1 for frame in spec['frames'] for layer in frame['layers'] if layer['type']=='face'),default=0)
    if faces and not args.validation_photo:parser.error('face plans require --validation-photo; source previews do not test replacements')
    photos=[]
    if args.validation_photo:
        with Image.open(args.validation_photo) as source:photos=[source.convert('RGBA')]*faces
    directory=root()/'template_assets';directory.mkdir(parents=True,exist_ok=True)
    for digest,data in assets.items():
        (directory/(digest+('.gif' if data.startswith(b'GIF') else '.png'))).write_bytes(data)
    args.preview_dir.mkdir(parents=True,exist_ok=True)
    suffix='.gif' if len(spec['frames'])>1 else '.png'
    (args.preview_dir/'reference.png').write_bytes(render(spec,[],preview=True).getvalue())
    variants={'replacement':spec['defaults'],'captions-blank':['']*len(spec['defaults']),
              'captions-short':['新文案']*len(spec['defaults'])}
    if any('\n' in s for s in spec['defaults']):variants['captions-multiline']=['第一行\n第二行']*len(spec['defaults'])
    checks={}
    for name,texts in variants.items():
        try:
            result=render(spec,photos,texts)
            (args.preview_dir/(name+suffix)).write_bytes(result.getvalue())
            checks[name]='rendered-for-visual-review'
        except ValueError as error:checks[name]=str(error)
    result={'key':plan.get('key'),'spec':spec,'geometry':geometry,'metadata':{
        **plan.get('metadata',{}),'review':{'visual_status':'draft'},
        'quality':{'spec_sha256':fingerprint(spec),'analyzed_frames':len(spec['frames']),
                   'actual_input_rendered':bool(faces and args.validation_photo),'checks':checks}}}
    args.output_json.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':'draft','frames':len(spec['frames']),'image_slots':faces,'checks':checks},ensure_ascii=False))


if __name__=='__main__':main()
