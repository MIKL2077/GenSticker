import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import cv2
import numpy as np
from PIL import Image, ImageDraw
from pydantic import ValidationError

from meme_generator.features.declarative import TemplateSpec, render
from meme_generator.features import face_fusion
from meme_generator.features.face_slot import composite, removal_mask, FaceInputError


def fixture():
    image=Image.new('RGBA',(96,96),'#c7947e');d=ImageDraw.Draw(image)
    d.rectangle((20,25,75,43),fill='#242424');d.line((37,64,59,64),fill='#803434',width=4)
    anchors=np.array([[34,35],[62,35],[46,50],[48,64],[48,83],[15,56],[81,56],
        [48,14],[48,2],[10,10],[86,10],[24,76],[72,76],[8,37],[88,37]],np.float32)
    alpha=Image.new('L',image.size);ImageDraw.Draw(alpha).ellipse((6,2,89,84),fill=255)
    return image,face_fusion.Portrait(np.asarray(image.convert('RGB')).copy(),np.asarray(alpha,dtype='float32')/255,anchors)


def spec_layer(**updates):
    value={'type':'face','box':[10,5,108,113],'tone':'original','feather':3,
        'protect_polygons':[[[0,50],[22,50],[22,105],[0,105]]],
        'fusion':{'eyes':[[38,38],[66,38]],'hair':[[52,18],[52,4],[16,12],[91,12],[8,38],[99,38]],
                  'fallback_box':[26,24,58,70],'edge':5}}
    value.update(updates)
    return TemplateSpec(width=128,height=128,layers=[value]).layers[0]


class CPUFusionTests(unittest.TestCase):
    def test_fixed_props_and_real_identity_pixels_survive_multiband(self):
        photo,portrait=fixture();layer=spec_layer();base=Image.new('RGBA',(128,128),'#e1d9c3')
        ImageDraw.Draw(base).rectangle((10,55,32,110),fill='#423021')
        before=np.asarray(base).copy();canvas=base.copy()
        self.assertTrue(face_fusion.composite(canvas,portrait,layer))
        mask=np.asarray(removal_mask(base.size,[layer]))
        self.assertTrue(np.array_equal(np.asarray(canvas)[mask==0],before[mask==0]))
        pixels=np.asarray(canvas)[:,:,:3]
        self.assertGreater(np.count_nonzero(pixels[30:55,40:85].max(2)<80),25)
        self.assertGreater(np.abs(np.asarray(canvas).astype(int)-before).sum(),1000)

    def test_a_gif_prepares_the_private_portrait_once_and_keeps_timing(self):
        photo,portrait=fixture()
        with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'GENSTICKER_STATE_DIR':directory}):
            assets=Path(directory)/'features/template_assets';assets.mkdir(parents=True);frames=[]
            for i,duration in enumerate([80,120,160]):
                im=Image.new('RGBA',(128,128),'#e1d9c3');ImageDraw.Draw(im).rectangle((5+i*5,95,30+i*5,120),fill='#423021')
                out=BytesIO();im.save(out,'PNG');raw=out.getvalue();digest=hashlib.sha256(raw).hexdigest();(assets/(digest+'.png')).write_bytes(raw)
                frames.append({'asset':digest,'duration_ms':duration,'layers':[spec_layer().model_dump()]})
            spec=TemplateSpec(width=128,height=128,frames=frames)
            with patch.object(face_fusion,'prepare',return_value=portrait) as prepare:
                output=render(spec,[photo]);self.assertEqual(prepare.call_count,1)
            im=Image.open(output);self.assertEqual(im.format,'GIF');self.assertEqual(im.n_frames,3)
            durations=[]
            for i in range(im.n_frames):im.seek(i);durations.append(im.info['duration'])
            self.assertEqual(durations,[80,120,160]);self.assertEqual(im.info['loop'],0)

    def test_no_face_is_a_bounded_avatar_paste_and_never_blocks_objects(self):
        photo=Image.new('RGBA',(50,50),'#09e033');layer=spec_layer();canvas=Image.new('RGBA',(128,128),'white')
        with patch.object(face_fusion,'prepare',return_value=None) as prepare:
            composite(canvas,photo,layer,background_prepared=True,fusion_inputs={})
            self.assertEqual(prepare.call_count,1)
        pixels=np.asarray(canvas);changed=np.any(pixels[:,:,:3]!=255,axis=2)
        self.assertTrue(changed.any());ys,xs=np.where(changed)
        self.assertGreaterEqual(xs.min(),36);self.assertLess(xs.max(),94)
        self.assertGreaterEqual(ys.min(),29);self.assertLess(ys.max(),99)

    def test_transparent_and_oversize_input_fail_before_loading_a_model(self):
        with patch.object(face_fusion,'warmup') as warmup:
            for image in [Image.new('RGBA',(64,64)),Image.new('RGB',(2001,2000))]:
                with self.assertRaises(FaceInputError):face_fusion.prepare(image)
            warmup.assert_not_called()

    def test_missing_model_uses_paste_and_corrupt_model_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(face_fusion,'_detector',None):
            path=Path(directory)/'model.task'
            with patch.dict(os.environ,{'GENSTICKER_FACE_LANDMARK_MODEL':str(path)}):
                self.assertFalse(face_fusion.warmup())
                path.write_bytes(b'not-the-pinned-public-model')
                with self.assertRaisesRegex(ValueError,'checksum'):face_fusion.warmup()

    def test_untrusted_recipes_cannot_escape_the_declared_slot(self):
        cases=[{'eyes':[[0,0],[float('nan'),3]]},{'eyes':[[5,5],[5,5]]},
            {'eyes':[[20,20],[50,20]],'hair':[[3,3]]},
            {'eyes':[[20,20],[150,20]]},{'eyes':[[20,20],[50,20]],'fallback_box':[0,0,999,2]}]
        for recipe in cases:
            with self.assertRaises(ValidationError):spec_layer(fusion=recipe)
        with self.assertRaises(ValidationError):spec_layer(type='subject')

    def test_photocopy_is_explicit_and_preserves_protected_pixels(self):
        _,portrait=fixture();base=Image.new('RGBA',(128,128),'white');layer=spec_layer()
        a=base.copy();face_fusion.composite(a,portrait,layer)
        ink=layer.model_copy(update={'fusion':layer.fusion.model_copy(update={'style':'photocopy'})})
        b=base.copy();face_fusion.composite(b,portrait,ink)
        self.assertFalse(np.array_equal(np.asarray(a),np.asarray(b)))
        self.assertTrue(np.all(np.asarray(b)[:,:,:3][:,:,0]==np.asarray(b)[:,:,:3][:,:,1]))


if __name__=='__main__':unittest.main()
