import hashlib
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
from PIL import Image
from pydantic import ValidationError
from meme_generator.features import expression_math as m, expression_controls as c, expression_runtime as rt
from meme_generator.features.declarative import ExpressionControls,ExpressionRecipe
from meme_generator.features.storage import asset_refs


def portrait():
    rng=np.random.default_rng(19);p=rng.uniform(12,52,(478,2)).astype('float32')
    for ids,center,axes in [(m.OVAL,(32,32),(22,28)),(m.L_EYE,(23,25),(5,2)),(m.R_EYE,(41,25),(5,2)),(m.OUTER,(32,43),(8,3)),(m.INNER,(32,43),(6,2))]:
        theta=np.linspace(0,2*np.pi,len(ids),endpoint=False);p[ids]=center+np.stack([np.cos(theta),np.sin(theta)],1)*axes
    # Canonical eye corners define a horizontal, nonzero scale.
    p[33]=[18,25];p[133]=[28,25];p[362]=[36,25];p[263]=[46,25]
    return {'p':p,'n':m.normalized(p),'rgb':np.full((64,64,3),140,np.uint8),'matte':np.ones((64,64),np.float32),'glasses':True}


class ReviewedExpressionTests(unittest.TestCase):
    def test_original_ab_file_is_unchanged(self):
        self.assertEqual(hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest(),'217d629e9e74d59ee0253d9effbc61ebdc54278c3b8543791f84455478923713')

    def test_component_masks_survive_archive_gc_in_both_recipe_paths(self):
        r={'reference_asset':'a'*64,'base_asset':'b'*64,'mask_asset':'c'*64,'controls':{'components':[{'name':'nose','mask_asset':'d'*64}]}}
        expected={x*64 for x in 'abcd'}
        self.assertEqual(asset_refs({'frames':[{'asset':'a'*64,'layers':[{'expression':r}]}]}),expected)
        self.assertEqual(asset_refs({'expression_policy':{'recipe':r}}),expected)

    def test_controls_are_bounded_and_optional(self):
        for v in [{'eye_aperture':[0,1]},{'opacity':float('nan')},{'profile':2},{'components':[{'name':'nose','mask_asset':'https://remote'}]}]:
            with self.assertRaises(ValidationError):ExpressionControls.model_validate(v)

    def test_extreme_cartoon_deformation_never_inverts_source_triangles(self):
        s=portrait();target=s['p'].copy();target[m.OVAL]=target[m.OVAL]*[.4,1.8]+[15,-12];target[m.OUTER]*=[1,1.2]
        q=c.controlled_points(s,target,.94,'animal',ExpressionControls(eye_strength=1,eye_aperture=(.015,.9),profile=-.9))
        _,tri=m.triangles(s['p'][m.IDS],64,64);a=s['p'][m.IDS];b=q[m.IDS]
        for ids in tri:
            def area(p):
                u=p[ids[1]]-p[ids[0]];v=p[ids[2]]-p[ids[0]];return u[0]*v[1]-u[1]*v[0]
            self.assertGreater(area(a)*area(b),0)

    def test_controlled_render_preserves_all_pixels_outside_authored_support(self):
        s=portrait();original=np.full((64,64,3),40,np.uint8);mask=np.zeros((64,64),np.uint8);mask[12:54,12:54]=255
        guide={'original':original,'base':original.copy(),'mask':mask,'p':s['p'],'components':[]}
        result,metric=c.render_frame(s,guide,.94,'animal',ExpressionControls(blur=2,opacity=.4,mouth='source'))
        self.assertTrue(np.array_equal(np.array(result)[mask==0],original[mask==0]));self.assertEqual(metric['fixed_pixel_max_error'],0)

    def test_default_recipe_keeps_frozen_dispatch_and_opt_in_routes_controls(self):
        from tests.features.test_expression_fusion import recipe
        canvas=Image.new('RGBA',(64,64),'white');guide={'base':np.full((64,64,3),255,np.uint8),'mask':np.ones((64,64),np.uint8)*255}
        with patch.object(rt,'prepare',return_value={}),patch.object(rt,'guide',return_value=guide),patch.object(rt.math,'render_frame',return_value=(canvas.convert('RGB'),{})) as old,patch.object(c,'render_frame',return_value=(canvas.convert('RGB'),{})) as new:
            rt.composite(canvas,canvas,ExpressionRecipe.model_validate(recipe()),0,{})
            rt.composite(canvas,canvas,ExpressionRecipe.model_validate(recipe()|{'controls':{'mouth':'source'}}),0,{})
            self.assertEqual(old.call_count,1);self.assertEqual(new.call_count,1)
