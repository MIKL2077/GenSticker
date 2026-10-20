"""Bounded template DSL; no executable model output or remote asset references."""
from meme_generator.safe_images import open_image

from io import BytesIO
from pathlib import Path
from typing import Literal
from PIL import Image, ImageOps, ImageDraw, ImageFont
from pydantic import BaseModel, Field, ConfigDict, model_validator
from .store import root


class Layer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["subject", "face", "text", "asset"]
    box: tuple[int, int, int, int]
    slot: int = Field(default=0, ge=0, le=1)
    value: str = Field(default="", max_length=300)
    color: str = Field(default="#222222", pattern=r"^#[0-9a-fA-F]{6}$")
    font_size: int = Field(default=32, ge=10, le=100)
    fit: Literal["contain", "cover"] = "contain"
    align: Literal["left", "center", "right"] = "left"
    weight: Literal["normal", "bold"] = "normal"
    stroke_color: str = Field(default="#000000", pattern=r"^#[0-9a-fA-F]{6}$")
    stroke_width: int = Field(default=0, ge=0, le=4)
    tone: Literal["original", "grayscale"] = "grayscale"
    feather: int = Field(default=3, ge=0, le=12)
    erase_polygon: list[tuple[int, int]] = Field(default_factory=list, max_length=24)
    text_mask: Literal['box','glyph'] = 'box'
    max_lines: int = Field(default=0, ge=0, le=5)


class TemplateSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    width: int = Field(default=512, ge=64, le=1024)
    height: int = Field(default=512, ge=64, le=1024)
    background: str = Field(default="#ffffff", pattern=r"^#[0-9a-fA-F]{6}$")
    layers: list[Layer] = Field(min_length=1, max_length=20)
    defaults: list[str] = Field(default_factory=list, max_length=5)
    background_prepared: bool = False
    reference_asset: str = Field(default='',pattern=r'^(?:[a-f0-9]{64})?$')

    @model_validator(mode="after")
    def bounds(self):
        for layer in self.layers:
            x, y, w, h = layer.box
            if (
                min(x, y) < 0
                or min(w, h) < 1
                or x + w > self.width
                or y + h > self.height
            ):
                raise ValueError("layer outside canvas")
            if layer.type == "asset" and (
                len(layer.value) != 64
                or any(c not in "0123456789abcdef" for c in layer.value)
            ):
                raise ValueError("asset must be a local SHA256")
            if layer.erase_polygon and (layer.type != 'face' or len(layer.erase_polygon)<3 or any(px<0 or py<0 or px>=w or py>=h for px,py in layer.erase_polygon)):
                raise ValueError('face mask outside declared slot')
        return self


def font(size, bold=False):
    from ..dirs import get_data_dir
    filename = 'NotoSansSC-Bold.ttf' if bold else 'NotoSansSC-Regular.ttf'
    # A directory's first font can be Latin-only. Prefer the named CJK face in
    # both authoring and deployment so quality gates measure real glyphs.
    for path in (root().parent / 'fonts' / filename,
                 Path(__file__).resolve().parents[2] / 'resources/fonts' / filename,
                 get_data_dir() / 'fonts' / filename):
        if path.is_file():
            return ImageFont.truetype(str(path), size)
    if bold:
        for path in [root().parent / "fonts/NotoSansSC-Bold.ttf", Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"), Path("/System/Library/Fonts/STHeiti Medium.ttc")]:
            if path.exists():
                return ImageFont.truetype(str(path), size)
    for path in [
        root().parent / "fonts/NotoSansSC-Regular.ttf",
        Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path('/System/Library/Fonts/STHeiti Light.ttc'),
    ]:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    # Existing meme generator font directory, populated by deployment.
    from ..dirs import get_data_dir

    for path in (get_data_dir() / "fonts").glob("**/*"):
        if path.suffix.lower() in (".ttf", ".otf", ".ttc"):
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default(size=size)


def render(spec, images, texts=None, *, preview=False):
    spec = TemplateSpec.model_validate(spec)
    canvas = Image.new("RGBA", (spec.width, spec.height), spec.background)
    if preview and spec.reference_asset:
        with open_image(root()/'template_assets'/(spec.reference_asset+'.png')) as reference:
            canvas.alpha_composite(reference.convert('RGBA'))
    for layer in spec.layers:
        x, y, w, h = layer.box
        if layer.type == 'face':
            if preview:
                continue
            from .face_slot import composite, FaceInputError
            if layer.slot >= len(images):
                raise FaceInputError('请上传一张清晰的单人正面照片')
            composite(canvas, images[layer.slot], layer, background_prepared=spec.background_prepared)
        elif layer.type in ("subject", "asset"):
            if preview and spec.reference_asset and layer.type=='asset':continue
            if layer.type == "subject":
                if layer.slot >= len(images):
                    raise ValueError("missing subject")
                image = images[layer.slot].convert("RGBA")
            else:
                with open_image(
                    root() / "template_assets" / (layer.value + ".png")
                ) as source:
                    image = source.convert("RGBA")
            image = (
                ImageOps.fit(image, (w, h))
                if layer.fit == "cover"
                else ImageOps.contain(image, (w, h))
            )
            canvas.alpha_composite(
                image, (x + (w - image.width) // 2, y + (h - image.height) // 2)
            )
        else:
            value = (
                (texts or spec.defaults)[layer.slot]
                if layer.slot < len(texts or spec.defaults)
                else layer.value
            )[:200]
            draw = ImageDraw.Draw(canvas)
            fits=False
            for size in range(layer.font_size, 9, -1):
                face = font(size, layer.weight == "bold")
                lines, current = [], ""
                for char in value:
                    if char == "\n" or draw.textlength(current + char, font=face) > w - 2 * layer.stroke_width:
                        lines.append(current)
                        current = "" if char == "\n" else char
                    else:
                        current += char
                lines.append(current)
                if layer.max_lines and len(lines)>layer.max_lines:continue
                line_height = max(draw.textbbox((0,0), line or " ", font=face, stroke_width=layer.stroke_width)[3] - draw.textbbox((0,0), line or " ", font=face, stroke_width=layer.stroke_width)[1] for line in lines)
                if len(lines) * line_height + (len(lines)-1)*4 <= h:
                    fits=True
                    break
            if not fits:
                raise ValueError("text overflows")
            for index, line in enumerate(lines):
                bbox = draw.textbbox((0,0), line, font=face, stroke_width=layer.stroke_width)
                length = bbox[2]-bbox[0]
                left = x + (w-length)/2 if layer.align == "center" else x+w-length if layer.align == "right" else x
                draw.text((left-bbox[0], y + index*(line_height+4)-bbox[1]), line, font=face, fill=layer.color, stroke_width=layer.stroke_width, stroke_fill=layer.stroke_color)
    output = BytesIO()
    canvas.convert("RGB").save(output, "JPEG", quality=90)
    return output


def add_attribution(output, metadata):
    if metadata.get("origin") == "user-provided":
        return output
    if not metadata.get("source_url"):
        return output
    with open_image(output) as original:
        # Credits must be applied to each frame, never flatten a GIF to its cover.
        from PIL import ImageSequence
        frames=[];durations=[]
        if getattr(original,'n_frames',1)>240:raise ValueError('too many animation frames')
        for source in ImageSequence.Iterator(original):
            image=source.convert('RGB')
            credits=[metadata.get('author','')[:80]+' · '+metadata.get('license',''),metadata['source_url'],metadata.get('license_url','')]
            width=max(image.width,512);face=font(12);measure=ImageDraw.Draw(image);lines=[]
            for credit in credits:
                current=''
                for char in credit:
                    if measure.textlength(current+char,font=face)>width-12:lines.append(current);current=char
                    else:current+=char
                if current:lines.append(current)
            frame=Image.new('RGB',(width,image.height+len(lines)*16+12),'white');frame.paste(image,((width-image.width)//2,0))
            ImageDraw.Draw(frame).multiline_text((6,image.height+5),'\n'.join(lines),font=face,fill='#666666',spacing=4)
            frames.append(frame);durations.append(max(20,int(source.info.get('duration',100))))
        result=BytesIO()
        if len(frames)>1:frames[0].save(result,'GIF',save_all=True,append_images=frames[1:],duration=durations,loop=original.info.get('loop',0),disposal=2)
        else:frames[0].save(result,'JPEG',quality=90)
        return result
