import os, tempfile, time, json
from io import BytesIO
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
with tempfile.TemporaryDirectory(prefix='gensticker-ocr-isolated-') as state:
    os.environ['GENSTICKER_STATE_DIR'] = state
    from meme_generator.features.quality import recognize, convert_caption
    from meme_generator.features.declarative import render
    image = Image.new('RGB', (512, 512), 'white')
    draw = ImageDraw.Draw(image)
    draw.ellipse((120, 130, 392, 390), fill='#e6c188')
    draw.text((35, 30), 'WHY NO?', font=ImageFont.truetype('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc', 42), fill='black')
    b = BytesIO()
    image.save(b, 'PNG')
    t = time.perf_counter()
    boxes = recognize(image)
    ocr_s = time.perf_counter() - t
    report = {'scope': 'isolated temporary state on production hardware; real OCR; no provider moderation, public publishing or production DB access', 'ocr_seconds': round(ocr_s, 4), 'recognized': [{'text': r[1], 'confidence': float(r[2])} for r in boxes]}
    try:
        t = time.perf_counter()
        spec, metadata = convert_caption(b.getvalue(), {'origin': 'user-provided', 'review': {'explicit_user_request': True}}, publish_result=False)
        out = render(spec, [], ['NEW JOKE'])
        report.update(status='passed', conversion_seconds=round(time.perf_counter() - t, 4), quality=metadata['quality'], replacement_output_bytes=len(out.getvalue()))
    except Exception as e:
        report.update(status='needs_manual', reason=str(e))
    Path('/tmp/gensticker-ocr-stage-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report))
