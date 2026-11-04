"""Full template examples for sharing. Never render with a user's inputs."""
from io import BytesIO
from pathlib import Path

from fastapi import HTTPException, Response

from meme_generator.exception import MemeGeneratorException
from meme_generator.manager import get_meme
from meme_generator.safe_images import open_image
from .catalog import declared, refresh
from .public_preview import declared_source
from .store import connect

MAX_BYTES = 12 * 1024 * 1024


def example_response(key: str):
    # An entry removed from the catalog can remain in the runtime registry.
    # Check publication and block state before using that registry.
    db = connect()
    try:
        row = db.execute('SELECT status,spec,version FROM templates WHERE key=?', (key,)).fetchone()
        blocked = db.execute('SELECT 1 FROM template_blocks WHERE key=?', (key,)).fetchone()
    finally:
        db.close()
    if blocked or (row and row['status'] != 'published'):
        raise HTTPException(404, '模板不存在')
    if row and row['spec']:
        source = declared_source(declared(key))
    else:
        refresh()
        try:
            meme = get_meme(key)
        except MemeGeneratorException as error:
            raise HTTPException(error.status_code, error.message) from None
        # Use the exact same example chosen for the grid, at full resolution.
        directory = Path(__file__).resolve().parents[1] / 'memes' / meme.key
        source = next((directory / ('example' + ext) for ext in ('.gif', '.jpg', '.jpeg', '.png')
                       if (directory / ('example' + ext)).is_file()), None)
        if source is None:
            source = meme.generate_preview()
    raw = source.getvalue() if hasattr(source, 'getvalue') else Path(source).read_bytes()
    if not raw or len(raw) > MAX_BYTES:
        raise HTTPException(413, '模板示例过大，暂时无法分享')
    with open_image(BytesIO(raw)) as image:
        media = {'GIF': 'image/gif', 'PNG': 'image/png', 'JPEG': 'image/jpeg'}.get(image.format)
    if not media:
        raise HTTPException(422, '模板示例格式暂不支持分享')
    return Response(raw, media_type=media, headers={'Cache-Control': 'public, max-age=300'})
