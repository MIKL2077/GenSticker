"""Export only exact, technically checked, human-approved face choices.

Public source artwork only: never test portraits or resulting private media.
The output is a normal seed batch; review files remain private and durable.
"""
import argparse
import base64
import copy
import hashlib
import json
from pathlib import Path
import sys

REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO/'backend/meme-generator'))
from meme_generator.features.declarative import TemplateSpec
from meme_generator.features.element_templates import fingerprint,validate_elements
from meme_generator.features.reviewed_faces import validate_tenor_face
from meme_generator.features.storage import asset_refs


def export(directory,audit_directory,output):
    if (directory/'withdrawal.json').exists():raise ValueError('withdrawn batch')
    records=json.loads((directory/'reviews.json').read_text())['records']
    templates=[];assets={};batches=[]
    output.mkdir(parents=True,exist_ok=True)
    def flush():
        if not templates:return
        payload={'format':'gensticker-reviewed-face-v1','templates':templates.copy(),'assets':assets.copy()}
        raw=json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode()
        if len(raw)>32*1024**2:raise ValueError('batch exceeds byte bound')
        path=output/f'20261030-tenor-approved-{len(batches)+1:02d}.json'
        path.write_bytes(raw);batches.append({'file':path.name,'count':len(templates),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
        templates.clear();assets.clear()
    for key,review in records.items():
        if review.get('decision')!='approved':continue
        row=json.loads((directory/'drafts'/(key+'.json')).read_text())
        variant=row['variants'].get(review.get('method'),{})
        if (row['status']!='draft' or review['spec_sha256']!=row['spec_sha256']
                or review.get('selected_spec_sha256')!=variant.get('spec_sha256')
                or review['method'] in row.get('blocked_methods',{})):
            raise ValueError('stale/blocked approval: '+key)
        spec=TemplateSpec.model_validate(variant['spec']).model_dump()
        if fingerprint(spec)!=review['selected_spec_sha256']:raise ValueError('serialized recipe changed')
        audit=json.loads((audit_directory/'technical'/(key+'-'+review['method']+'.json')).read_text())
        if (audit['spec_sha256']!=fingerprint(spec) or audit['status']!='passed'
                or audit['protected_pixel_max_error']!=0 or audit['decoded_outputs']<3):
            raise ValueError('missing bound technical checks')
        metadata=copy.deepcopy(row['metadata'])
        annotation=hashlib.sha256(json.dumps(review,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
        actual_method=next(l for l in spec['frames'][0]['layers'] if l['type']=='face')['expression']['driver']['method']
        metadata.update(name=review['name'] or row['name'],keywords=review['keywords'],
            author=row.get('source_author') or '原作者未核实',animated=True,
            original_hash=row['original_sha256'],source_canvas=row['canvas'],conversion='element-replacement-v1',
            source_use='explicit-user-request-with-attribution',
            subject_types=['person','animal','object','unknown'],
            input_hint='上传头像，融合到猫脸内部并驱动表情；保留猫耳、身体、原字幕和场景。侧脸、眼镜遮挡效果可能受限。',
            review={'visual_status':'approved','source':'local-tenor-face-review','template_key':key,
                'method':'eye-v2' if actual_method=='geometry-eye-v2' else review['method'],
                'annotation_sha256':annotation,'selected_spec_sha256':fingerprint(spec),'reviewed_at':review['updated_at']},
            quality={'spec_sha256':fingerprint(spec),'analyzed_frames':len(spec['frames']),
                'protected_pixel_mae':0,'actual_replacement_verified':True,
                'caption_inventory_complete':True,'motion_verified':True,
                'decoded_outputs':audit['decoded_outputs'],'duration_ms':row['duration_ms']},
            expression_policy={'visual_status':'user-approved','disposition':'expression','mode':'A',
                'method':'cpu-expression-ab-v1','driver':actual_method,'authored_actions':True,
                'review':{'source':'local-tenor-face-review','annotation_sha256':annotation}})
        validate_elements(spec,metadata);validate_tenor_face(key,spec,metadata)
        item={'key':key,'version':1,'spec':spec,'metadata':metadata};extra={}
        for digest in asset_refs(spec):
            path=next((directory/'state/features/template_assets').glob(digest+'.*'))
            raw=path.read_bytes()
            if hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('asset checksum')
            extra[digest]=base64.b64encode(raw).decode()
        estimated=len(json.dumps({'templates':templates+[item],'assets':assets|extra},ensure_ascii=False).encode())
        if templates and (len(templates)>=100 or estimated>31*1024**2):flush()
        templates.append(item);assets.update(extra)
    flush()
    (output/'export-report.json').write_text(json.dumps({'approved':sum(b['count'] for b in batches),'batches':batches},indent=2)+'\n')
    return batches


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--directory',required=True,type=Path);p.add_argument('--audit-directory',required=True,type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    print(json.dumps(export(a.directory,a.audit_directory,a.output)))
