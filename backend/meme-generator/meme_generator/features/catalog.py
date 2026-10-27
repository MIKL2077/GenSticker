from meme_generator.safe_images import open_image
import os
from pathlib import Path
import hashlib
import json
import uuid
from PIL import Image
from fastapi import APIRouter, HTTPException, Response
from .store import connect
from .search_terms import keywords as search_keywords
from .declarative import TemplateSpec, render
from ..manager import get_memes, add_meme, get_meme_keys, get_meme

router = APIRouter()
loaded_versions = {}
_native_functions = {}
NAMESPACE = uuid.UUID("bcd6c8b6-6ffb-409c-92c0-69238a97c80c")


@router.get('/templates/sources')
def sources():
    from .discovery import SOURCES
    return SOURCES


def emotion_tags(name):
    groups = {
        "happy": ["笑", "开心", "摸", "亲", "爱", "喜"],
        "angry": ["怒", "打", "揍", "气", "爬"],
        "sad": ["哭", "伤", "悲", "累"],
        "surprised": ["惊", "震", "什么", "问号"],
    }
    return [
        tag for tag, words in groups.items() if any(word in name for word in words)
    ] or ["general"]


def publish(key, metadata, spec=None, *, minimum_version=1, publication=None):
    db=connect()
    try:blocked=db.execute('SELECT 1 FROM template_blocks WHERE key=?',(key,)).fetchone()
    finally:db.close()
    if blocked:raise ValueError('template blocked by operator')
    retired=json.loads(Path(__file__).with_name("template_policy.json").read_text())["retired_keys"]
    if key in retired:
        raise ValueError("template withdrawn by owner")
    if spec is None and metadata.get('origin')=='bundled' and 'expression_policy' not in metadata:
        # Native bootstrap must retain the versioned A/B policy on restarts.
        db=connect()
        try:
            old=db.execute('SELECT metadata FROM templates WHERE key=?',(key,)).fetchone()
            if old and (policy:=json.loads(old['metadata']).get('expression_policy')):
                metadata={**metadata,'expression_policy':policy}
        finally:db.close()
    if spec is not None:
        spec = TemplateSpec.model_validate(spec).model_dump()
    metadata = dict(metadata)
    from .search_terms import keywords
    metadata["keywords"] = keywords(metadata)
    if spec is not None:
        # Publication gate: deterministic rendering must succeed with representative subjects.
        sample = Image.new("RGBA", (512, 384), "#e0c3b0")
        render(spec, [sample, sample], preview=True)
    fingerprint = hashlib.sha256(
        json.dumps(
            {"metadata": metadata, "spec": spec}, sort_keys=True, ensure_ascii=False
        ).encode()
    ).hexdigest()
    identifier = uuid.uuid5(NAMESPACE, key).hex
    db = connect()
    try:
        with db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT * FROM templates WHERE key=?", (key,)).fetchone()
            if old and old['status']=='archived':
                raise ValueError('template archived; restore the verified archive explicitly')
            if (not old or old['status']!='published') and db.execute("SELECT count(*) FROM templates WHERE status='published'").fetchone()[0] >= min(8000,max(1,int(os.getenv('GENSTICKER_PUBLIC_TEMPLATE_LIMIT','8000')))):
                raise ValueError('public template limit reached; archive old templates before publication')
            if old and old["fingerprint"] == fingerprint and old['version'] >= minimum_version:
                return dict(old)
            version = max((old["version"] + 1 if old and old['fingerprint'] != fingerprint else old['version'] if old else 1), minimum_version)
            values = (
                identifier,
                key,
                version,
                fingerprint,
                json.dumps(metadata, ensure_ascii=False),
                json.dumps(spec) if spec else None,
            )
            db.execute(
                "INSERT INTO templates(id,key,version,fingerprint,metadata,spec) VALUES(?,?,?,?,?,?) ON CONFLICT(key) DO UPDATE SET version=excluded.version,fingerprint=excluded.fingerprint,metadata=excluded.metadata,spec=excluded.spec,status='published'",
                values,
            )
            db.execute(
                "INSERT INTO template_versions VALUES(?,?,?,?,?)",
                (identifier, version, fingerprint, values[4], values[5]),
            )
            if publication:
                import time
                db.execute('INSERT INTO template_publications VALUES(?,?,?,?) ON CONFLICT(key) DO UPDATE SET batch_id=excluded.batch_id,published=excluded.published,score=excluded.score',(key,publication['batch_id'],time.time(),publication['score']))
        return dict(
            db.execute("SELECT * FROM templates WHERE key=?", (key,)).fetchone()
        )
    finally:
        db.close()


def bootstrap():
    db=connect()
    try:blocked={r[0] for r in db.execute('SELECT key FROM template_blocks')} | {r[0] for r in db.execute("SELECT key FROM templates WHERE status='archived'")}
    finally:db.close()
    for meme in get_memes():
        if meme.key in blocked:continue
        if meme.key.startswith("auto_"):
            continue
        p = meme.params_type
        name = (meme.keywords or [meme.key])[0]
        publish(
            meme.key,
            {
                "name": name,
                "input_hint": "每张图片填写一个对应名字，按上传顺序填写" if meme.key=='always_like' else "请填写图片里主角的名字" if meme.key in {'alipay','ask','google_captcha','make_friend','wechat_pay','why_have_hands'} else '',

                "tags": sorted(set(meme.tags) | set(emotion_tags(name))),
                "min_images": p.min_images,
                "max_images": p.max_images,
                "min_texts": p.min_texts,
                "max_texts": p.max_texts,
                "default_texts": p.default_texts,
                "origin": "bundled",
                "animated": (Path(__file__).resolve().parents[1]/'memes'/meme.key/'example.gif').is_file(),
                "subject_types": ["person", "animal", "object", "unknown"],
                "slot_aspect": 1.0,
            },
        )
    if os.getenv("GENSTICKER_BOOTSTRAP_SEEDS", "1") == "1":
        from .seed import restore

        restore()
        from .common_scenes import restore as restore_scenes
        restore_scenes()
        from .expression_library import restore as restore_expression
        restore_expression()


def rows():
    db = connect()
    try:
        return [
            dict(r)
            for r in db.execute("SELECT * FROM templates WHERE status='published'")
        ]
    finally:
        db.close()


def refresh():
    db=connect()
    try:published=[dict(r) for r in db.execute("SELECT key,version FROM templates WHERE status='published'")]
    finally:db.close()
    db=connect()
    try:blocked={r[0] for r in db.execute('SELECT key FROM template_blocks')} | {r[0] for r in db.execute("SELECT key FROM templates WHERE status='archived'")}
    finally:db.close()
    published=[row for row in published if row['key'] not in blocked]
    current = {row['key'] for row in published}
    from .. import manager
    for key in set(loaded_versions) | blocked:
        if key not in current:
            manager._memes.pop(key, None)
            loaded_versions.pop(key, None)
    keys = set(get_meme_keys())
    for row in published:
        if loaded_versions.get(row["key"]) == row["version"]:
            continue
        db=connect()
        try:row=dict(db.execute("SELECT * FROM templates WHERE key=? AND status='published'",(row['key'],)).fetchone() or {})
        finally:db.close()
        if not row:continue
        if not row['spec']:
            if row['key'] in keys:
                meme=get_meme(row['key'])
                original=_native_functions.setdefault(row['key'],meme.function)
                policy=json.loads(row['metadata']).get('expression_policy')
                from .expression_runtime import wrap_native
                meme.function=wrap_native(original,policy) if policy else original
                loaded_versions[row['key']]=row['version']
            continue
        spec = json.loads(row["spec"])
        metadata = json.loads(row["metadata"])

        def generate(images, texts, args, spec=spec):
            return render(spec, [img.image for img in images], texts, face_blend=getattr(args,"face_blend","replace"))

        if row["key"] in keys:
            meme = get_meme(row["key"])
            meme.function = generate
            meme.keywords = metadata.get("keywords") or [metadata["name"]]
            meme.tags = set(metadata["tags"])
            for name in [
                "min_images",
                "max_images",
                "min_texts",
                "max_texts",
                "default_texts",
            ]:
                setattr(
                    meme.params_type,
                    name,
                    metadata.get(name, [] if name == "default_texts" else 0),
                )
        if row["key"] not in keys:
            add_meme(
                row["key"],
                generate,
                min_images=metadata["min_images"],
                max_images=metadata["max_images"],
                min_texts=metadata.get("min_texts", 0),
                max_texts=metadata.get("max_texts", 0),
                default_texts=metadata.get("default_texts", []),
                keywords=metadata.get("keywords") or [metadata["name"]],
                tags=set(metadata["tags"]),
            )
        loaded_versions[row["key"]] = row["version"]


def public_metadata(raw):
    data=json.loads(raw) if isinstance(raw,str) else dict(raw)
    if policy:=data.get('expression_policy'):
        data['expression_policy']={k:v for k,v in policy.items() if k!='recipe'}
    return data


@router.get("/templates")
def catalog():
    db=connect()
    try:published=[dict(r) for r in db.execute("SELECT id,key,version,metadata FROM templates WHERE status='published'")]
    finally:db.close()
    return [
        {
            "template_id": r["id"],
            "key": r["key"],
            "version": r["version"],
            **public_metadata(r["metadata"]),
        }
        for r in published
    ]


def declared(key):
    db = connect()
    try:
        row = db.execute(
            "SELECT * FROM templates WHERE key=? AND spec IS NOT NULL AND status='published' AND NOT EXISTS (SELECT 1 FROM template_blocks WHERE template_blocks.key=templates.key)",
            (key,),
        ).fetchone()
    finally:
        db.close()
    if not row:
        raise HTTPException(404, "模板不存在")
    return dict(row)


@router.get("/memes/{key}/info")
def info(key):
    r = declared(key)
    m = json.loads(r["metadata"])
    return {
        "key": key,
        "template_id": r["id"],
        "version": r["version"],
        "keywords": search_keywords(m),
        "face_blend": "\"face\"" in r["spec"],
        "tags": m["tags"],
        "params_type": {
            k: m.get(k, [] if k == "default_texts" else 0)
            for k in [
                "min_images",
                "max_images",
                "min_texts",
                "max_texts",
                "default_texts",
            ]
        },
    }


@router.get("/memes/{key}/thumbnail")
def thumbnail(key, v: str | None = None):
    from .public_preview import response, declared_source
    row=declared(key)
    return response(key,row['version'],lambda:declared_source(row),v)
