"""Restore reviewed fixtures and explicitly requested source batches shipped with code."""
from meme_generator.safe_images import open_image

import base64
import hashlib
import json
from pathlib import Path
from .store import connect, root
from .declarative import TemplateSpec
from .storage import asset_refs
from io import BytesIO


def restore(*, include_batches=True):
    from .catalog import publish

    manifest = json.loads(Path(__file__).with_name("template_seed.json").read_text())
    withdrawals = []
    if include_batches:
        for path in sorted(Path(__file__).with_name('template_batches').glob('*.json')):
            batch = json.loads(path.read_text())
            withdrawals.extend(batch.get('withdrawals', []))
            for item in batch['templates']:
                m = item['metadata']; q = m.get('quality', {})
                from urllib.parse import urlsplit
                source = urlsplit(m.get('source_url', ''))
                allowed = (m.get('origin') == 'chinesebqb' and source.hostname == 'github.com' and source.path.startswith('/zhaoolee/ChineseBQB/blob/')) or (m.get('origin') == 'weshine' and source.hostname == 'u.weshineapp.com')
                caption=(m.get('conversion')=='caption-preserved-v2' and q.get('observed_min_confidence',0)>=.95 and q.get('round_trip_mae',100)<=12 and q.get('protected_pixel_mae',100)<=.1)
                story=(m.get('conversion')=='reaction-story-v1' and q.get('reference_preserved') is True and q.get('replacement_verified') is True and q.get('slot_overlap_pixels',1)==0 and (not m.get('animated') or q.get('motion_verified') is True))
                elements = m.get('conversion') == 'element-replacement-v1'
                if elements:
                    from .element_templates import validate_elements
                    validate_elements(item['spec'], m)
                if not (allowed and source.scheme == 'https' and m.get('source_use') == 'explicit-user-request-with-attribution'
                        and m.get('review', {}).get('visual_status') == 'approved' and (caption or story or elements)):
                    raise ValueError('unreviewed source batch')
                if story:
                    from .reaction_templates import validate_story
                    validate_story(item['spec'],m)
            manifest['templates'].extend(batch['templates']); manifest['assets'].update(batch['assets'])
    retired = set(json.loads(Path(__file__).with_name("template_policy.json").read_text())["retired_keys"])
    db = connect()
    restored = 0
    try:
        with db:
            for item in withdrawals:
                # Withdraw only the precise legacy source version this manifest
                # reviewed. Never withdraw an operator's newer replacement.
                old = db.execute('SELECT metadata FROM templates WHERE key=?', (item['key'],)).fetchone()
                if old:
                    metadata = json.loads(old['metadata'])
                    if metadata.get('conversion') == 'reaction-story-v1' and metadata.get('original_hash') == item['original_hash']:
                        db.execute("UPDATE templates SET status='withdrawn' WHERE key=? AND status!='archived'", (item['key'],))
            for key in retired:
                db.execute("UPDATE templates SET status='withdrawn' WHERE key=? AND status!='archived'", (key,))
        for item in manifest["templates"]:
            if item['key'] in retired:
                continue
            archived=db.execute("SELECT 1 FROM templates WHERE key=? AND status='archived'",(item['key'],)).fetchone()
            if archived:
                continue
            metadata = item["metadata"]
            source_reference = metadata.get('source_use') == 'explicit-user-request-with-attribution' and metadata.get('review', {}).get('visual_status') == 'approved' and metadata.get('origin') in {'chinesebqb', 'weshine'}
            user_test = metadata.get('origin') == 'user-provided' and metadata.get('review', {}).get('explicit_user_request') is True
            if not user_test and not source_reference and metadata["license"] not in {"CC BY-SA 4.0", "Public domain"}:
                raise ValueError("unreviewed seed license")
            if metadata["origin"] == "openmoji":
                if not metadata["source_url"].startswith(
                    "https://github.com/hfg-gmuend/openmoji/blob/master/color/72x72/"
                ):
                    raise ValueError("unreviewed seed origin")
            elif not user_test and not source_reference and (
                metadata["source_url"]
                != "https://commons.wikimedia.org/wiki/File:LEGO_%22Y_U_NO_%22_meme_(Free_to_use).jpg"
            ):
                raise ValueError("unreviewed seed origin")
            old = db.execute("SELECT version FROM templates WHERE key=?", (item["key"],)).fetchone()
            if old and old['version'] >= item.get('version',1):
                continue
            spec = TemplateSpec.model_validate(item["spec"]).model_dump()
            for digest in asset_refs(spec):
                if digest in manifest['assets']:
                    raw = base64.b64decode(manifest["assets"][digest], validate=True)
                    if hashlib.sha256(raw).hexdigest() != digest:
                        raise ValueError("seed asset checksum mismatch")
                    directory = root() / "template_assets"
                    directory.mkdir(exist_ok=True)
                    suffix = '.gif' if raw.startswith((b'GIF87a', b'GIF89a')) else '.png'
                    with open_image(BytesIO(raw)) as image:
                        if image.format != ('GIF' if suffix == '.gif' else 'PNG'):
                            raise ValueError('seed asset format mismatch')
                    (directory / (digest + suffix)).write_bytes(raw)
                elif not any((root() / 'template_assets' / (digest + suffix)).is_file() for suffix in ['.png', '.gif']):
                    raise ValueError('seed asset missing')
            if item.get('prepare_background_from_reference'):
                from .face_slot import prepared_background
                with open_image(root()/'template_assets'/(spec['reference_asset']+'.png')) as source:
                    prepared=prepared_background(source,TemplateSpec.model_validate(spec).layers)
                output=BytesIO();prepared.save(output,'PNG');digest=hashlib.sha256(output.getvalue()).hexdigest()
                (root()/'template_assets'/(digest+'.png')).write_bytes(output.getvalue())
                spec['layers'][0]['value']=digest
            publish(item["key"], metadata, spec, minimum_version=item.get('version',1))
            with db:
                db.execute(
                    "INSERT OR IGNORE INTO candidates VALUES(?,?,?,?,?)",
                    (
                        metadata["original_hash"],
                        metadata["source_url"],
                        "published",
                        "restored reviewed public seed",
                        metadata.get("collected_at", 0),
                    ),
                )
            restored += 1
        return restored
    finally:
        db.close()


if __name__ == "__main__":
    print("restored", restore())
