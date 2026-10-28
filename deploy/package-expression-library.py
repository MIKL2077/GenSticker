#!/usr/bin/env python3
"""Build a public-only, hash checked A/B runtime and library delta."""
import argparse,hashlib,json,subprocess,tarfile
from pathlib import Path


def main():
    p=argparse.ArgumentParser();p.add_argument('--host',required=True);p.add_argument('--identity',required=True);p.add_argument('--segmentation-model',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--batch',action='append',help='Deploy only these batch basenames; historical batches stay installed.')
    p.add_argument('--reviewed-drivers',action='store_true',help='Package only the reviewed driver runtime, without unrelated native edits.')
    p.add_argument('--driver-model',type=Path)
    a=p.parse_args()
    project=Path(__file__).resolve().parents[1];base=project/'backend/meme-generator';folder=base/'meme_generator/features'
    names=['catalog','client_render','declarative','face_slot','storage','template_archive','expression_math','expression_runtime','expression_library','expression_controls']
    if a.reviewed_drivers:
        if not a.batch or not a.driver_model:raise ValueError('reviewed drivers require explicit batches and the pinned model')
        names=['declarative','storage','expression_math','expression_runtime','expression_library','expression_controls','expression_driver']
    batches=sorted((folder/'expression_batches').glob('*.json'))
    if a.batch:
        if any(Path(n).name!=n or not n.endswith('.json') for n in a.batch):raise ValueError('invalid batch basename')
        batches=[folder/'expression_batches'/n for n in a.batch]
        if any(not p.is_file() for p in batches):raise ValueError('missing selected batch')
    files=([] if a.reviewed_drivers else ['meme_generator/memes/charpic/__init__.py','meme_generator/app.py','meme_generator/features/worker.py'])+['meme_generator/features/'+n+'.py' for n in names]+[str(p.relative_to(base)) for p in batches]
    if a.batch:
        files += ['meme_generator/features/authoring/'+name for name in ['SKILL.md','in-place-elements.md','references/review-calibration.md']]
    from_digest='c6748b1253a99067ef71f7e26ca71096cd449baefa8f101900ea23016507e0e0'
    if hashlib.sha256(a.segmentation_model.read_bytes()).hexdigest()!=from_digest:raise ValueError('segmentation checksum mismatch')
    probe='import json,hashlib\nfrom pathlib import Path\nr=Path("/opt/gensticker-current").resolve();b=r/"meme-generator"\nnames='+repr(files)+'\nprint(json.dumps({"release":str(r),"files":{n:hashlib.sha256((b/n).read_bytes()).hexdigest() if (b/n).is_file() else None for n in names}}))'
    result=subprocess.run(['ssh','-i',a.identity,'-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','ConnectTimeout=15',a.host,'python3 -'],input=probe,text=True,capture_output=True,check=True,timeout=40);old=json.loads(result.stdout)
    updates={item['key']:{'base_version':item['base_version'],'base_fingerprint':item['base_fingerprint'],'version':item['version'],'mode':item['metadata']['expression_policy']['mode'],
                         'driver':item['metadata']['expression_policy'].get('driver'),'visual_status':item['metadata']['expression_policy']['visual_status']} for p in batches for item in json.loads(p.read_text())['templates']}
    manifest={'format':'gensticker-expression-deploy-v1','release':old['release'],'updates':updates,'files':{n:{'old_sha256':old['files'][n],'sha256':hashlib.sha256((base/n).read_bytes()).hexdigest()} for n in files},'model_sha256':from_digest}
    if a.reviewed_drivers:
        driver_sha='e4ceefd1c354a1e13a1d46e322108aeb5024d846ee7536468d19aca3f51b6f46'
        if a.driver_model.stat().st_size>36_000_000 or hashlib.sha256(a.driver_model.read_bytes()).hexdigest()!=driver_sha:raise ValueError('driver model checksum mismatch')
        manifest['driver_model']={'name':'ganimation-emotionnet-v1.onnx','sha256':driver_sha}
    a.output.mkdir(parents=True,exist_ok=True);(a.output/'manifest.json').write_text(json.dumps(manifest,indent=2))
    with tarfile.open(a.output/'update.tar.gz','w:gz') as tar:
        for name in files:tar.add(base/name,arcname='runtime/'+name)
        tar.add(project/'deploy/apply-expression-library.py',arcname='apply.py')
        tar.add(a.output/'manifest.json',arcname='manifest.json');tar.add(a.segmentation_model,arcname='selfie_multiclass_256x256.tflite')
        if a.reviewed_drivers:tar.add(a.driver_model,arcname=manifest['driver_model']['name'])
    print(json.dumps({'files':len(files),'templates':len(updates),'package_bytes':(a.output/'update.tar.gz').stat().st_size}))

if __name__=='__main__':main()
