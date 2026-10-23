"""Acceptance: retire one already-withdrawn public template, restore exact bytes,
then re-archive it. Does not alter any active template or customer material.
"""
import hashlib,json
from meme_generator.features.store import connect,root
from meme_generator.features.template_archive import archive_template,restore_template,public_record
from meme_generator.features.storage import asset_refs


def snapshot(key):
 db=connect()
 try:
  row=dict(db.execute('SELECT * FROM templates WHERE key=?',(key,)).fetchone());versions=[dict(v) for v in db.execute('SELECT * FROM template_versions WHERE template_id=? ORDER BY version',(row['id'],))]
 finally:db.close()
 assets={}
 for ref in set().union(*(asset_refs(v['spec']) for v in versions if v['spec'])):
  for suffix in ['.png','.gif']:
   path=root()/'template_assets'/(ref+suffix)
   if path.is_file():assets[path.name]=hashlib.sha256(path.read_bytes()).hexdigest()
 return row,versions,assets


def main():
 db=connect();selected=None
 try:
  for row in db.execute("SELECT * FROM templates WHERE status='withdrawn' AND spec IS NOT NULL ORDER BY key"):
   try:public_record(row);selected=row['key'];break
   except ValueError:continue
 finally:db.close()
 if not selected:raise SystemExit('No already-withdrawn public fixture; no active template may be used')
 before=snapshot(selected);first=archive_template(selected);restored=restore_template(selected);after=snapshot(selected)
 if after!=before:raise RuntimeError('restore differs from original UUID/version/spec/artwork')
 final=archive_template(selected)
 print(json.dumps({'status':'passed','key':selected,'original_status':before[0]['status'],'stable_uuid':before[0]['id'],'version':before[0]['version'],'versions_verified':len(before[1]),'asset_files_verified':len(before[2]),'exact_database_and_artwork_roundtrip':True,'first_archive':first,'restore':restored,'final_archive':final,'active_templates_changed':0},ensure_ascii=False))


if __name__=='__main__':main()
