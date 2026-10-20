"""Bounded on-host acceptance probe. Never publishes or alters real users.
Run as the GenSticker account with the production state/config environment.
Explicit --allow-fixtures is required. Outputs no tokens or private image bytes.
"""
import argparse, base64, hashlib, json, os, re, secrets, shutil, statistics, subprocess, tempfile, threading, time, uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
import httpx
from PIL import Image, ImageDraw, ImageSequence
from meme_generator import account
from meme_generator.features import studio, livegif
from meme_generator.features.store import connect, root
parser = argparse.ArgumentParser()
parser.add_argument('--allow-fixtures', action='store_true')
parser.add_argument('--output', required=True)
parser.add_argument('--face-fixture')
args = parser.parse_args()
if not args.allow_fixtures:
    raise SystemExit('Use --allow-fixtures only on an authorized host')
report = {'time_utc': datetime.now(timezone.utc).isoformat(), 'status': 'running', 'checks': [], 'measurements': [], 'request_metrics': [], 'limits': {'read_concurrency': 2, 'ai_batches': 2, 'video_cases': 2, 'publishes': 0}}
users = []
tokens = []
sample_stop = threading.Event()
samples = []
asset_hashes = set()
started = time.perf_counter()

def mem_available():
    return int(next((line.split()[1] for line in Path('/proc/meminfo').read_text().splitlines() if line.startswith('MemAvailable:')))) * 1024

def guard():
    if mem_available() < 3 * 1024 ** 3 or os.getloadavg()[0] > 3.5 or shutil.disk_usage(root()).free < 10 * 1024 ** 3:
        raise RuntimeError('resource guard: no more jobs submitted')

def sample():
    while not sample_stop.wait(0.5):
        row = {'elapsed_s': round(time.perf_counter() - started, 2), 'available_memory': mem_available(), 'load1': os.getloadavg()[0]}
        for name in ('gensticker', 'gensticker-worker'):
            p = Path('/sys/fs/cgroup/system.slice') / (name + '.service')
            try:
                row[name + '_memory'] = int((p / 'memory.current').read_text())
                row[name + '_cpu_usec'] = int(dict((line.split() for line in (p / 'cpu.stat').read_text().splitlines()))['usage_usec'])
            except OSError:
                pass
        samples.append(row)

def mark(name, **values):
    report['checks'].append({'name': name, 'status': 'passed', **values})
    print(json.dumps(report['checks'][-1]), flush=True)

def measure(name, seconds, **values):
    report['measurements'].append({'name': name, 'seconds': round(seconds, 4), **values})

def create_user():
    user = 'delivery_qa_' + uuid.uuid4().hex
    token = secrets.token_urlsafe(32)
    db = account.connection()
    with db:
        db.execute('INSERT INTO users(id,openid,name) VALUES(?,?,?)', (user, user, 'QA synthetic'))
        db.execute('INSERT INTO sessions VALUES(?,?,?)', (hashlib.sha256(token.encode()).hexdigest(), user, int(time.time()) + 1800))
    db.close()
    users.append(user)
    tokens.append(token)
    return token

def req(client, method, path, expected=200, **kw):
    t = time.perf_counter()
    r = client.request(method, path, **kw)
    elapsed = time.perf_counter() - t
    report['request_metrics'].append({'method': method, 'route': re.sub('user_[a-f0-9]{24}|[a-f0-9]{32,64}', ':id', path.split('?')[0]), 'seconds': round(elapsed, 4), 'status': r.status_code, 'response_bytes': len(r.content)})
    if r.status_code != expected:
        raise AssertionError(f"{method} {path.split('?')[0]}: expected {expected}, got {r.status_code}: {r.text[:160]}")
    return (r, time.perf_counter() - t)

def wait_job(client, path):
    t = time.perf_counter()
    while time.perf_counter() - t < 120:
        r = client.get(path)
        r.raise_for_status()
        job = r.json()
        if job['status'] not in ('queued', 'running'):
            if job['status'] != 'completed':
                raise AssertionError('Fixture worker result: ' + job['status'])
            return (job, time.perf_counter() - t)
        time.sleep(0.3)
    raise TimeoutError('fixture worker did not finish')

def image_metrics(raw):
    with Image.open(BytesIO(raw)) as im:
        return {'format': im.format, 'bytes': len(raw), 'width': im.width, 'height': im.height, 'frames': getattr(im, 'n_frames', 1), 'duration_ms': sum((f.info.get('duration', 0) for f in ImageSequence.Iterator(im)))}

def cleanup():
    db = connect()
    active = any((db.execute("SELECT 1 FROM jobs WHERE user_id=? AND status IN ('queued','running')", (u,)).fetchone() or db.execute("SELECT 1 FROM studio_jobs WHERE user_id=? AND status IN ('queued','running')", (u,)).fetchone() for u in users))
    if active:
        db.close()
        return False
    for user in users:
        jobs = [r['id'] for r in db.execute('SELECT id FROM jobs WHERE user_id=?', (user,))]
        paths = [Path(r[k]) for j in jobs for r in db.execute('SELECT path,preview FROM results WHERE job_id=?', (j,)) for k in ('path', 'preview')]
        studio_jobs = [r['id'] for r in db.execute('SELECT id FROM studio_jobs WHERE user_id=?', (user,))]
        assets = [r['id'] for r in db.execute('SELECT id FROM assets WHERE user_id=?', (user,))]
        with db:
            for table in ('results', 'job_variations', 'quotas', 'cost_ledger', 'feedback_history'):
                for j in jobs:
                    db.execute('DELETE FROM ' + table + ' WHERE job_id=?', (j,))
            for table in ('jobs', 'assets', 'events', 'preferences', 'generation_admissions', 'studio_jobs', 'studio_views', 'studio_templates', 'studio_ai_daily'):
                if db.execute('SELECT 1 FROM sqlite_master WHERE name=?', (table,)).fetchone():
                    db.execute('DELETE FROM ' + table + ' WHERE user_id=?', (user,))
        for p in paths:
            p.unlink(missing_ok=True)
        for j in studio_jobs:
            (root() / 'studio_results' / j).unlink(missing_ok=True)
            (root() / 'studio_replays' / (j + '.json')).unlink(missing_ok=True)
        for a in assets:
            (root() / 'history_thumbs' / (a + '.jpg')).unlink(missing_ok=True)
        shutil.rmtree(root() / 'private' / user, ignore_errors=True)
        for p in livegif.directory().glob('*.json'):
            if json.loads(p.read_text()).get('user_id') == user:
                for suffix in ('.json', '.jpg', '.media'):
                    p.with_suffix(suffix).unlink(missing_ok=True)
        adb = account.connection()
        with adb:
            for table in ('favorites', 'history', 'sessions'):
                adb.execute('DELETE FROM ' + table + ' WHERE user_id=?', (user,))
            adb.execute('DELETE FROM users WHERE id=?', (user,))
        adb.close()
    references = [r['spec'] for r in db.execute('SELECT spec FROM templates WHERE spec IS NOT NULL')] + [r['spec'] for r in db.execute('SELECT spec FROM studio_templates')]
    db.close()
    for digest in asset_hashes:
        if not any((digest in spec for spec in references)):
            (root() / 'template_assets' / (digest + '.png')).unlink(missing_ok=True)
    return True
thread = threading.Thread(target=sample, daemon=True)
thread.start()
try:
    guard()
    db = studio.init()
    active = db.execute("SELECT (SELECT count(*) FROM jobs WHERE status IN ('queued','running'))+(SELECT count(*) FROM studio_jobs WHERE status IN ('queued','running'))").fetchone()[0]
    db.close()
    if active:
        raise RuntimeError('existing user jobs active: defer production probe')
    token = create_user()
    other = create_user()
    with httpx.Client(base_url='http://127.0.0.1:3001', headers={'Authorization': 'Bearer ' + token}, timeout=40) as client, httpx.Client(base_url='http://127.0.0.1:3001', headers={'Authorization': 'Bearer ' + other}, timeout=20) as stranger, httpx.Client(base_url='http://127.0.0.1:3001', timeout=20) as guest:
        for path in ('/healthz', '/memes/categories', '/templates/popularity'):
            for i in range(5):
                r, d = req(guest, 'GET', path)
                measure('read:' + path, d, bytes=len(r.content))

        def health(_):
            r, d = req(guest, 'GET', '/healthz')
            return d
        with ThreadPoolExecutor(max_workers=2) as pool:
            values = list(pool.map(health, range(10)))
        for value in values:
            measure('health-concurrency-2', value)
        for path in ('/account/library', '/recommend/jobs', '/studio/jobs'):
            req(guest, 'GET', path, 401)
        req(client, 'GET', '/auth/me')
        req(client, 'GET', '/recommend/quota')
        req(client, 'GET', '/studio/quota')
        req(client, 'PUT', '/account/profile', json={'name': 'QA fixture'})
        req(client, 'PUT', '/account/favorites/petpet')
        req(client, 'PUT', '/account/history/petpet')
        library = req(client, 'GET', '/account/library')[0].json()
        assert 'petpet' in library['favorite_keys']
        assert not req(stranger, 'GET', '/account/library')[0].json()['favorite_keys']
        req(client, 'POST', '/account/library/merge', json={'favorite_keys': ['always'], 'history': [{'key': 'always', 'visited_at': int(time.time() * 1000)}]})
        req(client, 'DELETE', '/account/favorites/petpet', 204)
        req(client, 'DELETE', '/account/history', 204)
        mark('authentication-library-account-isolation')
        photo = Image.new('RGB', (360, 480), '#eee3ce')
        draw = ImageDraw.Draw(photo)
        draw.ellipse((50, 30, 310, 440), fill='#cb895a')
        draw.ellipse((100, 170, 130, 200), fill='black')
        draw.ellipse((230, 170, 260, 200), fill='black')
        draw.arc((100, 220, 260, 350), 0, 180, fill='black', width=6)
        buf = BytesIO()
        photo.save(buf, 'PNG')
        raw = buf.getvalue()
        encoded = base64.b64encode(raw).decode()
        for key in ('always', 'petpet'):
            for i in range(3):
                response, d = req(client, 'POST', '/memes/' + key + '/generate', json={'images': [encoded], 'texts': [], 'args': {}})
                metrics = image_metrics(response.content)
                assert metrics['bytes'] > 100
                if key == 'petpet':
                    assert metrics['frames'] > 1
                measure('manual:' + key, d, cache=response.headers.get('x-gensticker-cache', 'miss'), **metrics)
        mark('manual-static-and-animated-output')
        preview, d = req(client, 'POST', '/images/subject', json={'image': encoded, 'delivery': 'binary'})
        metrics = image_metrics(preview.content)
        assert metrics['format'] == 'PNG'
        measure('background-removal-preview', d, **metrics)
        detect_raw = Path(args.face_fixture).read_bytes() if args.face_fixture else raw
        detected, d = req(client, 'POST', '/recommend/subjects/detect', files={'file': ('fixture.jpg', detect_raw, 'image/jpeg')})
        detected = detected.json()
        measure('subject-detection', d, candidates=len(detected['candidates']))
        if args.face_fixture:
            assert len(detected['candidates']) >= 2
            x, y, w, h = detected['candidates'][1]['box']
            im = Image.open(BytesIO(detect_raw))
            im = im.crop((int(x * im.width), int(y * im.height), int((x + w) * im.width), int((y + h) * im.height)))
            buf = BytesIO()
            im.save(buf, 'PNG')
            raw = buf.getvalue()
        asset = req(client, 'POST', '/recommend/assets', 201, files={'file': ('selected.png', raw, 'image/png')}, data={'subject_selected': 'true'})[0].json()['asset_id']
        previous = None
        sets = []
        for batch in range(2):
            guard()
            payload = {'idempotency_key': uuid.uuid4().hex, **({'previous_job_id': previous} if previous else {'asset_id': asset})}
            t = time.perf_counter()
            j = req(client, 'POST', '/recommend/jobs', 202, json=payload)[0].json()
            assert req(client, 'POST', '/recommend/jobs', 202, json=payload)[0].json()['job_id'] == j['job_id']
            result, _ = wait_job(client, '/recommend/jobs/' + j['job_id'])
            keys = {r['key'] for r in result['results']}
            assert len(keys) == 9
            if sets:
                assert not keys & sets[-1]
            sets.append(keys)
            previous = j['job_id']
            bytes_total = 0
            animated = 0
            for item in result['results']:
                response = req(client, 'GET', item['image_url'])[0]
                metrics = image_metrics(response.content)
                bytes_total += len(response.content)
                animated += metrics['frames'] > 1
                req(stranger, 'GET', item['image_url'], 404)
            measure('ai-batch', time.perf_counter() - t, batch=batch + 1, results=9, output_bytes=bytes_total, animated=animated, subject_selected=result['analysis'].get('subject_selected'), framing=result['analysis'].get('framing'))
        req(client, 'POST', '/recommend/jobs/' + previous + '/selections', json={'event_id': uuid.uuid4().hex, 'slots': [0], 'action': 'choose'})
        req(client, 'PUT', '/recommend/preferences', json={'enabled': False})
        assert req(client, 'GET', '/recommend/quota')[0].json()['personalization'] is False
        mark('actual-model-nine-results-reroll-animation-ownership', batches=2, adjacent_overlap=0, candidates=len(detected['candidates']))
        spec = {'width': 512, 'height': 512, 'layers': [{'type': 'asset', 'box': [0, 0, 512, 512], 'value': '0' * 64}, {'type': 'subject', 'box': [0, 0, 512, 400]}, {'type': 'text', 'box': [10, 420, 492, 70], 'font_size': 32, 'slot': 0, 'value': 'QA'}], 'defaults': ['QA']}
        background = Image.new('RGB', (512, 512), '#fbeedc')
        background.putpixel((0, 0), (secrets.randbelow(255), secrets.randbelow(255), secrets.randbelow(255)))
        buf = BytesIO()
        background.save(buf, 'PNG')
        item = req(client, 'POST', '/studio/templates', 201, json={'name': 'QA private', 'spec': spec, 'background_image': base64.b64encode(buf.getvalue()).decode()})[0].json()
        digest = item['spec']['layers'][0]['value']
        asset_hashes.add(digest)
        req(stranger, 'GET', '/studio/templates/' + item['id'], 404)
        req(guest, 'GET', '/template-assets/' + digest + '.png', 404)
        job = req(client, 'POST', '/studio/jobs', 201, json={'template_key': item['id'], 'images': [encoded], 'texts': ['QA'], 'args': {}, 'idempotency_key': uuid.uuid4().hex})[0].json()
        j, d = wait_job(client, '/studio/jobs/' + job['id'])
        image_metrics(req(client, 'GET', j['result_url'])[0].content)
        measure('private-template-queue', d)
        req(client, 'POST', '/studio/jobs/' + j['id'] + '/view', 204)
        req(client, 'GET', '/studio/unread')
        redo = req(client, 'POST', '/studio/jobs/' + j['id'] + '/regenerate', 201, json={'idempotency_key': uuid.uuid4().hex})[0].json()
        redone, d = wait_job(client, '/studio/jobs/' + redo['id'])
        measure('queue-regeneration', d)
        req(client, 'DELETE', '/studio/jobs/' + redo['id'], 204)
        req(client, 'GET', '/studio/jobs/' + redo['id'], 404)
        mark('private-template-background-is-private-queue-completes')
        with tempfile.TemporaryDirectory(prefix='gensticker-qa-video-') as temp:
            folder = Path(temp)
            for complex_scene in (False, True):
                guard()
                video = folder / ('complex.mp4' if complex_scene else 'simple.mp4')
                source = 'testsrc2=size=360x480:rate=10' if complex_scene else 'testsrc=size=360x480:rate=10'
                subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i', source, '-t', '9', '-c:v', 'libx264', '-threads', '1', '-pix_fmt', 'yuv420p', '-y', str(video)], check=True, timeout=30)
                r, d = req(client, 'POST', '/studio/live/assets', 201, files={'file': ('fixture.mp4', video.read_bytes(), 'video/mp4')})
                asset = r.json()
                measure('video-upload-prepare', d, source_bytes=video.stat().st_size)
                payload = {'asset_id': asset['asset_id'], 'idempotency_key': uuid.uuid4().hex, 'start': 0, 'duration': 9, 'crop': [0.1, 0.1, 0.8, 0.8], 'rotation': 90, 'flip': True, 'text': '测试字幕', 'caption_style': {'x': 0.5, 'y': 0.2, 'size': 0.12, 'color': '#1890ff', 'background': 'light', 'bold': True}}
                t = time.perf_counter()
                j = req(client, 'POST', '/studio/live/jobs', 201, json=payload)[0].json()
                result, _ = wait_job(client, '/studio/jobs/' + j['id'])
                rawgif = req(client, 'GET', result['result_url'])[0].content
                metrics = image_metrics(rawgif)
                assert metrics['bytes'] <= 512000 and max(metrics['width'], metrics['height']) <= 240 and (metrics['duration_ms'] >= 8800)
                if complex_scene:
                    assert metrics['frames'] > 1
                req(stranger, 'GET', result['result_url'], 404)
                measure('video-nine-seconds', time.perf_counter() - t, complex_scene=complex_scene, **metrics)
                if complex_scene:
                    idem = uuid.uuid4().hex
                    uploaded = req(client, 'POST', '/studio/live/results', 201, files={'file': ('local.gif', rawgif, 'image/gif')}, data={'idempotency_key': idem})[0].json()
                    assert req(client, 'POST', '/studio/live/results', 201, files={'file': ('local.gif', rawgif, 'image/gif')}, data={'idempotency_key': idem})[0].json()['id'] == uploaded['id']
                    wait_job(client, '/studio/jobs/' + uploaded['id'])
        mark('video-crop-rotation-caption-full-duration-size-local-sync-idempotency')
        req(client, 'POST', '/recommend/assets', 413, files={'file': ('huge.jpg', b'a' * (3 * 1024 * 1024 + 1), 'image/jpeg')})
        req(client, 'POST', '/studio/live/jobs', 422, json={'asset_id': '0' * 32, 'idempotency_key': uuid.uuid4().hex, 'duration': 10})
        req(client, 'POST', '/studio/templates/ai', 422, json={'image': encoded, 'idempotency_key': uuid.uuid4().hex, 'rights_attested': False})
        db = connect()
        with db:
            count = db.execute('SELECT count(*) FROM generation_admissions WHERE user_id=? AND created>?', (users[0], time.time() - 60)).fetchone()[0]
            for _ in range(max(0, 8 - count)):
                db.execute('INSERT INTO generation_admissions VALUES(?,?,?)', (uuid.uuid4().hex, users[0], time.time()))
        db.close()
        db = connect()
        aid = db.execute('SELECT id FROM assets WHERE user_id=? LIMIT 1', (users[0],)).fetchone()[0]
        db.close()
        limited = req(client, 'POST', '/recommend/jobs', 429, json={'asset_id': aid, 'idempotency_key': uuid.uuid4().hex})[0]
        assert int(limited.headers['retry-after']) > 0
        mark('input-bounds-private-access-rights-consent-rolling-rate-limit')
    report['status'] = 'passed'
except Exception as error:
    report['status'] = 'failed'
    report['error'] = str(error)
    raise
finally:
    sample_stop.set()
    thread.join(timeout=2)
    report['elapsed_s'] = round(time.perf_counter() - started, 3)
    report['resources'] = samples
    report['fixture_cleaned'] = cleanup() if users else True
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print('REPORT', args.output, report['status'], 'fixture_cleaned', report['fixture_cleaned'], flush=True)
