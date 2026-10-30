import json
import unittest
from unittest.mock import patch

import numpy as np

from meme_generator.features import expression_driver as d
from meme_generator.features.declarative import ExpressionDriver
from meme_generator.features.element_templates import fingerprint
from meme_generator.features.reviewed_faces import validate_tenor_face


class InnerBrowDriverTests(unittest.TestCase):
    def test_inner_brow_lift_is_distinct_from_outer_brow_lift(self):
        points=np.full((478,2),64,dtype='float32')
        for ids,xs in [(d.m.L_BROW,np.linspace(24,56,len(d.m.L_BROW))),
                       (d.m.R_BROW,np.linspace(72,104,len(d.m.R_BROW)))]:
            points[ids,0]=xs;points[ids,1]=35
        values=np.zeros(17,np.float32);values[d.AU_ORDER.index(1)]=.8
        rgb=np.full((128,128,3),180,np.uint8)
        captured=[]
        def deform(rgb,before,after):
            captured.append(after.copy());return rgb.copy()
        with patch.object(d,'deform',side_effect=deform):
            d.eye_geometry(rgb,points,values)
            d.eye_geometry(rgb,points,values,inner_brow=True)
        for ids in [d.m.L_BROW,d.m.R_BROW]:
            inner=ids[np.argmin(abs(points[ids,0]-64))]
            outer=ids[np.argmax(abs(points[ids,0]-64))]
            self.assertAlmostEqual(captured[0][inner,1],captured[0][outer,1])
            self.assertLess(captured[1][inner,1],captured[1][outer,1]-2)
        np.testing.assert_array_equal(captured[0][d.m.OUTER],captured[1][d.m.OUTER])

    def test_v4_is_opt_in_and_has_a_separate_request_cache(self):
        portrait={'rgb':np.zeros((128,128,3),np.uint8),'p':np.zeros((478,2),np.float32)}
        with patch.object(d,'align',return_value=portrait), \
                patch.object(d,'eye_geometry',return_value=portrait['rgb']) as eye, \
                patch.object(d,'paste',side_effect=lambda rgb,*args:rgb):
            cache={}
            for method in ['geometry-eye-v2','geometry-eye-v4','geometry-eye-v4']:
                d.render_frame({}, {}, ExpressionDriver(method=method,aus=[0]*17),cache,0)
        self.assertEqual(eye.call_count,2)
        self.assertNotIn('inner_brow',eye.call_args_list[0].kwargs)
        self.assertTrue(eye.call_args_list[1].kwargs['inner_brow'])

    def test_v4_round_trip_preserves_the_recipe(self):
        driver=ExpressionDriver(method='geometry-eye-v4',aus=[.1]*17,gaze_x=-.15)
        value=driver.model_dump(mode='json')
        self.assertEqual(value,ExpressionDriver.model_validate_json(json.dumps(value)).model_dump(mode='json'))

    def test_review_evidence_cannot_substitute_a_different_eye_driver(self):
        key='tenor_face_'+'a'*24
        spec={'frames':[{'layers':[{'type':'face','expression':{'driver':{'method':'geometry-eye-v4'}}}]}]}
        metadata=dict(origin='tenor',source_url='https://tenor.com/view/cat-gif-123',
                      source_use='explicit-user-request-with-attribution',license='unverified',
                      min_images=1,max_images=1,min_texts=0,max_texts=0,
                      review=dict(source='local-tenor-face-review',visual_status='approved',
                                  template_key=key,selected_spec_sha256=fingerprint(spec),
                                  annotation_sha256='b'*64,method='eye-v4'))
        validate_tenor_face(key,spec,metadata)
        metadata['review']['method']='eye-v2'
        with self.assertRaisesRegex(ValueError,'driver differs'):
            validate_tenor_face(key,spec,metadata)
