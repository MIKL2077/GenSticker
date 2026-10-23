"""Qualify earlier isolated pilot outputs with the final independent VLM gate.
Only this private pilot database is updated. Production is never changed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
from PIL import Image
from meme_generator.features.minimax_authoring import MiniMax,cross_validate,normalize,local_proposals,verify_face_geometry
from meme_generator.features.declarative import Layer
from meme_generator.features.store import connect,root


def main():
    p=argparse.ArgumentParser();p.add_argument('--state',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    os.environ['GENSTICKER_STATE_DIR']=str(args.state);client=MiniMax(limit=12);db=connect();report=[]
    try:
        rows=list(db.execute('SELECT t.key,t.metadata,t.spec FROM templates t JOIN template_publications p ON p.key=t.key'))
        for row in rows:
            metadata=json.loads(row['metadata']);folder=root()/'authoring_evidence'/row['key'];boards=[]
            for path in sorted(folder.glob('*.jpg'),key=lambda p:int(p.stem)):
                with Image.open(path) as image:boards.append(('Source/opaque/empty text/new text/cutout; source frame '+path.stem,image.convert('RGB')))
            try:
                raw=(root()/'authoring_sources'/(hashlib.sha256(metadata['image_url'].encode()).hexdigest()+'.image')).read_bytes();_,frames,_=normalize(raw);spec=json.loads(row['spec'])
                plans=[[Layer.model_validate(l) for l in frame['layers'] if l['type'] in {'face','text'}] for frame in spec['frames']]
                geometry=verify_face_geometry(plans,frames,local_proposals(frames))
                if not geometry['verified']:raise ValueError('local geometry unverified: '+geometry.get('reason',''))
                result=cross_validate(client,boards,metadata['quality']['source_contract']);metadata['quality']['cross_visual_review']=result
                metadata['quality']['local_geometry']=geometry
                with db:db.execute('UPDATE templates SET metadata=? WHERE key=?',(json.dumps(metadata,ensure_ascii=False),row['key']))
                report.append({'key':row['key'],'status':'vlm-passed-awaiting-independent-review','frames':len(boards),'review':result})
            except ValueError as error:
                with db:db.execute("UPDATE templates SET status='withdrawn' WHERE key=?",(row['key'],))
                report.append({'key':row['key'],'status':'rejected','reason':str(error)[:400]})
        args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False))
    finally:db.close();client.close()


if __name__=='__main__':main()
