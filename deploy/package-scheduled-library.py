#!/usr/bin/env python3
"""Prepare a bounded runtime delta against the target's current file hashes."""
import argparse,hashlib,json,subprocess,tarfile
from pathlib import Path


def main():
 p=argparse.ArgumentParser();p.add_argument('--host',required=True);p.add_argument('--identity',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 project=Path(__file__).resolve().parents[1];base=project/'backend/meme-generator';files=['meme_generator/app.py','meme_generator/meme.py']
 files+=['meme_generator/features/'+name+'.py' for name in ['catalog','seed','store','monitor','lifecycle','moderation','element_templates','minimax_authoring','public_sources','scheduled_authoring','template_archive','trials','share','declarative','face_slot','frame_render','studio','worker','public_preview','search_terms','common_scenes','face_fusion']]
 files+=['meme_generator/features/common_scenes.json','meme_generator/features/template_batches/20261027-face-repair.json']
 files += [str(f.relative_to(base)) for f in sorted((base/'meme_generator/features/template_batches').glob('20261027-cpu-fusion-*.json'))]
 files += [str(f.relative_to(base)) for f in (base/'meme_generator/features/authoring').iterdir() if f.is_file()]
 files += [str(f.relative_to(base)) for f in sorted((base/'meme_generator/assets/share').glob('cover-v*.jpg'))]
 probe='import json,hashlib\nfrom pathlib import Path\nr=Path("/opt/gensticker-current").resolve();base=r/"meme-generator"\nnames='+repr(files)+'\nprint(json.dumps({"release":str(r),"files":{n:hashlib.sha256((base/n).read_bytes()).hexdigest() if (base/n).is_file() else None for n in names}}))\n'
 result=subprocess.run(['ssh','-i',a.identity,'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',a.host,'python3 -'],input=probe,text=True,capture_output=True,check=True,timeout=30);old=json.loads(result.stdout)
 manifest={'release':old['release'],'minimum_templates':944,'files':{n:{'old_sha256':old['files'][n],'sha256':hashlib.sha256((base/n).read_bytes()).hexdigest()} for n in files}}
 manifest['template_updates']={item['key']:{'version':item['version'],'spec_sha256':item['metadata']['quality']['spec_sha256']} for path in (base/'meme_generator/features/template_batches').glob('20261027-cpu-fusion-*.json') for item in json.loads(path.read_text())['templates']}
 a.output.mkdir(parents=True,exist_ok=True);(a.output/'manifest.json').write_text(json.dumps(manifest,indent=2))
 with tarfile.open(a.output/'runtime-update.tar.gz','w:gz') as tar:
  for n in files:tar.add(base/n,arcname='runtime/'+n)
  for n in ['apply-scheduled-library.py','gensticker-ingest.service','gensticker-archive.service','gensticker-archive.timer','gensticker-template-admin']:tar.add(project/'deploy'/n,arcname=n)
  tar.add(a.output/'manifest.json',arcname='manifest.json')
 print('Prepared hash-checked delta:',len(files),'files')


if __name__=='__main__':main()
