import unittest
import json
from unittest.mock import patch
import cv2
import numpy as np
from pydantic import ValidationError
from meme_generator.features.declarative import ExpressionDriver
from meme_generator.features import expression_driver as d


class EyeDriverTests(unittest.TestCase):
    def test_learned_mouth_cannot_repaint_nose_or_glasses(self):
        p=np.full((478,2),64,dtype='float32');p[d.m.OUTER,0]=np.linspace(48,80,len(d.m.OUTER));p[d.m.OUTER,1]=85
        base=np.full((128,128,3),90,np.uint8);generated=np.full_like(base,220)
        with patch.object(d,'eye_geometry',return_value=base):
            result=d.local_mouth(generated,{'rgb':base,'p':p},np.zeros(17,np.float32))
        np.testing.assert_array_equal(result[:79],base[:79])
        self.assertGreater(result[85,64,0],base[85,64,0])

    def test_old_driver_serialization_does_not_gain_new_fields(self):
        for method in ['geometry-v1','ganimation-emotionnet-v1']:
            raw={'method':method,'aus':[0.0]*17}
            self.assertEqual(ExpressionDriver.model_validate(raw).model_dump(mode='json'),raw)
            with self.assertRaises(ValidationError):
                ExpressionDriver(method=method,aus=[0]*17,gaze_x=.1)
        for value in [.21,-.21,float('nan')]:
            with self.assertRaises(ValidationError):
                ExpressionDriver(method='geometry-eye-v2',aus=[0]*17,gaze_x=value)

    def test_eye_driver_default_keeps_the_same_recipe_on_json_round_trips(self):
        value={'method':'geometry-eye-v2','aus':[0]*17}
        first=json.dumps(ExpressionDriver.model_validate(value).model_dump(mode='json'),sort_keys=True)
        for _ in range(3):
            second=json.dumps(ExpressionDriver.model_validate_json(first).model_dump(mode='json'),sort_keys=True)
            self.assertEqual(second,first)

    def test_blink_closes_own_eye_texture_and_keeps_outside_and_glasses(self):
        p=np.full((478,2),64,dtype='float32');rgb=np.full((128,128,3),190,np.uint8)
        angles=np.linspace(0,2*np.pi,16,endpoint=False)
        for ids,cx in [(d.m.L_EYE,42),(d.m.R_EYE,86)]:
            p[ids]=np.array([cx,46])+np.stack([np.cos(angles)*9,np.sin(angles)*3],1)
            cv2.ellipse(rgb,(cx,46),(7,2),0,0,360,(20,20,20),-1)
            cv2.line(rgb,(cx-12,38),(cx+12,38),(30,30,30),1)
        a=np.zeros(17,np.float32);a[-1]=1
        with patch.object(d,'geometric',side_effect=lambda points,values:points.copy()):
            result=d.eye_geometry(rgb,p,a)
        self.assertLess(np.count_nonzero(result[43:50,:,0]<80),np.count_nonzero(rgb[43:50,:,0]<80))
        np.testing.assert_array_equal(result[38],rgb[38])
        np.testing.assert_array_equal(result[80:],rgb[80:])
        with patch.object(d,'geometric',side_effect=lambda points,values:points.copy()):
            neutral=d.eye_geometry(rgb,p,np.zeros(17,np.float32))
        np.testing.assert_array_equal(neutral,rgb)

    def test_gaze_is_separate_in_request_cache(self):
        portrait={'rgb':np.zeros((128,128,3),np.uint8),'p':np.zeros((478,2),np.float32)}
        cache={}
        with patch.object(d,'align',return_value=portrait),patch.object(d,'eye_geometry',return_value=portrait['rgb']) as eye,patch.object(d,'paste',side_effect=lambda rgb,*args:rgb):
            for gaze in [0,.1,.1,0]:
                d.render_frame({}, {}, ExpressionDriver(method='geometry-eye-v2',aus=[0]*17,gaze_x=gaze),cache,0)
        self.assertEqual(eye.call_count,2)
