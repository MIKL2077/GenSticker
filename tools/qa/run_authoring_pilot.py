"""Run real discovery/authoring in an isolated catalog shadow, never production.
Existing public fingerprints prevent counting already-known memes as additions.
"""
import argparse
import json
import os
from pathlib import Path
import sqlite3
from meme_generator.features.store import connect
from meme_generator.features.minimax_authoring import MiniMax
from meme_generator.features.scheduled_authoring import run


def main():
    p=argparse.ArgumentParser();p.add_argument('--baseline',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=True);os.environ['GENSTICKER_STATE_DIR']=str(args.output/'state');os.environ['GENSTICKER_BOOTSTRAP_SEEDS']='0'
    original=sqlite3.connect('file:'+str(args.baseline/'features/features.sqlite3')+'?mode=ro',uri=True);original.row_factory=sqlite3.Row;db=connect();copied=0
    try:
        with db:
            for row in original.execute('SELECT * FROM templates'):
                meta=json.loads(row['metadata'])
                if meta.get('origin') in {'user','user-provided','studio','private'} or meta.get('creator') or meta.get('user_id'):continue
                db.execute('INSERT OR IGNORE INTO templates VALUES(?,?,?,?,?,NULL,?)',(row['id'],row['key'],row['version'],row['fingerprint'],row['metadata'],row['status']));copied+=1
    finally:original.close();db.close()
    client=MiniMax(limit=45)
    try:report=run(client=client,force=True,target=3,max_attempts=12)
    finally:client.close()
    report.update(publication_scope='isolated-pilot-only',copied_public_fingerprints=copied)
    (args.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
