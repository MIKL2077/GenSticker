"""Public, pinned weights for optional device inference; never serves user files."""
import hashlib
import os
from functools import lru_cache
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from .store import root

router=APIRouter()
MODEL_SHA='309c8469258dda742793dce0ebea8e6dd393174f89934733ecc8b14c76f4ddd8'
MODEL_BYTES=4574861

@lru_cache(maxsize=2)
def verified(path,mtime,size):
    return size==MODEL_BYTES and hashlib.sha256(Path(path).read_bytes()).hexdigest()==MODEL_SHA

@router.get('/images/subject-model/{filename}')
def subject_model(filename: str):
    if filename!=MODEL_SHA+'.onnx':raise HTTPException(404,'模型不存在')
    path=Path(os.getenv('U2NET_HOME',str(root()/'models')))/'u2netp.onnx'
    try:
        info=path.stat()
        if not verified(str(path),info.st_mtime_ns,info.st_size):raise HTTPException(503,'本机模型暂不可用，将使用云端处理')
    except OSError:raise HTTPException(503,'本机模型暂不可用，将使用云端处理')
    return FileResponse(path,media_type='application/octet-stream',headers={'Cache-Control':'public, max-age=31536000, immutable','ETag':'"'+MODEL_SHA+'"'})
