import argparse
import json
from pathlib import Path
from meme_generator.features.ingest import convert

parser=argparse.ArgumentParser()
parser.add_argument('image')
parser.add_argument('metadata_json')
parser.add_argument('--authorized-local',action='store_true',help='Only for an image explicitly supplied and requested by the owner; not a web ingestion bypass')
args=parser.parse_args()
metadata=json.loads(Path(args.metadata_json).read_text())
spec=convert(Path(args.image).read_bytes(),metadata,authorized_local=args.authorized_local)
print(json.dumps(spec,ensure_ascii=False))
