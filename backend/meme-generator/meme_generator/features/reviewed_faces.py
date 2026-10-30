"""Admission evidence for the explicitly requested Tenor face-template library."""
import re
from urllib.parse import urlsplit
from .element_templates import fingerprint


def validate_tenor_face(key, spec, metadata):
    review=metadata.get('review',{})
    source=urlsplit(metadata.get('source_url',''))
    if (metadata.get('origin')!='tenor' or source.scheme!='https' or source.hostname!='tenor.com'
            or not source.path.startswith('/view/')
            or metadata.get('source_use')!='explicit-user-request-with-attribution'
            or metadata.get('license')!='unverified'):
        raise ValueError('unexpected Tenor reference provenance')
    if (review.get('source')!='local-tenor-face-review' or review.get('visual_status')!='approved'
            or review.get('template_key')!=key or review.get('selected_spec_sha256')!=fingerprint(spec)
            or not re.fullmatch('[a-f0-9]{64}',review.get('annotation_sha256',''))
            or [metadata.get(n) for n in ['min_images','max_images','min_texts','max_texts']]!=[1,1,0,0]):
        raise ValueError('missing recipe-bound face approval')
    method={'direct':'geometry-v1','geometry':'geometry-v1','gan':'ganimation-emotionnet-v1',
            'eye-v2':'geometry-eye-v2','eye-v4':'geometry-eye-v4',
            'hybrid':'ganimation-mouth-eye-v3'}.get(review.get('method'))
    layers=[l for f in spec.get('frames',[]) for l in f['layers'] if l['type']=='face']
    if not layers or not method or any((l.get('expression') or {}).get('driver',{}).get('method')!=method for l in layers):
        raise ValueError('reviewed face driver differs from approved output')
