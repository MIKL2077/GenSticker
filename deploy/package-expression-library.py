#!/usr/bin/env python3
"""Build a public-only, hash checked A/B runtime and library delta."""
import argparse,hashlib,json,subprocess,tarfile
from pathlib import Path


def main():
    p=argparse.ArgumentParser();p.add_argument('--host',required=True);p.add_argument('--identity',required=True);p.add_argument('--segmentation-model',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    project=Path(__file__).resolve().parents[1];base=project/'backend/meme-generator';folder=base/'meme_generator/features'
    names=['catalog','client_render','declarative','face_slot','storage','template_archive','expression_math','expression_runtime','expression_library']
    files=['meme_generator/app.py','meme_generator/features/worker.py']+['meme_generator/features/'+n+'.py' for n in names]+[str(p.relative_to(base)) for p in sorted((folder/'expression_batches').glob('*.json'))]
    from_digest='c6748b1253a99067ef71f7e26ca71096cd449baefa8f101900ea23016507e0e0'
    if hashlib.sha256(a.segmentation_model.read_bytes()).hexdigest()!=from_digest:raise ValueError('segmentation checksum mismatch')
    probe='import json,hashlib\nfrom pathlib import Path\nr=Path("/opt/gensticker-current").resolve();b=r/"meme-generator"\nnames='+repr(files)+'\nprint(json.dumps({"release":str(r),"files":{n:hashlib.sha256((b/n).read_bytes()).hexdigest() if (b/n).is_file() else None for n in names}}))'
    result=subprocess.run(['ssh','-i',a.identity,'-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=15',a.host,'python3 -'],input=probe,text=True,capture_output=True,check=True,timeout=40);old=json.loads(result.stdout)
    updates={item['key']:{'base_version':item['base_version'],'base_fingerprint':item['base_fingerprint'],'version':item['version'],'mode':item['metadata']['expression_policy']['mode']} for p in (folder/'expression_batches').glob('*.json') for item in json.loads(p.read_text())['templates']}
    manifest={'format':'gensticker-expression-deploy-v1','release':old['release'],'updates':updates,'files':{n:{'old_sha256':old['files'][n],'sha256':hashlib.sha256((base/n).read_bytes()).hexdigest()} for n in files},'model_sha256':from_digest}
    a.output.mkdir(parents=True,exist_ok=True);(a.output/'manifest.json').write_text(json.dumps(manifest,indent=2))
    with tarfile.open(a.output/'update.tar.gz','w:gz') as tar:
        for name in files:tar.add(base/name,arcname='runtime/'+name)
        tar.add(project/'deploy/apply-expression-library.py',arcname='apply.py')
        tar.add(a.output/'manifest.json',arcname='manifest.json');tar.add(a.segmentation_model,arcname='selfie_multiclass_256x256.tflite')
    print(json.dumps({'files':len(files),'templates':len(updates),'package_bytes':(a.output/'update.tar.gz').stat().st_size}))

if __name__=='__main__':main()
