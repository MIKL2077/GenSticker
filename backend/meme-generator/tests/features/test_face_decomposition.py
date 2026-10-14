import os
import tempfile
import unittest
from io import BytesIO
from unittest.mock import patch
import numpy as np
from PIL import Image, ImageDraw
from meme_generator.features.decomposition import decompose
from meme_generator.features.declarative import render, TemplateSpec
from meme_generator.features.face_slot import locate, composite, FaceInputError


class FaceDecompositionTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'GENSTICKER_STATE_DIR':self.directory.name});self.env.start()
        image=Image.new('RGB',(256,256),'#756f65');buf=BytesIO();image.save(buf,'PNG');self.raw=buf.getvalue()
        self.face={'type':'face','box':[64,16,128,160],'erase_polygon':[[0,0],[127,0],[127,159],[0,159]]}
        self.brief={'canvas':[256,256],'intent':'保持背景和底部文字，按用户要求替换头部','protected':[{'name':'fixed prop','box':[0,180,40,40]}],'slots':[self.face,{'type':'text','box':[30,220,196,28],'value':'WHY NO?','font_size':18,'color':'#ffffff'}],'metadata':{'name':'test','origin':'user-provided','review':{'explicit_user_request':True},'source_url':'user test','author':'unknown','license':'unverified','license_url':''}}

    def tearDown(self):self.env.stop();self.directory.cleanup()

    def test_decomposition_guards_and_real_generation_boundary(self):
        with self.assertRaisesRegex(ValueError,'license'):decompose(self.raw,self.brief)
        conflict={**self.brief,'protected':[{'name':'overlap','box':[80,60,10,10]}]}
        with self.assertRaisesRegex(ValueError,'overlaps'):decompose(self.raw,conflict,authorized_local=True)
        wrong={**self.brief,'canvas':[512,256]}
        with self.assertRaisesRegex(ValueError,'dimensions'):decompose(self.raw,wrong,authorized_local=True)
        with self.assertRaisesRegex(ValueError,'actual face'):decompose(self.raw,self.brief,authorized_local=True,publish=True)
        result=decompose(self.raw,self.brief,authorized_local=True)
        self.assertEqual(result['metadata']['min_images'],1)
        self.assertFalse(result['metadata']['quality']['face_slot_tested'])
        self.assertEqual(Image.open(render(result['spec'],[],preview=True)).size,(256,256))
        with self.assertRaises(FaceInputError):render(result['spec'],[])

    def test_face_composite_preserves_outside_slot_and_grayscale(self):
        portrait=Image.new('RGB',(180,220),'white');draw=ImageDraw.Draw(portrait)
        draw.ellipse((25,10,155,210),fill='#e9a47f');draw.ellipse((25,10,155,70),fill='#222222');draw.ellipse((65,95,75,105),fill='black');draw.ellipse((105,95,115,105),fill='black')
        canvas=Image.new('RGBA',(256,256),'#756f65');before=np.array(canvas)
        layer=TemplateSpec(width=256,height=256,layers=[self.face]).layers[0]
        with patch('meme_generator.features.face_slot.locate',return_value=portrait):composite(canvas,portrait,layer)
        after=np.array(canvas);outside=np.ones((256,256),dtype=bool);outside[16:176,64:192]=False
        self.assertTrue(np.array_equal(before[outside],after[outside]))
        centre=after[80:130,105:150,:3];self.assertLess(np.abs(centre[:,:,0].astype(float)-centre[:,:,2]).mean(),5)
        self.assertGreater(np.abs(before.astype(float)-after).sum(),1000)
        bad={**self.face,'erase_polygon':[[0,0],[300,0],[0,20]]}
        with self.assertRaises(ValueError):TemplateSpec(width=256,height=256,layers=[bad])

    def test_no_ambiguous_or_oversized_face_is_silently_inserted(self):
        image=Image.new('RGB',(256,256),'white')
        with self.assertRaisesRegex(FaceInputError,'未找到'):locate(image)
        class Detector:
            def detectMultiScale(self,*args,**kwargs):return np.array([[10,20,80,80],[120,30,75,75]])
        with patch('meme_generator.features.face_slot.detectors',return_value=(Detector(),Detector())):
            with self.assertRaisesRegex(FaceInputError,'多张'):locate(image)
        with self.assertRaisesRegex(FaceInputError,'过大'):locate(Image.new('RGB',(2001,2000)))

    def test_seed_upgrades_same_key_without_recreating_template(self):
        import json
        from meme_generator.features.seed import restore
        from meme_generator.features.catalog import rows, publish
        from meme_generator.features.store import connect
        restore();current=rows()[0];meta=json.loads(current['metadata']);spec=json.loads(current['spec'])
        db=connect()
        with db:db.execute('DELETE FROM templates');db.execute('DELETE FROM template_versions')
        db.close()
        old=publish(current['key'],{**meta,'min_images':0,'max_images':0},{**spec,'layers':[l for l in spec['layers'] if l['type']!='face']})
        self.assertEqual(old['version'],1);self.assertEqual(restore(),1)
        upgraded=rows()[0];self.assertEqual(upgraded['id'],old['id']);self.assertEqual(upgraded['version'],2)
        self.assertEqual(json.loads(upgraded['metadata'])['min_images'],1);self.assertEqual(restore(),0)


if __name__=='__main__':unittest.main()
