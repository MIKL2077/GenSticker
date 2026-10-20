"""Repeatable isolated regression suite; run with the backend Python environment."""
import argparse, json, os, re, subprocess, sys, tempfile, time
from datetime import datetime, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', default='docs/testing/evidence/latest-local.json')
    p.add_argument('--build', action='store_true')
    args = p.parse_args()
    commands = [(['node', str(f.relative_to(ROOT))], ROOT) for f in sorted((ROOT / 'frontend/tests').glob('*.cjs'))]
    backend = ROOT / 'backend/meme-generator'
    commands += [([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_account.py'], backend), ([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests/features', '-p', 'test_*.py'], backend)]
    if args.build:
        commands += [(['npm', 'run', 'build:mp-weixin'], ROOT / 'frontend'), (['npm', 'run', 'build:h5'], ROOT / 'frontend')]
    rows = []
    with tempfile.TemporaryDirectory(prefix='gensticker-qa-') as temp:
        env = {**os.environ, 'GENSTICKER_STATE_DIR': temp, 'GENSTICKER_BOOTSTRAP_SEEDS': '0', 'PYTHONPATH': str(backend)}
        for cmd, cwd in commands:
            started = time.perf_counter()
            try:
                result = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=240)
                log = result.stdout + result.stderr
                passed = result.returncode == 0
            except subprocess.TimeoutExpired:
                log = 'Timed out after 240 seconds'
                passed = False
            count = re.search('Ran (\\d+) tests?', log)
            row = {'command': ' '.join(cmd).replace(str(ROOT), '$REPO'), 'cwd': str(cwd.relative_to(ROOT)) or '.', 'status': 'passed' if passed else 'failed', 'seconds': round(time.perf_counter() - started, 3), 'cases': int(count.group(1)) if count else None, 'output': log.replace(str(ROOT), '$REPO')}
            rows.append(row)
            print(json.dumps({k: v for k, v in row.items() if k != 'output'}, ensure_ascii=False), flush=True)
    report = {'time_utc': datetime.now(timezone.utc).isoformat(), 'python': sys.version.split()[0], 'revision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(), 'status': 'passed' if all((r['status'] == 'passed' for r in rows)) else 'failed', 'results': rows}
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    return 0 if report['status'] == 'passed' else 1
if __name__ == '__main__':
    raise SystemExit(main())
