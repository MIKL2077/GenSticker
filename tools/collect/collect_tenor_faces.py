"""Public Tenor search references for private, face-first template authoring.

Read literal SSR JSON; use observed original media URLs, never execute scripts
or infer a full-size URL. Collection is not a reuse license or publication.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
import hashlib
import json
from pathlib import Path
import re
import sys
import time
import urllib.request

sys.path.insert(0,str(Path(__file__).resolve().parent))
from prepare_expansion_review import normalize, save


class State(HTMLParser):
    def __init__(self):
        super().__init__();self.active=False;self.parts=[]
    def handle_starttag(self,tag,attrs):
        if tag=='script':self.active=dict(attrs).get('id')=='store-cache'
    def handle_data(self,data):
        if self.active:self.parts.append(data)
    def handle_endtag(self,tag):
        if tag=='script':self.active=False


def get(url,limit):
    from urllib.parse import urlsplit
    parsed=urlsplit(url)
    if parsed.scheme!='https' or not (parsed.hostname=='tenor.com' or re.fullmatch(r'media\d*\.tenor\.com',parsed.hostname or '')):
        raise ValueError('unexpected reference host')
    request=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
    with urllib.request.urlopen(request,timeout=30) as response:
        raw=response.read(limit+1)
    if len(raw)>limit:raise ValueError('reference exceeds byte budget')
    return raw


def collect(directory,limit=140):
    directory.mkdir(parents=True,exist_ok=True)
    searches=['cat','funny-cat','cat-meme','cat-blink','cat-laugh','cat-scream','cat-angry','cat-happy']
    rows={}
    for term in searches:
        url='https://tenor.com/zh-CN/search/'+term+'-gifs'
        path=directory/(term+'.html')
        if not path.exists():path.write_bytes(get(url,3_000_000))
        parser=State();parser.feed(path.read_text())
        state=json.loads(''.join(parser.parts))
        groups=state.get('universal',{}).get('search',{}).values()
        for group in groups:
            for index,item in enumerate(group.get('results',[])):
                if not re.fullmatch(r'\d{1,24}',str(item.get('id',''))):
                    continue
                media=item.get('media_formats',{}).get('gif',{})
                if not media.get('url') or media.get('size',0)>12*1024**2:continue
                if min(media.get('dims',[0]))<110:continue
                if item['id'] in rows:continue
                rows[item['id']]={'origin':'tenor','source_id':item['id'],
                    'source_url':item['itemurl'],'image_url':media['url'],
                    'name':item.get('title') or item.get('h1_title') or item.get('content_description',''),
                    'description':item.get('content_description',''),'source_tags':item.get('tags',[]),
                    'source_shares':item.get('shares'),'source_created':item.get('created'),
                    'source_author':(item.get('user') or {}).get('username'),
                    'source_search':url,'search_position':index+1,'observed_at':'2026-10-30',
                    'license':'unverified','source_use':'explicit-user-request-private-reference'}
        print(json.dumps({'search':term,'unique':len(rows)}),flush=True)
    inventory=list(rows.values())
    save(directory/'source-inventory.json',inventory)
    for name in ['originals','sources','downloads']:(directory/name).mkdir(exist_ok=True)
    def score(row):
        text=(row['description']+' '+' '.join(row['source_tags'])).lower()
        facial=any(t in text for t in ['face','mouth','eyes','blink','yawn','scream','laugh','smile','cry','angry','stare','head shake'])
        return (not facial,-int(row.get('source_shares') or 0))
    chosen=sorted(inventory,key=score)[:limit]
    def download(row):
        result=directory/'downloads'/(row['source_id']+'.json')
        if result.exists():return json.loads(result.read_text())
        data={**row,'status':'pending'}
        try:
            raw=get(row['image_url'],12*1024**2)
            digest=hashlib.sha256(raw).hexdigest();original=directory/'originals'/(digest+'.gif')
            original.write_bytes(raw)
            normalized,meta=normalize(raw)
            if not meta['animated']:raise ValueError('single frame; not an animated face template')
            if meta['loop']!=0:raise ValueError('finite loop requires another adapter')
            normalized_hash=hashlib.sha256(normalized).hexdigest();path=directory/'sources'/(digest+'.gif')
            path.write_bytes(normalized)
            data.update(meta,status='source-ready',path=str(path.resolve()),original_path=str(original.resolve()),
                key='tenor_face_'+digest[:24],original_sha256=digest,normalized_sha256=normalized_hash)
        except Exception as error:data['reason']=type(error).__name__+': '+str(error)[:180]
        save(result,data);return data
    started=time.monotonic()
    with ThreadPoolExecutor(max_workers=4) as pool:out=list(pool.map(download,chosen))
    seen=set();unique=[]
    for row in out:
        digest=row.get('original_sha256')
        if digest and digest in seen:continue
        if digest:seen.add(digest)
        unique.append(row)
    save(directory/'inventory.json',unique)
    print(json.dumps({'indexed':len(inventory),'downloaded':len(out),
        'actual_animations':sum(x['status']=='source-ready' for x in unique),
        'seconds':round(time.monotonic()-started,1)}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--directory',type=Path,required=True)
    parser.add_argument('--limit',type=int,default=140);args=parser.parse_args()
    collect(args.directory.resolve(),max(1,min(200,args.limit)))
