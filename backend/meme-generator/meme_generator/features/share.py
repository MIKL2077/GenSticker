"""Public immutable share artwork, with an explicit asset allowlist."""
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router=APIRouter()
COVERS=frozenset({'cover-v2.jpg','cover-v3.jpg','cover-v4.jpg','cover-v5.jpg'})


@router.get('/share/{name}',include_in_schema=False)
def share_cover(name:str):
    # No inference, user photos, authentication or arbitrary file access.
    if name not in COVERS:raise HTTPException(404,'分享封面不存在')
    return FileResponse(Path(__file__).resolve().parents[1]/'assets/share'/name,
                        media_type='image/jpeg',
                        headers={'Cache-Control':'public, max-age=31536000, immutable',
                                 'X-Content-Type-Options':'nosniff'})
