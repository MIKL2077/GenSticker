"""Offline per-template smoke and shape checks. Local host only; never a load test."""
import argparse, json, os, subprocess, sys, tempfile, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'backend/meme-generator'))
p = argparse.ArgumentParser()
p.add_argument('--key')
p.add_argument('--fill-optional', action='store_true')
p.add_argument('--output', default='docs/testing/evidence/2026-10-20/catalog-smoke.json')
args = p.parse_args()
if args.key:
    from io import BytesIO
    from PIL import Image, ImageDraw
    from meme_generator.manager import get_meme
    meme = get_meme(args.key)
    image = Image.new('RGB', (256, 256), '#eadfc8')
    draw = ImageDraw.Draw(image)
    draw.ellipse((40, 30, 215, 230), fill='#b67d58')
    draw.ellipse((80, 90, 100, 115), fill='black')
    draw.ellipse((160, 90, 180, 115), fill='black')
    buf = BytesIO()
    image.save(buf, 'PNG')
    params = meme.params_type
    texts = params.default_texts.copy()
    if not params.min_texts <= len(texts) <= params.max_texts:
        texts = ['测试' + str(i + 1) for i in range(params.min_texts)]
    if args.fill_optional and params.max_texts > 0:
        texts = ['测试' + str(i + 1) for i in range(min(params.max_texts, max(1, params.min_images, params.min_texts)))]
    t = time.perf_counter()
    raw = meme(images=[buf.getvalue()] * params.min_images, texts=texts, args={}).getvalue()
    with Image.open(BytesIO(raw)) as out:
        result = {'key': args.key, 'status': 'passed', 'render_seconds': round(time.perf_counter() - t, 4), 'format': out.format, 'width': out.width, 'height': out.height, 'frames': getattr(out, 'n_frames', 1), 'bytes': len(raw)}
    print('QA_RESULT ' + json.dumps(result))
    raise SystemExit()
with tempfile.TemporaryDirectory(prefix='gensticker-catalog-qa-') as temp:
    env = {**os.environ, 'GENSTICKER_STATE_DIR': temp, 'PYTHONPATH': str(ROOT / 'backend/meme-generator')}
    code = 'import json;from meme_generator.manager import get_meme_keys;print("QA_KEYS "+json.dumps(get_meme_keys()))'
    proc = subprocess.run([sys.executable, '-c', code], env=env, cwd=ROOT / 'backend/meme-generator', text=True, capture_output=True, timeout=30)
    keys = json.loads(next((x[8:] for x in proc.stdout.splitlines() if x.startswith('QA_KEYS '))))
    rows = []
    for i, key in enumerate(sorted(keys)):
        t = time.perf_counter()
        try:
            r = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--key', key], env=env, cwd=ROOT / 'backend/meme-generator', text=True, capture_output=True, timeout=15)
            lines = [x[10:] for x in r.stdout.splitlines() if x.startswith('QA_RESULT ')]
            row = json.loads(lines[-1]) if r.returncode == 0 and lines else {'key': key, 'status': 'failed', 'error': (r.stderr + r.stdout)[-1400:].replace(str(Path.home()), '~')}
        except subprocess.TimeoutExpired:
            row = {'key': key, 'status': 'timeout', 'error': '15 second per-template deadline'}
        row['process_seconds'] = round(time.perf_counter() - t, 4)
        rows.append(row)
        if (i + 1) % 25 == 0:
            print('Catalog', i + 1, '/', len(keys), 'passed', sum((x['status'] == 'passed' for x in rows)), flush=True)
        target = ROOT / args.output
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({'scope': 'local offline synthetic input, one default parameter combination per native template; not an aesthetic benchmark or server-capacity measurement', 'results': rows}, ensure_ascii=False, indent=2) + '\n')
    print('Catalog complete', len(rows), flush=True)
    raise SystemExit(0 if all((r['status'] == 'passed' for r in rows)) else 1)
