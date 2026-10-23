"""Read-only discovery/transport probe; never compiles or publishes a template."""
import json
from collections import Counter
from io import BytesIO
from pathlib import Path
import sys
from PIL import Image
from meme_generator.features.minimax_authoring import MiniMax
from meme_generator.features.public_sources import discover,fetch_public


def main():
    client=MiniMax(limit=1)
    try:
        candidates,errors=discover(client)
        downloads=[]
        for item in candidates[:6]:
            try:
                raw=fetch_public(item['image_url'])
                with Image.open(BytesIO(raw)) as image:
                    downloads.append({'url':item['image_url'],'bytes':len(raw),'format':image.format,'size':list(image.size),'frames':getattr(image,'n_frames',1)})
            except (ValueError,OSError) as error:downloads.append({'url':item['image_url'],'error':type(error).__name__+':'+str(error)[:100]})
        report={'candidates':len(candidates),'origins':dict(Counter(item['origin'] for item in candidates)),'source_errors':errors,'downloads':downloads,'published':0}
        Path(sys.argv[1]).write_text(json.dumps({'report':report,'candidates':candidates},ensure_ascii=False,indent=2))
        print(json.dumps(report,ensure_ascii=False))
    finally:client.close()


if __name__=='__main__':main()
