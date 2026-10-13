import json
import sys
from pathlib import Path
from meme_generator.features.ingest import convert,LICENSES
from meme_generator.features.vision import warmup

if len(sys.argv)!=3: raise SystemExit('Usage: convert.py IMAGE METADATA_JSON')
metadata=json.loads(Path(sys.argv[2]).read_text())
if any(not metadata.get(k) for k in ('name','source_url','author','license','license_url')): raise SystemExit('Missing source attribution')
if metadata['license'] not in LICENSES: raise SystemExit('Unsupported license')
warmup()
spec=convert(Path(sys.argv[1]).read_bytes(),metadata)
print(json.dumps(spec,ensure_ascii=False))
