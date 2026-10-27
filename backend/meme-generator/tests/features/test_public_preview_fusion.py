import json
import os
import tempfile
import unittest
from io import BytesIO
from unittest.mock import patch
import numpy as np
from PIL import Image, ImageDraw
from meme_generator.features.public_preview import encode, response, declared_source
from meme_generator.features.declarative import TemplateSpec
from meme_generator.features.face_slot import composite, removal_mask, FaceInputError
from meme_generator.features.search_terms import keywords


class PreviewFusionTests(unittest.TestCase):
    def test_gif_preserves_motion_and_full_loop_timing(self):
        frames=[Image.new('RGB',(320,240),(i*3,0,255-i*3)) for i in range(60)]
        source=BytesIO();frames[0].save(source,'GIF',save_all=True,append_images=frames[1:],duration=[40]*60,loop=0)
        source.seek(0);raw,kind=encode(source)
        image=Image.open(BytesIO(raw));self.assertEqual(kind,'image/gif')
        self.assertGreater(image.n_frames,1);self.assertLessEqual(image.n_frames,32)
        self.assertLessEqual(max(image.size),192)
        duration=0;observed=[]
        for i in range(image.n_frames):image.seek(i);duration+=image.info['duration'];observed.append(image.convert('RGB').getpixel((0,0)))
        self.assertEqual(duration,2400);self.assertNotEqual(observed[0],observed[-1])

    def test_disk_cache_loader_runs_once_and_version_invalidation(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ,{'GENSTICKER_STATE_DIR':directory}):
            calls=[]
            def load():
                calls.append(1);out=BytesIO();Image.new('RGB',(256,256),'red').save(out,'PNG');out.seek(0);return out
            a=response('sample',1,load,'1');b=response('sample',1,load,'1')
            self.assertEqual(a.body,b.body);self.assertEqual(len(calls),1)
            self.assertIn('immutable',a.headers['cache-control'])
            c=response('sample',2,load,'1');self.assertEqual(len(calls),2)
            self.assertNotEqual(a.headers['etag'],c.headers['etag']);self.assertNotIn('immutable',c.headers['cache-control'])

    def test_all_blends_preserve_hands_and_exact_outside_pixels(self):
        original=Image.new('RGBA',(128,128),'#b9a993');draw=ImageDraw.Draw(original)
        draw.rectangle((70,60,85,105),fill='#efffff')
        photo=Image.new('RGBA',(80,100),'#bd6e4c');ImageDraw.Draw(photo).ellipse((15,20,65,75),fill='#222222')
        layer=TemplateSpec(width=128,height=128,layers=[{'type':'face','box':[20,10,80,100],
            'protect_polygons':[[[50,50],[65,50],[65,95],[50,95]]],'feather':4}]).layers[0]
        mask=np.array(removal_mask(original.size,[layer]))
        results=[]
        for mode in ['replace','color','seamless','expression']:
            canvas=original.copy();composite(canvas,photo,layer,background_prepared=True,mode=mode,reference=original)
            self.assertTrue(np.array_equal(np.array(canvas)[mask==0],np.array(original)[mask==0]),mode)
            results.append(np.array(canvas))
        self.assertFalse(np.array_equal(results[0],results[1]))
        with self.assertRaises(FaceInputError):composite(original,photo,layer,mode='unknown')
        for mode in ['color','seamless','expression']:
            with self.assertRaises(FaceInputError):composite(original,Image.new('RGBA',(8,8)),layer,mode=mode)

    def test_scenarios_synonyms_and_negation(self):
        self.assertIn('哈喽',keywords({'name':'白猫挥手'}))
        self.assertIn('感谢',keywords({'name':'谢谢老板'}))
        self.assertIn('睡觉',keywords({'name':'晚安'}))
        for name in ['笑不出来','不开心','不喜欢']:
            self.assertNotIn('快乐',keywords({'name':name}))
        self.assertIn('无奈',keywords({'name':'笑不出来'}))


if __name__=='__main__':unittest.main()
