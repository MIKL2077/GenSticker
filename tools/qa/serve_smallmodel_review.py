#!/usr/bin/env python3
"""Loopback-only comparison gallery with per-version, durable scheme choices."""
import argparse
import json
import os
import tempfile
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit


def write_json(path, value):
    with tempfile.NamedTemporaryFile('w', dir=path.parent, encoding='utf-8', delete=False) as out:
        json.dump(value, out, ensure_ascii=False, indent=2)
        out.flush()
        os.fsync(out.fileno())
        name = out.name
    os.replace(name, path)


def handler(directory, review_file):
    data = json.loads((directory / 'data.json').read_text())
    allowed = {(t['key'], t['version']): t['id'] for t in data['templates']}
    methods = {m['key'] for m in data['methods']} | {'reject', ''}
    lock = threading.Lock()

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(directory), **kwargs)

        def log_message(self, *args):
            pass

        def list_directory(self, path):
            self.send_error(404)

        def end_headers(self):
            self.send_header('Cache-Control', 'private, no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'")
            super().end_headers()

        def valid_host(self):
            return self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}'

        def respond(self, status, value):
            raw = json.dumps(value, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            if not self.valid_host():
                return self.send_error(403)
            path = unquote(urlsplit(self.path).path)
            if path == '/api/reviews':
                with lock:
                    return self.respond(200, json.loads(review_file.read_text()))
            if '..' in Path(path).parts or not (path in {'/', '/index.html', '/data.json'} or path.startswith(('/media/', '/sources/', '/contacts/'))):
                return self.send_error(404)
            super().do_GET()

        def do_POST(self):
            origin = f'http://127.0.0.1:{self.server.server_port}'
            if (not self.valid_host() or self.path != '/api/reviews' or self.headers.get('Origin') != origin
                    or self.headers.get_content_type() != 'application/json'):
                return self.send_error(403)
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 8192:
                    raise ValueError('length')
                value = json.loads(self.rfile.read(length))
                if set(value) != {'key', 'version', 'sample', 'choice', 'note'}:
                    raise ValueError('fields')
                tid = allowed[(value['key'], value['version'])]
                if value['sample'] not in data['samples'] or value['choice'] not in methods:
                    raise ValueError('choice')
                if value['choice'] not in {'', 'reject'} and value['choice'] not in data['cases'][tid + ':' + value['sample']]:
                    raise ValueError('unavailable candidate')
                if value['choice'] not in {'', 'reject'} and data['cases'][tid + ':' + value['sample']][value['choice']].get('folded_triangles', 0):
                    raise ValueError('candidate failed structural gate')
                if not isinstance(value['note'], str) or len(value['note']) > 1000:
                    raise ValueError('note')
                value['updated_at'] = time.time()
                value['origin'] = 'user'
                key = f"{value['key']}@{value['version']}:{value['sample']}"
                with lock:
                    saved = json.loads(review_file.read_text())
                    saved['records'][key] = value
                    write_json(review_file, saved)
                    with review_file.with_suffix('.jsonl').open('a') as log:
                        log.write(json.dumps(value, ensure_ascii=False) + '\n')
                        log.flush()
                        os.fsync(log.fileno())
                return self.respond(200, {'saved': True, 'record': value})
            except (ValueError, TypeError, KeyError):
                return self.respond(400, {'saved': False})

    return Handler


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--review-file', type=Path, required=True)
    parser.add_argument('--port', type=int, default=0)
    args = parser.parse_args()
    if not args.review_file.exists():
        write_json(args.review_file, {'schema': 'smallmodel-choice-v1', 'records': {}})
    server = ThreadingHTTPServer(('127.0.0.1', args.port), handler(args.directory.resolve(), args.review_file.resolve()))
    print(f'GALLERY_URL=http://127.0.0.1:{server.server_port}/index.html', flush=True)
    server.serve_forever()
