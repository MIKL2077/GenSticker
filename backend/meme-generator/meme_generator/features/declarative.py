"""Bounded template DSL; no executable model output or remote asset references."""
from meme_generator.safe_images import open_image

from io import BytesIO
from pathlib import Path
from typing import Literal
from PIL import Image, ImageOps, ImageDraw, ImageFont
from pydantic import BaseModel, Field, ConfigDict, model_validator
from .store import root


class FusionRecipe(BaseModel):
    """Measured head geometry, relative to the face layer's bounded box."""
    model_config = ConfigDict(extra="forbid")
    method: Literal['cpu-character-v1'] = 'cpu-character-v1'
    include_hair: bool = True
    style: Literal['natural','photocopy'] = 'natural'
    eyes: tuple[tuple[float,float],tuple[float,float]]
    hair: list[tuple[float,float]] = Field(default_factory=list,max_length=6)
    mouth: tuple[float,float] | None = None
    chin: tuple[float,float] | None = None
    fallback_box: tuple[int,int,int,int] | None = None
    edge: float = Field(default=4,ge=1,le=16)
    pyramid_levels: int = Field(default=3,ge=2,le=4)
    color_match: float = Field(default=.12,ge=0,le=.4)


class ExpressionRecipe(BaseModel):
    """Offline authored, full-canvas semantic rig; A/B parameters are immutable."""
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    method: Literal['cpu-expression-ab-v1'] = 'cpu-expression-ab-v1'
    mode: Literal['A','B']
    domain: Literal['human','ink','anime','animal']
    points: list[tuple[float,float]] = Field(min_length=478,max_length=478)
    reference_asset: str = Field(pattern=r'^[a-f0-9]{64}$')
    base_asset: str = Field(pattern=r'^[a-f0-9]{64}$')
    base_box: tuple[int,int,int,int] | None = None
    reference_format: Literal['png','gif'] = 'png'
    reference_index: int = Field(default=0,ge=0,le=39)
    mask_asset: str = Field(pattern=r'^[a-f0-9]{64}$')


class Layer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["subject", "face", "text", "asset"]
    box: tuple[int, int, int, int]
    slot: int = Field(default=0, ge=0, le=4)
    value: str = Field(default="", max_length=300)
    color: str = Field(default="#222222", pattern=r"^#[0-9a-fA-F]{6}$")
    font_size: int = Field(default=32, ge=6, le=100)
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
    original_asset: str = Field(default='', pattern=r'^(?:[a-f0-9]{64})?$')
    mask_asset: str = Field(default='', pattern=r'^(?:[a-f0-9]{64})?$')
    protect_polygons: list[list[tuple[int,int]]] = Field(default_factory=list,max_length=10)
    rotation: int = Field(default=0,ge=-180,le=180)
    line_spacing: int = Field(default=4,ge=0,le=16)
    direction: Literal['horizontal','vertical'] = 'horizontal'
    fusion: FusionRecipe | None = None
    expression: ExpressionRecipe | None = None


class TemplateFrame(BaseModel):
    """One authored frame: a clean plate, optional source preview and local slots."""
    model_config = ConfigDict(extra='forbid')
    asset: str = Field(pattern=r'^[a-f0-9]{64}$')
    asset_format: Literal['png','gif'] = 'png'
    source_index: int = Field(default=0,ge=0,le=39)
    reference_asset: str = Field(default='', pattern=r'^(?:[a-f0-9]{64})?$')
    duration_ms: int = Field(default=100, ge=20, le=8000)
    layers: list[Layer] = Field(default_factory=list, max_length=20)


class TemplateSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    width: int = Field(default=512, ge=64, le=1024)
    height: int = Field(default=512, ge=64, le=1024)
    background: str = Field(default="#ffffff", pattern=r"^#[0-9a-fA-F]{6}$")
    layers: list[Layer] = Field(default_factory=list, max_length=20)
    defaults: list[str] = Field(default_factory=list, max_length=5)
    background_prepared: bool = False
    reference_asset: str = Field(default='',pattern=r'^(?:[a-f0-9]{64})?$')
    animation_asset: str = Field(default='',pattern=r'^(?:[a-f0-9]{64})?$')
    animation_box: tuple[int,int,int,int] | None = None
    frames: list[TemplateFrame] = Field(default_factory=list, max_length=40)

    @model_validator(mode="after")
    def bounds(self):
        if not self.layers and not self.frames:raise ValueError('template has no layers or frames')
        if self.frames:
            if self.animation_asset or self.reference_asset or self.layers:raise ValueError('authored frames cannot mix legacy layers or animation')
            if self.width*self.height*len(self.frames)>8_000_000 or sum(f.duration_ms for f in self.frames)>8000:raise ValueError('authored timeline exceeds frame budget')
        if bool(self.animation_asset) != (self.animation_box is not None):raise ValueError('animation requires an asset and box')
        if self.animation_box:
            x,y,w,h=self.animation_box
            if min(x,y)<0 or min(w,h)<1 or x+w>self.width or y+h>self.height:raise ValueError('animation outside canvas')
            if self.reference_asset or any(l.type=='face' for l in self.layers):raise ValueError('animated reaction cannot mix head replacement')
        for layer in self.layers + [layer for frame in self.frames for layer in frame.layers]:
            x, y, w, h = layer.box
            if (
                min(x, y) < 0
                or min(w, h) < 1
                or x + w > self.width
                or y + h > self.height
            ):
                raise ValueError("layer outside canvas")
            if layer.expression:
                import math
                if layer.type!='face' or any(not math.isfinite(px) or not math.isfinite(py) or px < -self.width or px > 2*self.width or py < -self.height or py > 2*self.height for px,py in layer.expression.points):
                    raise ValueError('expression rig outside canvas bounds')
                if layer.expression.base_box:
                    bx,by,bw,bh=layer.expression.base_box
                    if min(bx,by)<0 or min(bw,bh)<1 or bx+bw>self.width or by+bh>self.height:raise ValueError('expression clean patch outside canvas')
                if math.dist(layer.expression.points[33],layer.expression.points[263])<2:
                    raise ValueError('expression rig requires distinct eye anchors')
            if layer.fusion:
                f=layer.fusion
                points=list(f.eyes)+f.hair+[p for p in [f.mouth,f.chin] if p is not None]
                import math
                if layer.type!='face' or len(f.hair) not in {0,6} or any(not math.isfinite(px) or not math.isfinite(py) or px<0 or py<0 or px>=w or py>=h for px,py in points):
                    raise ValueError('fusion geometry outside face slot')
                if f.fallback_box:
                    fx,fy,fw,fh=f.fallback_box
                    if min(fx,fy)<0 or min(fw,fh)<1 or fx+fw>w or fy+fh>h:raise ValueError('fallback outside fusion slot')
                if math.dist(*f.eyes)<2 or f.eyes[0][0]>=f.eyes[1][0]:raise ValueError('fusion eyes require ordered distinct anchors')
            if layer.type == "asset" and (
                len(layer.value) != 64
                or any(c not in "0123456789abcdef" for c in layer.value)
            ):
                raise ValueError("asset must be a local SHA256")
            if layer.erase_polygon and (layer.type != 'face' or len(layer.erase_polygon)<3 or any(px<0 or py<0 or px>=w or py>=h for px,py in layer.erase_polygon)):
                raise ValueError('face mask outside declared slot')
            if layer.original_asset and layer.type!='text':raise ValueError('original caption patch requires a text layer')
            if layer.mask_asset and layer.type!='face':raise ValueError('replacement mask requires a face layer')
            if any(len(polygon)<3 or len(polygon)>24 or any(px<0 or py<0 or px>=w or py>=h for px,py in polygon) for polygon in layer.protect_polygons):raise ValueError('protected polygon outside slot')
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


def render(spec, images, texts=None, *, preview=False, _transparent=False, _base=None, _reference=None, face_blend="replace", _fusion_inputs=None, _return_image=False):
    spec = TemplateSpec.model_validate(spec)
    if spec.frames:
        from .frame_render import render_frames
        return render_frames(spec,images,texts,preview=preview,face_blend=face_blend,_fusion_inputs=_fusion_inputs)
    if spec.animation_asset:
        from .reaction_animation import render_animation
        return render_animation(spec,images,texts,preview=preview)
    if _fusion_inputs is None:
        _fusion_inputs={}
    canvas = _base.convert('RGBA').copy() if _base is not None else Image.new("RGBA", (spec.width, spec.height), (0,0,0,0) if _transparent else spec.background)
    if not preview and spec.reference_asset and face_blend!='replace':
        with open_image(root()/'template_assets'/(spec.reference_asset+'.png')) as original:
            _reference=original.convert('RGBA')
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
            composite(canvas, images[layer.slot], layer, background_prepared=spec.background_prepared, mode=face_blend, reference=_reference, fusion_inputs=_fusion_inputs)
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
            )
            if _base is not None and len(value)>200:raise ValueError('text overflows')
            value=value[:200]
            if layer.original_asset and value == layer.value:
                with open_image(root()/'template_assets'/(layer.original_asset+'.png')) as patch:
                    if patch.size != (w,h):raise ValueError('original caption patch size mismatch')
                    canvas.alpha_composite(patch.convert('RGBA'),(x,y))
                continue
            draw = ImageDraw.Draw(canvas)
            if layer.direction=='vertical':
                columns=value.split('\n')
                for size in range(layer.font_size,5,-1):
                    face=font(size,layer.weight=='bold')
                    bounds=[draw.textbbox((0,0),char,font=face,stroke_width=layer.stroke_width) for char in value if char!='\n'] or [(0,0,1,1)]
                    char_width=max(b[2]-b[0] for b in bounds);char_height=max(b[3]-b[1] for b in bounds)
                    if len(columns)*char_width+(len(columns)-1)*layer.line_spacing<=w and max(map(len,columns))*(char_height+layer.line_spacing)-layer.line_spacing<=h:break
                else:raise ValueError('text overflows')
                if layer.max_lines and len(columns)>layer.max_lines:raise ValueError('text overflows')
                left=x+(w-(len(columns)*char_width+(len(columns)-1)*layer.line_spacing))/2
                for column_index,column in enumerate(reversed(columns)):
                    for char_index,char in enumerate(column):
                        bbox=draw.textbbox((0,0),char,font=face,stroke_width=layer.stroke_width)
                        draw.text((left+column_index*(char_width+layer.line_spacing)-bbox[0],y+char_index*(char_height+layer.line_spacing)-bbox[1]),char,font=face,fill=layer.color,stroke_width=layer.stroke_width,stroke_fill=layer.stroke_color)
                continue
            fits=False
            for size in range(layer.font_size, (6 if _base is not None else min(10,layer.font_size))-1, -1):
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
                if any(draw.textbbox((0,0), line, font=face, stroke_width=layer.stroke_width)[2]-draw.textbbox((0,0), line, font=face, stroke_width=layer.stroke_width)[0]>w for line in lines):continue
                line_height = max(draw.textbbox((0,0), line or " ", font=face, stroke_width=layer.stroke_width)[3] - draw.textbbox((0,0), line or " ", font=face, stroke_width=layer.stroke_width)[1] for line in lines)
                if len(lines) * line_height + (len(lines)-1)*layer.line_spacing <= h:
                    fits=True
                    break
            if not fits:
                raise ValueError("text overflows")
            for index, line in enumerate(lines):
                bbox = draw.textbbox((0,0), line, font=face, stroke_width=layer.stroke_width)
                length = bbox[2]-bbox[0]
                left = x + (w-length)/2 if layer.align == "center" else x+w-length if layer.align == "right" else x
                draw.text((left-bbox[0], y + index*(line_height+layer.line_spacing)-bbox[1]), line, font=face, fill=layer.color, stroke_width=layer.stroke_width, stroke_fill=layer.stroke_color)
    if _return_image:return canvas
    output = BytesIO()
    if _transparent:canvas.save(output,'PNG')
    else:canvas.convert("RGB").save(output, "JPEG", quality=90)
    return output
