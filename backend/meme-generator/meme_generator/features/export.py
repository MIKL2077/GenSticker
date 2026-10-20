"""Bounded WeChat-size copies; originals remain available at their existing URLs."""

import base64
import binascii
from io import BytesIO
import threading
from PIL import Image, ImageSequence
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field
from ..safe_images import open_image

router = APIRouter()
slots = threading.BoundedSemaphore(2)
MAX_BYTES = 500 * 1024


class ExportRequest(BaseModel):
    image: str = Field(min_length=1, max_length=12 * 1024 * 1024)


def adapt(raw):
    if len(raw) > 8 * 1024 * 1024:
        raise ValueError("image too large")
    with open_image(BytesIO(raw)) as original:
        if getattr(original, "n_frames", 1) > 1:
            frames, durations = [], []
            for frame in ImageSequence.Iterator(original):
                image = frame.convert("RGBA")
                image.thumbnail((240, 240))
                plate = Image.new("RGBA", image.size, "white")
                plate.alpha_composite(image)
                frames.append(plate.convert("RGB"))
                durations.append(
                    max(20, min(10000, int(frame.info.get("duration", 100))))
                )
            if sum(durations) > 60000:
                raise ValueError("animation too long")
            for edge, stride, colors in (
                (240, 1, 128),
                (200, 1, 96),
                (160, 1, 64),
                (160, 2, 64),
                (120, 2, 48),
                (96, 3, 32),
                (64, 4, 16),
                (32, 6, 8),
            ):
                reduced, delays = [], []
                for i in range(0, len(frames), stride):
                    image = frames[i].copy()
                    image.thumbnail((edge, edge))
                    reduced.append(image.quantize(colors=colors))
                    delays.append(sum(durations[i : i + stride]))
                out = BytesIO()
                reduced[0].save(
                    out,
                    "GIF",
                    save_all=True,
                    append_images=reduced[1:],
                    duration=delays,
                    loop=original.info.get("loop", 0),
                    disposal=2,
                    optimize=True,
                )
                if len(out.getvalue()) <= MAX_BYTES:
                    return out.getvalue(), "image/gif"
        else:
            image = original.convert("RGBA")
            image.thumbnail((240, 240))
            out = BytesIO()
            image.save(out, "PNG", optimize=True)
            if len(out.getvalue()) <= MAX_BYTES:
                return out.getvalue(), "image/png"
    raise ValueError("export too large")


@router.post("/images/wechat-export")
def export_image(params: ExportRequest):
    if not slots.acquire(False):
        raise HTTPException(503, "导出处理中，请稍后再试")
    try:
        try:
            raw = base64.b64decode(params.image, validate=True)
            content, mime = adapt(raw)
        except (ValueError, binascii.Error, OSError, Image.DecompressionBombError):
            raise HTTPException(
                422, "请选择 8 MB 以内、动画不超过一分钟的图片；复杂动图请缩短后再试"
            )
        return Response(
            content, media_type=mime, headers={"Cache-Control": "private, no-store"}
        )
    finally:
        slots.release()
