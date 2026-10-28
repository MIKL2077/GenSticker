#!/usr/bin/env python3
"""Local-only evaluation gallery with versioned, durable annotation storage."""
import argparse
import json
import os
import tempfile
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit


def save_json(path, data):
    path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w',dir=path.parent,delete=False,encoding='utf-8') as f:
        json.dump(data,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno());name=f.name
    os.replace(name,path)


def make_handler(directory, review_file):
    directory=directory.resolve();review_file=review_file.resolve();lock=threading.Lock()
    data=json.loads((directory/'data.json').read_text())
    allowed={(t['key'],t['version']) for t in data['templates']}
    samples=set(data['samples'])
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(directory),**kwargs)
        def log_message(self,*args):pass
        def list_directory(self,path):self.send_error(404)
        def end_headers(self):
            self.send_header('Cache-Control','private, no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            super().end_headers()
        def valid_host(self):return self.headers.get('Host')==f'127.0.0.1:{self.server.server_port}'
        def respond(self,status,data):
            raw=json.dumps(data,ensure_ascii=False).encode();self.send_response(status)
            self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(raw)))
            self.end_headers();self.wfile.write(raw)
        def do_GET(self):
            if not self.valid_host():return self.send_error(403)
            path=unquote(urlsplit(self.path).path)
            if path=='/api/reviews':
                with lock:record=json.loads(review_file.read_text())
                return self.respond(200,record)
            if '..' in Path(path).parts or not (path in {'/','/index.html','/data.json'} or path.startswith(('/sources/','/thumbs/','/media/','/contacts/','/regions/'))):
                return self.send_error(404)
            super().do_GET()
        def do_POST(self):
            origin=f'http://127.0.0.1:{self.server.server_port}'
            if (not self.valid_host() or self.path!='/api/reviews' or self.headers.get('Origin')!=origin
                    or self.headers.get_content_type()!='application/json'):
                return self.send_error(403)
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=8192:raise ValueError('size')
                record=json.loads(self.rfile.read(length))
                if set(record)-{'key','version','sample','rating','note'}:raise ValueError('fields')
                if (record['key'],record['version']) not in allowed or record['sample'] not in samples:raise ValueError('template version')
                if record['rating'] not in {'','可用','需调整','不可用','不需要'}:raise ValueError('rating')
                if not isinstance(record.get('note',''),str) or len(record.get('note',''))>500:raise ValueError('note')
                record={**record,'updated_at':time.time(),'origin':'user'}
                key=f"{record['key']}@{record['version']}:{record['sample']}"
                with lock:
                    saved=json.loads(review_file.read_text());saved['records'][key]=record
                    saved['updated_at']=record['updated_at'];save_json(review_file,saved)
                    with review_file.with_suffix('.jsonl').open('a',encoding='utf-8') as log:
                        log.write(json.dumps(record,ensure_ascii=False)+'\n');log.flush();os.fsync(log.fileno())
                return self.respond(200,{'saved':True,'record':record})
            except (ValueError,TypeError,KeyError,json.JSONDecodeError):return self.respond(400,{'saved':False,'error':'invalid review'})
    return Handler


def main():
    p=argparse.ArgumentParser();p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--review-file',type=Path,required=True);p.add_argument('--port',type=int,default=0);a=p.parse_args()
    server=ThreadingHTTPServer(('127.0.0.1',a.port),make_handler(a.directory,a.review_file))
    print(f'GALLERY_URL=http://127.0.0.1:{server.server_port}/index.html',flush=True);server.serve_forever()


if __name__=='__main__':main()
