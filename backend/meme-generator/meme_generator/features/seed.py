"""Restore only the reviewed, openly licensed template fixtures shipped with code."""

import base64
import hashlib
import json
from pathlib import Path
from PIL import Image
from .store import connect, root
from .declarative import TemplateSpec


def restore():
    from .catalog import publish

    manifest = json.loads(Path(__file__).with_name("template_seed.json").read_text())
    retired = set(json.loads(Path(__file__).with_name("template_policy.json").read_text())["retired_keys"])
    db = connect()
    restored = 0
    try:
        with db:
            for key in retired:
                db.execute("UPDATE templates SET status='withdrawn' WHERE key=?", (key,))
        for item in manifest["templates"]:
            if item['key'] in retired:
                continue
            metadata = item["metadata"]
            user_test = metadata.get('origin') == 'user-provided' and metadata.get('review', {}).get('explicit_user_request') is True
            if not user_test and metadata["license"] not in {"CC BY-SA 4.0", "Public domain"}:
                raise ValueError("unreviewed seed license")
            if metadata["origin"] == "openmoji":
                if not metadata["source_url"].startswith(
                    "https://github.com/hfg-gmuend/openmoji/blob/master/color/72x72/"
                ):
                    raise ValueError("unreviewed seed origin")
            elif not user_test and (
                metadata["source_url"]
                != "https://commons.wikimedia.org/wiki/File:LEGO_%22Y_U_NO_%22_meme_(Free_to_use).jpg"
            ):
                raise ValueError("unreviewed seed origin")
            old = db.execute("SELECT version FROM templates WHERE key=?", (item["key"],)).fetchone()
            if old and old['version'] >= item.get('version',1):
                continue
            spec = TemplateSpec.model_validate(item["spec"]).model_dump()
            hashes={layer['value'] for layer in spec['layers'] if layer['type']=='asset'}
            if spec.get('reference_asset'):hashes.add(spec['reference_asset'])
            for digest in hashes:
                if digest in manifest['assets']:
                    raw = base64.b64decode(manifest["assets"][digest], validate=True)
                    if hashlib.sha256(raw).hexdigest() != digest:
                        raise ValueError("seed asset checksum mismatch")
                    directory = root() / "template_assets"
                    directory.mkdir(exist_ok=True)
                    (directory / (digest + ".png")).write_bytes(raw)
            if item.get('prepare_background_from_reference'):
                from .face_slot import prepared_background
                from io import BytesIO
                with Image.open(root()/'template_assets'/(spec['reference_asset']+'.png')) as source:
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
