from datetime import datetime

from PIL import Image, ImageOps

from pil_utils import BuildImage, Text2Image

from meme_generator import add_meme
from meme_generator.utils import make_jpg_or_gif


def ascii_rows(image, width=100, ratio=.5):
    """Composite alpha before luminance; black is the densest character."""
    rgba = image.convert("RGBA")
    paper = Image.new("RGBA", rgba.size, "white")
    paper.alpha_composite(rgba)
    gray = ImageOps.autocontrast(paper.convert("L"), cutoff=1)
    gray = gray.resize((width, max(1, round(gray.height * width / gray.width * ratio))), Image.Resampling.LANCZOS)
    palette = "@%#*+=-:. "
    pixels = [gray.getpixel((x,y)) for y in range(gray.height) for x in range(gray.width)]
    return ["".join(palette[min(len(palette)-1, value*len(palette)//256)]
                    for value in pixels[y*width:(y+1)*width]) for y in range(gray.height)]


def charpic(images: list[BuildImage], texts, args):
    t2m = Text2Image.from_text("@", 15, font_families=["Consolas"])
    ratio = t2m.longest_line / t2m.height

    def make(imgs: list[BuildImage]) -> BuildImage:
        lines = ascii_rows(imgs[0].image, width=100, ratio=ratio)
        text = "\n".join(lines)
        return BuildImage(
            Text2Image.from_text(text, 15, font_families=["Consolas"]).to_image(
                bg_color="white"
            )
        )

    return make_jpg_or_gif(images, make)


add_meme(
    "charpic",
    charpic,
    min_images=1,
    max_images=1,
    keywords=["字符画"],
    date_created=datetime(2022, 7, 21),
    date_modified=datetime(2024, 11, 1),
)
