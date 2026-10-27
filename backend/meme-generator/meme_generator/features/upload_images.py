"""Reconstruct native JPEG colour + lossless PNG alpha uploads before rendering."""
import base64
import binascii
import threading
from io import BytesIO

from fastapi import HTTPException
from PIL import Image
from meme_generator.safe_images import open_image

mask_slots = threading.BoundedSemaphore(2)


def restore_upload_masks(images: list[bytes], masks: list[str]) -> list[bytes]:
    if not masks:
        return images
    if len(masks) != len(images):
        raise HTTPException(422, '图片透明度数据数量不匹配，请重新选择')
    if not mask_slots.acquire(blocking=False):
        raise HTTPException(503, '图片处理繁忙，稍后再试一下')
    try:
        return _restore(images, masks)
    finally:
        mask_slots.release()


def _restore(images, masks):
    restored = []
    for raw, encoded in zip(images, masks):
        if not encoded:
            restored.append(raw)
            continue
        if len(encoded) > 6 * 1024 * 1024:
            raise HTTPException(413, '图片透明度数据过大，请先裁剪')
        try:
            mask_bytes = base64.b64decode(encoded, validate=True)
            limits = dict(max_pixels=1024*1024, max_frames=1)
            with open_image(BytesIO(raw), **limits) as colour, open_image(BytesIO(mask_bytes), **limits) as mask:
                if (colour.format != 'JPEG' or mask.format != 'PNG' or
                        max(colour.size) > 1024 or mask.size != colour.size or
                        getattr(mask, 'n_frames', 1) != 1):
                    raise ValueError('invalid alpha plane')
                result = colour.convert('RGBA')
                result.putalpha(mask.convert('L'))
                output = BytesIO()
                result.save(output, 'PNG')
                restored.append(output.getvalue())
        except (ValueError, binascii.Error, OSError, Image.DecompressionBombError):
            raise HTTPException(422, '图片透明度数据无效，请重新选择')
    return restored
