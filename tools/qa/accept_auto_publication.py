"""Exercise the real scheduled publisher on an explicit public-source manifest.

No bypass or alternate approval path: each item is freshly authored and must
pass all production gates. Run with the normal service user/env/budgets. Keep
the manifest/results private; it contains public-source URLs, never user photos.
"""
import argparse
import json
from pathlib import Path
import time
from urllib.parse import quote,unquote,urlsplit
from meme_generator.features.minimax_authoring import MiniMax
from meme_generator.features.public_sources import fetch_public
from meme_generator.features.scheduled_authoring import run


def main():
    p=argparse.ArgumentParser();p.add_argument('--candidates',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--publish',action='store_true')
    args=p.parse_args()
    if not args.publish:p.error('explicit --publish is required; this exercises the live catalog')
    items=json.loads(args.candidates.read_text())
    if not isinstance(items,list) or not 1<=len(items)<=10:p.error('1-10 explicit public candidates required')
    for item in items:
        if item.get('origin')=='chinesebqb' and not item.get('source_blob_sha'):
            parts=urlsplit(item['source_url']).path.split('/',5)
            if parts[1:4]!=['zhaoolee','ChineseBQB','blob']:raise ValueError('unexpected public repository')
            revision=parts[4];path=quote(unquote(parts[5]),safe='/')
            entry=json.loads(fetch_public('https://api.github.com/repos/zhaoolee/ChineseBQB/contents/'+path+'?ref='+revision,3*1024**2))
            item['source_blob_sha']=entry['sha']
        item['collected_at']=time.time()
    client=MiniMax(limit=24)
    try:report=run(client=client,candidates=items,force=True,target=3,max_attempts=len(items))
    finally:client.close()
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
