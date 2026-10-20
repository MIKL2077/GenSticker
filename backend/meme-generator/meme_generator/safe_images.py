"""Allow only required decoders, bounding frames before scanning an animation."""

from PIL import Image

FORMATS = ("JPEG", "PNG", "WEBP", "GIF")
MAX_PIXELS = 24_000_000
MAX_FRAMES = 180
MAX_TOTAL_PIXELS = 96_000_000


def open_image(
    source,
    *,
    max_pixels=MAX_PIXELS,
    max_frames=MAX_FRAMES,
    max_total_pixels=MAX_TOTAL_PIXELS,
):
    image = Image.open(source, formats=FORMATS)
    try:
        pixels = image.width * image.height
        if pixels > max_pixels:
            raise ValueError("图片尺寸过大，请先缩小图片")
        allowed = min(max_frames, max_total_pixels // max(1, pixels))
        if allowed < 1:
            raise ValueError("图片尺寸过大，请先缩小图片")
        # n_frames may itself walk an entire hostile GIF. Seek only as far as
        # the permitted frame/pixel budget, then reset the lazy reader.
        try:
            image.seek(allowed)
        except EOFError:
            pass
        else:
            raise ValueError("动画帧数或总像素过大，请先缩小动图")
        image.seek(0)
        return image
    except Exception:
        image.close()
        raise


def open_input_image(source):
    # Uploaded images can be expanded by templates; keep their budget smaller
    # than the bounded internal/export result reader.
    image = open_image(
        source, max_pixels=12_000_000, max_frames=120, max_total_pixels=24_000_000
    )
    try:
        image.load()
        return image
    except Exception:
        image.close()
        raise
