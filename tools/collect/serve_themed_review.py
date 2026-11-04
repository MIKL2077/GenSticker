"""Local-only, hash-bound template review; never publishes a template."""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import threading
import time


def serve(directory, port):
    lock = threading.Lock()
    class Handler(SimpleHTTPRequestHandler):
        def reply(self, status, value):
            raw = json.dumps(value, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            if self.path == '/api/reviews':
                path = directory / 'reviews.json'
                return self.reply(200, json.loads(path.read_text()) if path.exists() else {})
            if self.path.split('?')[0] not in ['/', '/index.html', '/drafts.json', '/review-findings.json'] and not re.fullmatch(r'/media/[NCZ]\d{2}/(source|changed|blank|multiline)\.(gif|png)', self.path):
                return self.reply(404, {'error': 'not found'})
            return super().do_GET()

        def do_POST(self):
            if self.path != '/api/reviews':
                return self.reply(404, {'error': 'not found'})
            if self.headers.get('Origin') not in (None, f'http://127.0.0.1:{self.server.server_port}'):
                return self.reply(403, {'error': 'same-origin requests only'})
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 8192:
                    raise ValueError('invalid request size')
                value = json.loads(self.rfile.read(size))
                rows = {r['key']: r for r in json.loads((directory/'drafts.json').read_text()) if r.get('status') == 'draft-pending-review'}
                row = rows[value['key']]
                if value['spec_sha256'] != row['spec_sha256']:
                    raise ValueError('recipe changed; reload before reviewing')
                if value['rating'] not in ['', '通过', '需调整', '不要'] or not isinstance(value.get('note', ''), str) or len(value.get('note', '')) > 2000:
                    raise ValueError('invalid review')
                finding = json.loads((directory/'review-findings.json').read_text()).get(row['id'], {})
                if value['rating'] == '通过' and finding.get('blocked'):
                    raise ValueError('this draft needs repair before approval')
                value = {k: value[k] for k in ['key', 'spec_sha256', 'rating', 'note']}
                value['updated_at'] = time.time()
                with lock:
                    path = directory/'reviews.json'
                    reviews = json.loads(path.read_text()) if path.exists() else {}
                    reviews[row['key']] = value
                    temp = path.with_suffix('.tmp')
                    temp.write_text(json.dumps(reviews, ensure_ascii=False, indent=2))
                    temp.replace(path)
                    with (directory/'review-history.jsonl').open('a') as history:
                        history.write(json.dumps(value, ensure_ascii=False)+'\n')
                return self.reply(200, value)
            except (ValueError, KeyError, TypeError) as error:
                return self.reply(400, {'error': str(error)})
    server = ThreadingHTTPServer(('127.0.0.1', port), partial(Handler, directory=str(directory)))
    url = f'http://127.0.0.1:{server.server_port}/index.html'
    (directory/'review-url.txt').write_text(url+'\n')
    print(url, flush=True)
    server.serve_forever()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--port', type=int, default=0)
    args = parser.parse_args()
    directory = args.directory.resolve()
    (directory/'index.html').write_text(Path(__file__).with_name('themed_review.html').read_text())
    serve(directory, args.port)
