"""Exercise the actual public API without credentials or personal photos."""
import argparse
import base64
import hashlib
import json
import time
from datetime import datetime
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
from PIL import Image, ImageDraw


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', default='https://www.shangkun.uk/gensticker/api')
    parser.add_argument('--proxy')
    parser.add_argument('--output-dir', type=Path, default=Path('deploy/live-backend-verification'))
    parser.add_argument('--require-reroll', action='store_true')
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report = {'checked_at': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(), 'base_url': args.base_url, 'checks': [], 'limitations': []}
    with httpx.Client(proxy=args.proxy, timeout=httpx.Timeout(65, connect=25), follow_redirects=False) as client:
        def request(method, path, **kwargs):
            start = time.monotonic()
            for attempt in range(2):
                try:
                    response = client.request(method, args.base_url.rstrip('/') + path, **kwargs)
                    break
                except httpx.TransportError:
                    if attempt: raise
            response.raise_for_status()
            report['checks'].append({'method': method, 'path': path, 'status': response.status_code, 'seconds': round(time.monotonic()-start, 3)})
            return response

        def image(response, filename):
            with Image.open(BytesIO(response.content)) as decoded:
                size, format_name = decoded.size, decoded.format
                decoded.verify()
            (args.output_dir / filename).write_bytes(response.content)
            report['checks'][-1].update({'image_format': format_name, 'image_size': size, 'bytes': len(response.content), 'sha256': hashlib.sha256(response.content).hexdigest()})

        try:
            health = request('GET', '/healthz').json()
            if health.get('status') != 'ok': raise ValueError('unhealthy API')
            catalog = request('GET', '/memes/categories').json()
            report['template_count'] = len(catalog['all'])
            config = request('GET', '/account/config').json()
            # AppID is public. Never request or write AppSecret, sessions or login codes.
            report['login_enabled'] = config.get('login_enabled', False)
            report['backend_public_appid'] = config.get('app_id')
            if not config.get('app_id'):
                report['limitations'].append('Backend does not publish its AppID; account identity is not verified.')
            schema = request('GET', '/openapi.json').json()
            fields = schema.get('components', {}).get('schemas', {}).get('CreateJob', {}).get('properties', {})
            report['reroll_supported'] = 'previous_job_id' in fields
            if not report['reroll_supported']:
                report['limitations'].append('Deployed backend still uses the old job protocol and requires deployment before reroll works.')
            image(request('GET', '/memes/emperor_dragon/thumbnail'), 'thumbnail.png')
            image(request('POST', '/memes/emperor_dragon/generate', json={'images': [], 'texts': ['今天也要开心'], 'args': {}}), 'text-generation.png')
            fixture = Image.new('RGB', (192, 192), '#ece6de')
            draw = ImageDraw.Draw(fixture)
            draw.ellipse((30, 22, 162, 170), fill='#f5c76c')
            draw.ellipse((65, 70, 76, 85), fill='#273f49')
            draw.ellipse((116, 70, 127, 85), fill='#273f49')
            draw.arc((63, 85, 130, 132), 5, 175, fill='#273f49', width=6)
            data = BytesIO(); fixture.save(data, 'PNG')
            encoded = base64.b64encode(data.getvalue()).decode()
            image(request('POST', '/memes/always/generate', json={'images': [encoded], 'texts': [], 'args': {}}), 'photo-generation.jpg')
            image(request('POST', '/images/subject', json={'image': encoded}), 'subject-preview.png')
            report['status'] = 'partial' if report['limitations'] else 'passed'
        except Exception as error:
            # Do not include request bodies or credential-bearing URLs in reports.
            report['status'] = 'failed'
            report['error'] = type(error).__name__
        finally:
            (args.output_dir / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'status': report['status'], 'template_count': report.get('template_count'), 'reroll_supported': report.get('reroll_supported'), 'checks': len(report['checks']), 'report': str(args.output_dir/'report.json')}, ensure_ascii=False))
    return 1 if report['status'] == 'failed' else 2 if args.require_reroll and not report.get('reroll_supported') else 0


if __name__ == '__main__':
    raise SystemExit(main())
