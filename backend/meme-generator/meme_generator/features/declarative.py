"""Bounded template DSL; no executable model output or remote asset references."""
from io import BytesIO
from pathlib import Path
from typing import Literal
from PIL import Image, ImageOps, ImageDraw, ImageFont
from pydantic import BaseModel, Field, ConfigDict, model_validator
from .store import root


class Layer(BaseModel):
    model_config = ConfigDict(extra='forbid')
    type: Literal['subject', 'text', 'asset']
    box: tuple[int, int, int, int]
    slot: int = Field(default=0, ge=0, le=1)
    value: str = Field(default='', max_length=300)
    color: str = Field(default='#222222', pattern=r'^#[0-9a-fA-F]{6}$')
    font_size: int = Field(default=32, ge=10, le=100)
    fit: Literal['contain', 'cover'] = 'contain'


class TemplateSpec(BaseModel):
    model_config = ConfigDict(extra='forbid')
    width: int = Field(default=512, ge=64, le=1024)
    height: int = Field(default=512, ge=64, le=1024)
    background: str = Field(default='#ffffff', pattern=r'^#[0-9a-fA-F]{6}$')
    layers: list[Layer] = Field(min_length=1, max_length=20)
    defaults: list[str] = Field(default_factory=list, max_length=5)

    @model_validator(mode='after')
    def bounds(self):
        for layer in self.layers:
            x, y, w, h = layer.box
            if min(x,y) < 0 or min(w,h) < 1 or x+w > self.width or y+h > self.height:
                raise ValueError('layer outside canvas')
            if layer.type == 'asset' and (len(layer.value) != 64 or any(c not in '0123456789abcdef' for c in layer.value)):
                raise ValueError('asset must be a local SHA256')
        return self


def font(size):
    for path in [root().parent.parent / 'fonts/NotoSansSC-Regular.ttf', Path('/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc'), Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc')]:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    # Existing meme generator font directory, populated by deployment.
    from ..dirs import get_data_dir
    for path in (get_data_dir() / 'fonts').glob('**/*'):
        if path.suffix.lower() in ('.ttf','.otf','.ttc'):
            return ImageFont.truetype(str(path),size)
    return ImageFont.load_default(size=size)


def render(spec, images, texts=None):
    spec = TemplateSpec.model_validate(spec)
    canvas = Image.new('RGBA', (spec.width,spec.height), spec.background)
    for layer in spec.layers:
        x,y,w,h = layer.box
        if layer.type in ('subject','asset'):
            if layer.type == 'subject':
                if layer.slot >= len(images): raise ValueError('missing subject')
                image = images[layer.slot].convert('RGBA')
            else:
                with Image.open(root() / 'template_assets' / (layer.value+'.png')) as source: image = source.convert('RGBA')
            image = ImageOps.fit(image,(w,h)) if layer.fit == 'cover' else ImageOps.contain(image,(w,h))
            canvas.alpha_composite(image,(x+(w-image.width)//2,y+(h-image.height)//2))
        else:
            value = ((texts or spec.defaults)[layer.slot] if layer.slot < len(texts or spec.defaults) else layer.value)[:200]
            draw = ImageDraw.Draw(canvas)
            for size in range(layer.font_size,9,-1):
                face = font(size)
                lines, current = [], ''
                for char in value:
                    if char == '\n' or draw.textlength(current+char,font=face) > w:
                        lines.append(current); current = '' if char == '\n' else char
                    else: current += char
                lines.append(current)
                if len(lines)*(size+4) <= h: break
            if len(lines)*(size+4) > h: raise ValueError('text overflows')
            draw.multiline_text((x,y), '\n'.join(lines),font=face,fill=layer.color,spacing=4)
    output=BytesIO();canvas.convert('RGB').save(output,'JPEG',quality=90)
    return output
