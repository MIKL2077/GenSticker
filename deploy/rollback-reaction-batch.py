"""Withdraw only the reviewed reaction batches before reverting their renderer.

Dry-run by default. Run using the feature runtime and its existing state path.
User templates, favorites, generation history and image files are not removed.
"""
import argparse,json
from pathlib import Path
from meme_generator.features.store import connect


def withdraw(paths,apply=False):
    expected={}
    for path in paths:
        batch=json.loads(Path(path).read_text())
        for item in batch['templates']:
            if not item['key'].startswith('auto_story_') or item['metadata'].get('conversion')!='reaction-story-v1':raise ValueError('not a reaction batch')
            expected[item['key']]=item['metadata']['original_hash']
    db=connect()
    try:
        selected=[]
        for key,digest in expected.items():
            row=db.execute('SELECT metadata,status FROM templates WHERE key=?',(key,)).fetchone()
            if not row:continue
            metadata=json.loads(row['metadata'])
            if metadata.get('conversion')!='reaction-story-v1' or metadata.get('original_hash')!=digest:raise ValueError('runtime template changed; inspect before rollback')
            if row['status']=='published':selected.append(key)
        if apply:
            with db:
                for key in selected:db.execute("UPDATE templates SET status='withdrawn' WHERE key=?",(key,))
        return {'mode':'applied' if apply else 'dry-run','templates':len(selected),'keys':selected}
    finally:db.close()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('manifests',nargs='+');p.add_argument('--apply',action='store_true');args=p.parse_args();print(json.dumps(withdraw(args.manifests,args.apply)))
