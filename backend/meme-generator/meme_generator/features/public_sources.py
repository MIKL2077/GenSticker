"""Public, attributed candidate adapters. No cookies, JavaScript or model URLs as code."""
import hashlib
import base64
from html.parser import HTMLParser
import ipaddress
import json
import os
from pathlib import PurePosixPath
import socket
import subprocess
import tempfile
import time
from urllib.parse import urlsplit,urljoin,quote,unquote
from .store import connect


class SourceUnavailable(ValueError):pass


def validate_url(url):
    value=urlsplit(url)
    if value.scheme!='https' or not value.hostname or value.username or value.password or value.port not in (None,443) or len(url)>2000:raise SourceUnavailable('public_https_url_required')
    host=value.hostname.encode('idna').decode()
    try:addresses=list(dict.fromkeys(r[4][0] for r in socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)))
    except OSError:raise SourceUnavailable('source_dns_unavailable') from None
    if not addresses or any((not ipaddress.ip_address(a).is_global or ipaddress.ip_address(a).is_multicast or ipaddress.ip_address(a).is_reserved) for a in addresses):raise SourceUnavailable('private_source_address_rejected')
    return host,next((a for a in addresses if ':' not in a),addresses[0])


def reserve_bytes(cap):
    db=connect();day=time.strftime('%Y-%m-%d',time.gmtime(time.time()+8*3600))
    try:
        with db:
            db.execute('BEGIN IMMEDIATE');db.execute('INSERT OR IGNORE INTO budgets(day) VALUES(?)',(day,))
            daily=db.execute('SELECT bytes FROM budgets WHERE day=?',(day,)).fetchone()[0]
            monthly=db.execute('SELECT COALESCE(sum(bytes),0) FROM budgets WHERE day LIKE ?',(day[:7]+'%',)).fetchone()[0]
            if daily+cap>200*1024**2 or monthly+cap>1024**3:raise SourceUnavailable('source_download_budget_exhausted')
            db.execute('UPDATE budgets SET bytes=bytes+? WHERE day=?',(cap,day))
    finally:db.close()
    return day


def fetch_public(url,cap=2*1024**2):
    cap=min(cap,12*1024**2)
    for redirect in range(4):
        host,address=validate_url(url);day=reserve_bytes(cap)
        address='['+address+']' if ':' in address else address
        settled=False
        try:
            with tempfile.NamedTemporaryFile() as headers:
                result=subprocess.run(['curl','--silent','--show-error','--fail','--noproxy','*','--connect-timeout','8','--max-time','35','--max-filesize',str(cap),'--proto','=https','--resolve',host+':443:'+address,'--dump-header',headers.name,'--write-out','\n%{http_code}','-H','User-Agent: GenSticker-public-template-collector/2.0',url],capture_output=True,timeout=40,check=True)
                payload,_,status=result.stdout.rpartition(b'\n');status=int(status)
                if len(payload)>cap:raise SourceUnavailable('source_response_too_large')
                db=connect()
                try:
                    with db:db.execute('UPDATE budgets SET bytes=bytes-?+? WHERE day=?',(cap,len(payload),day))
                finally:db.close()
                settled=True
                if 300<=status<400:
                    locations=[l.split(':',1)[1].strip() for l in open(headers.name).read().splitlines() if l.lower().startswith('location:')]
                    if not locations:raise SourceUnavailable('source_redirect_missing')
                    url=urljoin(url,locations[-1]);continue
                if status!=200:raise SourceUnavailable('source_http_'+str(status))
                return payload
        except (subprocess.SubprocessError,OSError) as error:
            partial=getattr(error,'stdout',b'') or b'';payload,separator,status=partial.rpartition(b'\n')
            received=min(cap,len(payload if separator and status.isdigit() else partial))
            # A failed connection did not download the entire reserved image.
            # Settle actual bytes, otherwise dead URLs can consume a month of
            # budget despite transferring nothing.
            if not settled:
                db=connect()
                try:
                    with db:db.execute('UPDATE budgets SET bytes=bytes-?+? WHERE day=?',(cap,received,day))
                finally:db.close()
            if separator and status.isdigit() and 400<=int(status)<=599:raise SourceUnavailable('source_http_'+status.decode()) from None
            raise SourceUnavailable('source_request_unavailable') from None
    raise SourceUnavailable('source_redirect_limit')


class PublicImages(HTMLParser):
    def __init__(self,page):super().__init__();self.page=page;self.images={};self.title='';self.in_title=False;self.links=[];self.hero=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='title':self.in_title=True
        if tag=='a' and a.get('href'):self.links.append(urljoin(self.page,a['href']))
        values=[]
        if tag=='img':values=[a.get(k,'') for k in ['data-original','data-src','src']]
        if tag=='meta' and (a.get('property') or a.get('name')) in {'og:image','twitter:image'}:values=[a.get('content','')]
        for value in values:
            if not value:continue
            value=urljoin(self.page,value)
            if len(value)>2000:continue
            # Some publisher og:image tags contain the canonical HTML page.
            if value.split('#',1)[0].split('?',1)[0]==self.page.split('#',1)[0].split('?',1)[0] or urlsplit(value).path.lower().endswith(('.html','.htm')):continue
            if urlsplit(value).scheme!='https' or any(v in urlsplit(value).path.lower() for v in ['/logo','/icon','/avatar','sprite','/platformemotion/','thumb_default','placeholder','/loading']):continue
            width=a.get('width','');height=a.get('height','')
            if (width.isdigit() and int(width)<64) or (height.isdigit() and int(height)<64):continue
            self.images.setdefault(value,(a.get('alt') or a.get('title') or '').strip()[:100])
            if tag=='meta':self.hero.append(value)
    def handle_endtag(self,tag):
        if tag=='title':self.in_title=False
    def handle_data(self,data):
        if self.in_title:self.title=(self.title+data)[:150]


def page_candidates(url):
    html=fetch_public(url,1024**2).decode('utf-8',errors='replace');parser=PublicImages(url);parser.feed(html)
    # Nuxt/SSR markup often puts observed image URLs in literal JSON strings.
    import re
    for match in re.finditer(r'https?(?::|\\u003A)(?:/|\\/){2}[^\s<>"\']+?\.(?:gif|png|jpe?g|webp)(?:\?[^\s<>"\']*)?',html,re.I):
        image=match.group().replace('\\/','/').replace('\\u003A',':')
        if len(image)<=2000 and image.startswith('https://') and not any(t in urlsplit(image).path.lower() for t in ['logo','icon','avatar','/platformemotion/','thumb_default','placeholder','/loading']):parser.images.setdefault(image,'')
    images=parser.images
    if urlsplit(url).hostname!='u.weshineapp.com':
        # General pages also show unrelated recommendation photos. Only their
        # explicitly declared main artwork can inherit the page's meme title.
        if not re.search(r'表情|梗图|斗图|熊猫头|meme|reaction',parser.title,re.I):return []
        images={image:parser.images[image] for image in parser.hero[:1]}
    return [{'name':name or parser.title or '表情素材','image_url':image,'source_url':url,'origin':urlsplit(url).hostname,'hotness_method':'observed-public-page-order','source_position':index} for index,(image,name) in enumerate(images.items())][:60]


def chinese_candidates():
    commit=json.loads(fetch_public('https://api.github.com/repos/zhaoolee/ChineseBQB/commits/master',128*1024))['sha']
    if len(commit)!=40 or any(c not in '0123456789abcdef' for c in commit):raise SourceUnavailable('immutable_source_revision_missing')
    listing=json.loads(fetch_public('https://api.github.com/repos/zhaoolee/ChineseBQB/contents?ref='+commit,512*1024))
    folders=[r for r in listing if r.get('type')=='dir' and 'BQB' in r.get('name','')]
    folders.sort(key=lambda r:r['name'])
    if not folders:return []
    offset=int(time.time()//21600)%len(folders);selected=[folders[(offset+i)%len(folders)] for i in range(min(6,len(folders)))]
    out=[]
    for folder in selected:
        path=quote(folder['path'],safe='/')
        items=json.loads(fetch_public('https://api.github.com/repos/zhaoolee/ChineseBQB/contents/'+path+'?ref='+commit,1024**2))
        for item in items:
            if item.get('type')!='file' or PurePosixPath(item.get('name','')).suffix.lower() not in {'.gif','.png','.jpg','.jpeg','.webp'} or item.get('size',0)>2*1024**2:continue
            file_path=quote(item['path'],safe='/')
            out.append({'name':PurePosixPath(item['name']).stem[:100],'image_url':'https://raw.githubusercontent.com/zhaoolee/ChineseBQB/'+commit+'/'+file_path,'source_url':'https://github.com/zhaoolee/ChineseBQB/blob/'+commit+'/'+file_path,'origin':'chinesebqb','source_revision':commit,'source_blob_sha':item['sha'],'category':folder['name'],'hotness_method':'rotating-category-not-a-trending-chart'})
    out.sort(key=lambda r:hashlib.sha256((str(int(time.time()//21600))+r['image_url']).encode()).hexdigest())
    return out[:60]


def fetch_candidate(item):
    # The Mainland application host times out on raw.githubusercontent.com.
    # Prefer GitHub's official immutable public blob transport for this adapter;
    # other public websites keep their observed image URLs. No credentials.
    sha=item.get('source_blob_sha','')
    if item.get('origin')!='chinesebqb' or len(sha)!=40 or any(c not in '0123456789abcdef' for c in sha):return fetch_public(item['image_url'])
    result=json.loads(fetch_public('https://api.github.com/repos/zhaoolee/ChineseBQB/git/blobs/'+sha,3*1024**2))
    if result.get('encoding')!='base64' or not 0<int(result.get('size',0))<=2*1024**2:raise SourceUnavailable('invalid_public_blob_size')
    raw=base64.b64decode(''.join(result['content'].split()),validate=True)
    if len(raw)!=result['size'] or hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()!=sha:raise SourceUnavailable('public_blob_hash_mismatch')
    return raw


def discover(client):
    if os.getenv('GENSTICKER_ALLOW_ATTRIBUTED_SOURCES','0')!='1':return [],[{'source':'policy','reason':'operator-attributed-source-policy-not-enabled'}]
    sources=[];errors=[];pages=['https://u.weshineapp.com/','https://u.weshineapp.com/rank/expression_tot_1']
    pages.extend(v.strip() for v in os.getenv('GENSTICKER_SOURCE_PAGES','').split(',') if v.strip())
    try:
        date=time.strftime('%Y年%m月%d日',time.gmtime(time.time()+8*3600))
        for result in (client.search(date+' 最近 热梗 表情包 原图 动图') if client is not None else []):
            url=result.get('link','') or result.get('url','')
            if url.startswith('https://'):pages.append(url)
    except ValueError as error:errors.append({'source':'hot-search','reason':str(error)[:100]})
    for page in list(dict.fromkeys(pages))[:8]:
        try:sources.extend(page_candidates(page))
        except ValueError as error:errors.append({'source':urlsplit(page).hostname,'reason':str(error)[:100]})
    try:sources.extend(chinese_candidates())
    except (ValueError,KeyError,TypeError) as error:errors.append({'source':'chinesebqb','reason':type(error).__name__})
    seen=set();unique=[]
    for item in sources:
        if item['image_url'] in seen:continue
        seen.add(item['image_url']);item.update(license='unverified',license_status='unverified',source_use='explicit-user-request-with-attribution',author='公开素材页收录（原作者未标明）',license_url='',collected_at=time.time())
        unique.append(item)
    # Interleave sources so a large character pack cannot fill the whole batch.
    from collections import defaultdict,deque
    groups=defaultdict(deque)
    for item in unique:groups[item['origin']].append(item)
    preferred=[groups.pop(name) for name in ['u.weshineapp.com','chinesebqb'] if name in groups]
    ordered=[]
    while any(groups.values()) or any(preferred):
        # Search pages also contain unrelated news photos, QR codes and chrome.
        # Give genuine meme catalogs more slots without excluding new websites.
        for group in preferred:
            for _ in range(2):
                if group:ordered.append(group.popleft())
        for group in groups.values():
            if group:ordered.append(group.popleft())
    return ordered[:120],errors
