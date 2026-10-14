import os,tempfile,unittest
from io import BytesIO
from unittest.mock import patch
from PIL import Image,ImageDraw
from meme_generator.features.subjects import extract_subject,SubjectError

def png(image):
    buf=BytesIO();image.save(buf,'PNG');return buf.getvalue()

class SubjectTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.env=patch.dict(os.environ,{'GENSTICKER_STATE_DIR':self.directory.name});self.env.start()
    def tearDown(self):self.env.stop();self.directory.cleanup()
    def test_transparent_input_reuses_alpha_without_model_or_face_detection(self):
        image=Image.new('RGBA',(128,128));ImageDraw.Draw(image).ellipse((20,10,100,115),fill='red')
        with patch('meme_generator.features.vision.warmup') as warm:
            output=Image.open(BytesIO(extract_subject(png(image))));warm.assert_not_called()
        self.assertLess(output.width,128);self.assertEqual(output.mode,'RGBA')
        self.assertLess(output.getextrema()[3][0],255)
    def test_opaque_input_calls_segmentation_once_without_emotion(self):
        original=Image.new('RGB',(128,128),'white');cutout=Image.new('RGBA',(128,128));ImageDraw.Draw(cutout).rectangle((25,20,100,110),fill='blue')
        with patch('meme_generator.features.vision._session',None),patch('meme_generator.features.vision.warmup',return_value=True) as warm,patch('meme_generator.features.vision.extract',return_value=cutout) as extract:
            output=extract_subject(png(original));warm.assert_called_once_with(include_emotion=False);extract.assert_called_once()
        self.assertGreater(len(output),0)
    def test_empty_and_animated_inputs_have_actionable_errors(self):
        with self.assertRaisesRegex(SubjectError,'主体为空'):extract_subject(png(Image.new('RGBA',(128,128))))
        buf=BytesIO();Image.new('RGB',(128,128),'red').save(buf,'GIF',save_all=True,append_images=[Image.new('RGB',(128,128),'blue')])
        with self.assertRaisesRegex(SubjectError,'动图'):extract_subject(buf.getvalue())
