"""Private loopback review of unpublished source-element candidates.

Decisions bind key + recipe hash; writing a rating never publishes a template.
Private test portraits/media must remain outside source-controlled bundles.
"""
import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
import json
import mimetypes
from pathlib import Path
import re
import threading
import time
from urllib.parse import unquote, urlsplit

from PIL import Image, ImageDraw, ImageOps

HERE = Path(__file__).resolve().parent


class Review:
    def __init__(self, directory):
        self.directory = directory.resolve()
        self.lock = threading.RLock()
        self.updated = 0
        self.rows = {}
        self.selection = {}
        self.file = self.directory/'reviews.json'
        self.records = json.loads(self.file.read_text()).get('records',{}) if self.file.exists() else {}

    def refresh(self):
        with self.lock:
            if time.monotonic()-self.updated < 5:
                return
            self.rows = {}
            selection = self.directory/'selection.json'
            self.selection = json.loads(selection.read_text()) if selection.exists() else {}
            for path in (self.directory/'drafts').glob('*.json'):
                row = json.loads(path.read_text())
                if self.selection and row['key'] not in self.selection['keys'] and row['key'] not in self.records:
                    continue
                self.rows[row['key']] = row
            self.updated = time.monotonic()

    def data(self):
        self.refresh()
        withdrawal = self.directory/'withdrawal.json'
        if withdrawal.exists():
            return {'baseline':959,'target':1500,'needed':541,'rows':[],
                    'draft_count':0,'animated_drafts':0,'records':self.records,
                    'withdrawn':json.loads(withdrawal.read_text()),'publication':'withdrawn; not-published'}
        rows = []
        for row in self.rows.values():
            item = {k:row.get(k) for k in ['key','index','name','status','reason','animated','frames',
                'original_frames','duration_ms','source_indices','loop','source_rank','source_heat',
                'hotness_method','origin','source_url','image_url','source_revision','canvas',
                'image_slots','text_slots','defaults','warnings','spec_sha256','outputs']}
            item['keywords'] = row.get('metadata',{}).get('keywords',[])
            item['caption_inventory'] = row.get('caption_inventory',[])
            for name in ['source_shares','source_author','source_tags','limitations','recommended_method','blocked_methods']:
                item[name]=row.get(name)
            item['methods']={key:{'label':value['label'],'spec_sha256':value['spec_sha256']}
                             for key,value in row.get('variants',{}).items()}
            record = self.records.get(row['key'],{})
            current = record.get('spec_sha256') == row.get('spec_sha256')
            if record and row.get('variants'):
                chosen=row['variants'].get(record.get('method'),{})
                current=current and chosen.get('spec_sha256')==record.get('selected_spec_sha256')
            item['review'] = record if current else {}
            if record and not current:item['previous_review']=record
            rows.append(item)
        rows.sort(key=lambda r:(not r.get('animated'),r.get('source_rank') or 100000,r.get('index') or 0))
        return {'baseline':959,'target':1500,'needed':541,'rows':rows,
                'draft_count':sum(x['status']=='draft' for x in rows),
                'animated_drafts':sum(x['status']=='draft' and bool(x['animated']) for x in rows),
                'records':self.records,'selection':self.selection.get('counts',{}),
                'publication':'none; human approval required'}

    def save(self, body):
        if (self.directory/'withdrawal.json').exists():
            raise ValueError('本批候选已按用户要求撤销，历史评价保留，不再接收入库标记')
        self.refresh()
        key = body.get('key')
        row = self.rows.get(key)
        if not row or row['status']!='draft' or body.get('spec_sha256') != row.get('spec_sha256'):
            raise ValueError('候选已变化或没有可审核成品，请刷新页面')
        if self.selection and self.selection.get('recipes',{}).get(key)!=row.get('spec_sha256'):
            raise ValueError('候选配方与本轮技术检查不一致，请重新检查')
        decision = body.get('decision','')
        if decision not in {'','approved','adjust','reject'}:
            raise ValueError('invalid decision')
        method=body.get('method','')
        variants=row.get('variants',{})
        portrait=body.get('portrait')
        if variants and (method not in variants or variants[method]['spec_sha256']!=body.get('selected_spec_sha256')):
            raise ValueError('请选择并确认当前版本的换脸方案')
        if variants and portrait not in {None,'S03','S17','S29'}:
            raise ValueError('请记录当前查看的测试头像')
        if decision=='approved' and method in row.get('blocked_methods',{}):
            raise ValueError('已诊断失败的方案不能标为可用')
        note = str(body.get('note',''))[:1000]
        name = str(body.get('name','')).strip()[:40]
        terms = body.get('keywords',[])
        if not isinstance(terms,list) or any(not isinstance(x,str) for x in terms):
            raise ValueError('invalid keywords')
        record = {'key':key,'spec_sha256':row['spec_sha256'],'original_sha256':row['original_sha256'],
                  'decision':decision,'note':note,'name':name,
                  'keywords':list(dict.fromkeys(x.strip()[:80] for x in terms if x.strip()))[:128],
                  'samples':[x['sample'] for x in row['outputs']],
                  'updated_at':datetime.now(timezone.utc).isoformat()}
        if variants:
            record.update(method=method,selected_spec_sha256=variants[method]['spec_sha256'],reviewed_sample=portrait or 'unspecified')
        with self.lock:
            self.records[key] = record
            payload = {'version':1,'publication':'not-published','baseline':959,'target':1500,
                       'records':self.records}
            temporary = self.file.with_suffix('.tmp')
            temporary.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
            with temporary.open('rb') as stream:
                __import__('os').fsync(stream.fileno())
            temporary.replace(self.file)
            with (self.directory/'reviews.jsonl').open('a') as stream:
                stream.write(json.dumps(record,ensure_ascii=False)+'\n')
                stream.flush()
                __import__('os').fsync(stream.fileno())
        return record


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--directory',type=Path,required=True)
    parser.add_argument('--port',type=int,default=0)
    args=parser.parse_args()
    review=Review(args.directory)

    class Handler(BaseHTTPRequestHandler):
        def parse_request(self):
            if not super().parse_request():
                return False
            if self.headers.get('Host') not in {
                    f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}:
                self.send_error(403, 'loopback host required')
                return False
            return True

        def log_message(self,*args):
            pass

        def reply(self, raw, kind='application/json; charset=utf-8', status=200):
            if isinstance(raw,dict):
                raw=json.dumps(raw,ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type',kind)
            self.send_header('Content-Length',str(len(raw)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            path=unquote(urlsplit(self.path).path)
            if path in {'/','/index.html'}:
                filename='tenor_face_review.html' if (review.directory/'briefs.json').exists() else 'expansion_review.html'
                return self.reply((HERE/filename).read_bytes(),'text/html; charset=utf-8')
            if path=='/api/data':
                return self.reply(review.data())
            if path=='/api/export':
                withdrawn=(review.directory/'withdrawal.json').exists()
                return self.reply({'version':1,'records':review.records,
                    'publication':'withdrawn' if withdrawn else 'not-published'})
            review.refresh()
            if path.startswith('/source/'):
                key=path.removeprefix('/source/')
                row=review.rows.get(key)
                file=Path(row['path']) if row else None
            elif path.startswith('/media/'):
                name=path.removeprefix('/media/')
                valid=re.fullmatch(r'auto_element_[a-f0-9]{24}-(?:S03|S17|S29|blank|edited)\.(?:gif|png)',name) or re.fullmatch(r'tenor_face_[a-f0-9]{24}-S(?:03|17|29)-(?:direct|geometry|gan)\.gif',name)
                file=review.directory/'media'/name if valid else None
            elif path.startswith('/tracking/'):
                row=review.rows.get(path.removeprefix('/tracking/'))
                if not row or not row.get('variants'):
                    return self.reply({'error':'not found'},status=404)
                sheet=Image.new('RGB',(1200,430),'white');draw=ImageDraw.Draw(sheet)
                with Image.open(row['path']) as source:
                    for col,index in enumerate([0,row['frames']//2,row['frames']-1]):
                        source.seek(index);frame=source.convert('RGBA')
                        face=next(l for l in row['spec']['frames'][index]['layers'] if l['type']=='face')
                        digest=face['expression']['mask_asset']
                        with Image.open(review.directory/'state/features/template_assets'/(digest+'.png')) as mask:
                            tint=Image.new('RGBA',frame.size,'#e66159');tint.putalpha(mask.convert('L').point(lambda x:round(x*.28)))
                        frame=Image.alpha_composite(frame,tint)
                        thumb=ImageOps.contain(frame.convert('RGB'),(390,390));sheet.paste(thumb,(col*400,25))
                        draw.text((col*400+4,5),f'{index+1} / {row["frames"]}',fill='black')
                output=BytesIO();sheet.save(output,'JPEG',quality=90)
                return self.reply(output.getvalue(),'image/jpeg')
            elif path.startswith('/frames/'):
                parts=path.split('/')
                if len(parts)!=4 or parts[2] not in review.rows:
                    return self.reply({'error':'not found'},status=404)
                row=review.rows[parts[2]]
                sample=parts[3]
                if sample=='source':
                    source=Path(row['path'])
                else:
                    entry=next((x for x in row.get('outputs',[]) if x['sample']==sample),None)
                    if not entry:
                        return self.reply({'error':'sample not found'},status=404)
                    source=review.directory/'media'/entry['file']
                sheet=Image.new('RGB',(900,330),'white')
                draw=ImageDraw.Draw(sheet)
                with Image.open(source) as image:
                    count=getattr(image,'n_frames',1)
                    for col,index in enumerate([0,count//2,count-1]):
                        image.seek(index)
                        frame=ImageOps.contain(image.convert('RGB'),(294,295))
                        sheet.paste(frame,(col*300+(294-frame.width)//2,25+(295-frame.height)//2))
                        draw.text((col*300+8,5),f'{index+1} / {count}',fill='black')
                output=BytesIO();sheet.save(output,'JPEG',quality=85)
                return self.reply(output.getvalue(),'image/jpeg')
            else:
                file=None
            if file and file.is_file() and file.resolve().is_relative_to(review.directory):
                return self.reply(file.read_bytes(),mimetypes.guess_type(file)[0] or 'application/octet-stream')
            self.reply({'error':'not found'},status=404)

        def do_POST(self):
            origin=self.headers.get('Origin')
            if origin and origin not in {f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}'}:
                return self.reply({'error':'origin rejected'},status=403)
            if self.path!='/api/reviews' or int(self.headers.get('Content-Length','0'))>20000:
                return self.reply({'error':'invalid request'},status=400)
            try:
                body=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))))
                self.reply({'record':review.save(body)})
            except (ValueError,TypeError,KeyError) as error:
                self.reply({'error':str(error)},status=409)

    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    url=f'http://127.0.0.1:{server.server_port}/index.html'
    (review.directory/'review-url.txt').write_text(url+'\n')
    print(url,flush=True)
    server.serve_forever()


if __name__=='__main__':main()
