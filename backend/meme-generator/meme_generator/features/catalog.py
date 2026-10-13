import hashlib
import json
import uuid
from datetime import datetime
from PIL import Image
from fastapi import APIRouter, HTTPException, Response
from .store import connect
from .declarative import TemplateSpec, render
from ..manager import get_memes, add_meme, get_meme_keys, get_meme

router = APIRouter()
loaded_versions={}
NAMESPACE = uuid.UUID('bcd6c8b6-6ffb-409c-92c0-69238a97c80c')


def emotion_tags(name):
    groups={'happy':['笑','开心','摸','亲','爱','喜'], 'angry':['怒','打','揍','气','爬'], 'sad':['哭','伤','悲','累'], 'surprised':['惊','震','什么','问号']}
    return [tag for tag,words in groups.items() if any(word in name for word in words)] or ['general']


def publish(key, metadata, spec=None):
    if spec is not None: spec=TemplateSpec.model_validate(spec).model_dump()
    metadata=dict(metadata)
    if spec is not None:
        # Publication gate: deterministic rendering must succeed with representative subjects.
        sample=Image.new('RGBA',(512,384),'#e0c3b0')
        render(spec,[sample,sample])
    fingerprint=hashlib.sha256(json.dumps({'metadata':metadata,'spec':spec},sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    identifier=uuid.uuid5(NAMESPACE,key).hex
    db=connect()
    try:
        with db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT * FROM templates WHERE key=?',(key,)).fetchone()
            if old and old['fingerprint']==fingerprint: return dict(old)
            version=old['version']+1 if old else 1
            values=(identifier,key,version,fingerprint,json.dumps(metadata,ensure_ascii=False),json.dumps(spec) if spec else None)
            db.execute('INSERT INTO templates(id,key,version,fingerprint,metadata,spec) VALUES(?,?,?,?,?,?) ON CONFLICT(key) DO UPDATE SET version=excluded.version,fingerprint=excluded.fingerprint,metadata=excluded.metadata,spec=excluded.spec,status=\'published\'',values)
            db.execute('INSERT INTO template_versions VALUES(?,?,?,?,?)',(identifier,version,fingerprint,values[4],values[5]))
        return dict(db.execute('SELECT * FROM templates WHERE key=?',(key,)).fetchone())
    finally: db.close()


def bootstrap():
    for meme in get_memes():
        if meme.key.startswith('auto_'): continue
        p=meme.params_type
        name=(meme.keywords or [meme.key])[0]
        publish(meme.key,{'name':name,'tags':sorted(set(meme.tags)|set(emotion_tags(name))), 'min_images':p.min_images,'max_images':p.max_images,'min_texts':p.min_texts,'max_texts':p.max_texts,'default_texts':p.default_texts,'origin':'bundled'})


def rows():
    db=connect()
    try: return [dict(r) for r in db.execute("SELECT * FROM templates WHERE status='published'")]
    finally: db.close()


def refresh():
    keys=set(get_meme_keys())
    for row in rows():
        if not row['spec'] or loaded_versions.get(row['key'])==row['version']: continue
        spec=json.loads(row['spec']);metadata=json.loads(row['metadata'])
        def generate(images,texts,args, spec=spec):
            return render(spec,[img.image for img in images],texts)
        if row['key'] in keys:
            meme=get_meme(row['key']);meme.function=generate;meme.keywords=[metadata['name']];meme.tags=set(metadata['tags'])
            for name in ['min_images','max_images','min_texts','max_texts','default_texts']: setattr(meme.params_type,name,metadata.get(name,[] if name=='default_texts' else 0))
        add_meme(row['key'],generate,min_images=metadata['min_images'],max_images=metadata['max_images'],min_texts=metadata.get('min_texts',0),max_texts=metadata.get('max_texts',0),default_texts=metadata.get('default_texts',[]),keywords=[metadata['name']],tags=set(metadata['tags']))
        loaded_versions[row['key']]=row['version']


@router.get('/templates')
def catalog():
    return [{'template_id':r['id'],'key':r['key'],'version':r['version'],**json.loads(r['metadata'])} for r in rows()]


def declared(key):
    db=connect()
    try: row=db.execute("SELECT * FROM templates WHERE key=? AND spec IS NOT NULL AND status='published'",(key,)).fetchone()
    finally: db.close()
    if not row: raise HTTPException(404,'模板不存在')
    return dict(row)


@router.get('/memes/{key}/info')
def info(key):
    r=declared(key);m=json.loads(r['metadata'])
    return {'key':key,'template_id':r['id'],'version':r['version'],'keywords':[m['name']],'tags':m['tags'],'params_type':{k:m.get(k,[] if k=='default_texts' else 0) for k in ['min_images','max_images','min_texts','max_texts','default_texts']}}


@router.get('/memes/{key}/thumbnail')
def thumbnail(key):
    r=declared(key)
    output=render(json.loads(r['spec']),[Image.new('RGBA',(256,256),'#ffcbad')]*2)
    with Image.open(output) as image:
        image.thumbnail((256,256));from io import BytesIO;small=BytesIO();image.save(small,'JPEG',quality=75)
    return Response(small.getvalue(),media_type='image/jpeg',headers={'Cache-Control':'public, max-age=300'})
