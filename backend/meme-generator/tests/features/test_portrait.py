import unittest
from unittest.mock import patch
from PIL import Image,ImageDraw
from meme_generator.features.portrait import focus_portrait
from meme_generator.features import vision

class PortraitTests(unittest.TestCase):
    def test_person_focus_keeps_head_and_drops_full_body(self):
        image=Image.new('RGBA',(400,800));ImageDraw.Draw(image).rectangle((80,50,320,790),fill='red')
        output,analysis=focus_portrait(image,[('person',(130,80,100,120))])
        self.assertEqual(analysis['subject'],'person');self.assertEqual(analysis['framing'],'head')
        self.assertLess(output.height,250);self.assertEqual(output.width,output.height)
        self.assertLessEqual(analysis['focus_box'][1],80)
    def test_animal_head_retains_ears_and_largest_subject_wins(self):
        image=Image.new('RGBA',(500,500),(30,40,50,255))
        output,analysis=focus_portrait(image,[('animal',(100,120,160,140)),('animal',(10,10,20,20))])
        self.assertEqual(analysis['subject'],'animal');self.assertLess(analysis['focus_box'][1],120)
        self.assertGreater(output.width,250)
    def test_no_face_preserves_animal_or_object_silhouette(self):
        image=Image.new('RGBA',(500,700));ImageDraw.Draw(image).rectangle((200,300,280,450),fill='blue')
        output,analysis=focus_portrait(image,[]);self.assertEqual(analysis['framing'],'subject');self.assertLess(output.width,110);self.assertLess(output.height,180)
    def test_head_detection_is_downscaled_and_reused_for_focus(self):
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.png') as file:
            Image.new('RGB',(400,800),'white').save(file.name)
            with patch.object(vision,'_session',None),patch('meme_generator.features.portrait.detect_heads',return_value=[('person',(100,100,100,100))]) as detect:
                image,analysis=vision.process(file.name);detect.assert_called_once()
                self.assertEqual(analysis['framing'],'head');self.assertEqual(image.size,(165,165))
