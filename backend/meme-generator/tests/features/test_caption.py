import unittest
from PIL import Image,ImageChops
from pydantic import ValidationError
from meme_generator.features.caption import CaptionStyle,paint_caption
from meme_generator.features.livegif import LiveJob
class CaptionTests(unittest.TestCase):
    def test_position_color_background_and_size_affect_output(self):
        top=Image.new('RGB',(240,240),'white');paint_caption(top,'hello',CaptionStyle(x=.3,y=.2,size=.12,color='#ff4b55',background='dark',bold=False))
        bbox=ImageChops.difference(top,Image.new('RGB',top.size,'white')).getbbox();self.assertLess(bbox[3],100)
        bottom=Image.new('RGB',(240,240),'white');paint_caption(bottom,'hello',CaptionStyle(x=.7,y=.8,size=.18,color='#1890ff',background='color'))
        other=ImageChops.difference(bottom,Image.new('RGB',bottom.size,'white')).getbbox();self.assertGreater(other[1],120);self.assertGreater(other[2]-other[0],bbox[2]-bbox[0])
        blue=Image.new('RGB',(240,240),'white');paint_caption(blue,'hi',CaptionStyle(color='#1890ff',background='light'));self.assertTrue(any(pixel[2]>160 and pixel[0]<90 and pixel[1]<175 for pixel in blue.getdata()),'light background preserves the selected non-white text color')
    def test_invalid_style_is_rejected_before_queueing(self):
        for style in ({'x':float('nan')},{'y':1.1},{'size':1},{'color':'url(foo)'},{'background':'javascript'}):
            with self.assertRaises(ValidationError):LiveJob(asset_id='a'*32,idempotency_key='caption-check',caption_style=style)
