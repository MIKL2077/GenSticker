import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image,ImageDraw
from pydantic import ValidationError

from meme_generator.features.declarative import ExpressionRecipe,TemplateSpec,render
from meme_generator.features import expression_runtime as runtime
from meme_generator.features.storage import asset_refs


def recipe(mode='A'):
    points=[[32.,32.] for _ in range(478)];points[33]=[22.,25.];points[263]=[42.,25.]
    return {'mode':mode,'domain':'human','points':points,'reference_asset':'a'*64,'base_asset':'b'*64,'mask_asset':'c'*64}


class ExpressionFusionTests(unittest.TestCase):
    def test_new_rig_is_bounded_and_cannot_hide_on_an_asset(self):
        for changed in [{'mode':'C'},{'points':[[0,0]]*479},{'points':[[float('nan'),0]]*478}]:
            with self.assertRaises(ValidationError):ExpressionRecipe.model_validate({**recipe(),**changed})
        with self.assertRaises(ValidationError):
            TemplateSpec(width=64,height=64,layers=[{'type':'asset','box':[0,0,64,64],'value':'a'*64,'expression':recipe()}])

    def test_current_edited_props_survive_fusion_including_alpha(self):
        canvas=Image.new('RGBA',(64,64),(24,80,30,120));mask=np.zeros((64,64),np.uint8);mask[10:50,15:45]=255
        before=np.array(canvas).copy();cache={};r=ExpressionRecipe.model_validate(recipe('B'))
        with patch.object(runtime,'prepare',return_value={'supported':True}) as prepare,patch.object(runtime,'guide',return_value={'base':before[:,:,:3],'mask':mask}),patch.object(runtime.math,'render_frame',return_value=(Image.new('RGB',(64,64),'red'),{'fixed_pixel_max_error':0})) as renderer:
            runtime.composite(canvas,canvas,r,0,cache);runtime.composite(canvas,canvas,r,0,cache)
            self.assertEqual(prepare.call_count,1);self.assertEqual(renderer.call_args.args[2],.94)
        self.assertTrue(np.array_equal(np.array(canvas)[mask==0],before[mask==0]))
        self.assertTrue(np.all(np.array(canvas)[mask>0]==[255,0,0,255]))
        self.assertEqual(len(cache['expression_stats']),2)

    def test_animation_shares_preparation_and_retains_all_frame_durations(self):
        with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'GENSTICKER_STATE_DIR':directory}):
            assets=Path(directory)/'features/template_assets';assets.mkdir(parents=True);frames=[]
            for i,duration in enumerate([60,120,180]):
                im=Image.new('RGBA',(64,64),'white');ImageDraw.Draw(im).rectangle((i*4,50,10+i*4,60),fill='blue')
                out=BytesIO();im.save(out,'PNG');raw=out.getvalue();digest=hashlib.sha256(raw).hexdigest();(assets/(digest+'.png')).write_bytes(raw)
                frames.append({'asset':digest,'duration_ms':duration,'layers':[{'type':'face','box':[0,0,64,64],'expression':recipe()}]})
            guide={'base':np.full((64,64,3),255,np.uint8),'mask':np.pad(np.ones((20,20),np.uint8)*255,((20,24),(20,24)))}
            with patch.object(runtime,'prepare',return_value={'supported':True}) as prepare,patch.object(runtime,'guide',return_value=guide),patch.object(runtime.math,'render_frame',return_value=(Image.new('RGB',(64,64),'red'),{})):
                output=render({'width':64,'height':64,'frames':frames},[Image.new('RGB',(64,64),'green')]);self.assertEqual(prepare.call_count,1)
            gif=Image.open(output);self.assertEqual(gif.n_frames,3);durations=[]
            for i in range(gif.n_frames):gif.seek(i);durations.append(gif.info['duration'])
            self.assertEqual(durations,[60,120,180])

    def test_unavailable_face_falls_back_for_objects(self):
        spec={'width':64,'height':64,'layers':[{'type':'face','box':[0,0,64,64],'tone':'original','expression':recipe()}]}
        cache={}
        with patch.object(runtime,'prepare',return_value=None) as prepare:
            result=Image.open(render(spec,[Image.new('RGB',(64,64),'green')],_fusion_inputs=cache))
        self.assertEqual(prepare.call_count,1);self.assertFalse(cache['expression_stats'][0]['applied'])
        self.assertGreater(np.array(result)[:,:,1].sum(),0)

    def test_all_three_guide_assets_are_retained_for_native_and_declarative(self):
        expected={c*64 for c in 'abc'}
        self.assertEqual(asset_refs({'layers':[{'type':'face','expression':recipe()}]}),expected)
        self.assertEqual(asset_refs({'expression_policy':{'recipe':recipe()}}),expected)
        self.assertEqual(asset_refs(None),set())

    def test_delta_assets_are_atomic_readable_and_idempotent(self):
        import base64
        from meme_generator.features import expression_library as library
        from meme_generator.features.catalog import publish
        with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'GENSTICKER_STATE_DIR':directory}):
            folder=Path(directory);batches=folder/'expression_batches';batches.mkdir()
            assets=folder/'features/template_assets';assets.mkdir(parents=True)
            hashes=[];encoded={}
            for color in ['red','blue','white']:
                out=BytesIO();Image.new('RGB',(64,64),color).save(out,'PNG');raw=out.getvalue();digest=hashlib.sha256(raw).hexdigest();hashes.append(digest);encoded[digest]=base64.b64encode(raw).decode()
            existing=assets/(hashes[0]+'.png');existing.write_bytes(base64.b64decode(encoded[hashes[0]]));existing.chmod(0o600)
            metadata={'name':'permission fixture','origin':'bundled','max_images':1}
            old=publish('auto_permissions',metadata)
            r=recipe();r.update(dict(zip(['reference_asset','base_asset','mask_asset'],hashes)))
            metadata['expression_policy']={'mode':'A','visual_status':'pending-user-review','recipe':r}
            item={'key':'auto_permissions','base_version':old['version'],'base_fingerprint':old['fingerprint'],'version':old['version']+1,'spec':None,'metadata':metadata}
            (batches/'fixture.json').write_text(json.dumps({'format':'gensticker-expression-ab-v1','templates':[item],'assets':encoded}))
            with patch.object(library,'__file__',str(folder/'expression_library.py')):
                self.assertEqual(library.restore(),1);self.assertEqual(library.restore(),0)
            for digest in hashes:self.assertEqual((assets/(digest+'.png')).stat().st_mode & 0o777,0o644)
            self.assertEqual(list(assets.glob('*.tmp')),[])

    def test_native_nine_job_shares_input_and_releases_context(self):
        from pil_utils import BuildImage
        from meme_generator.meme import MemeArgsModel
        source=BuildImage(Image.new('RGB',(64,64),'green'));cache={}
        def original(images,texts,args):
            self.assertEqual(images[0].image.getpixel((0,0)),(0,128,0))
            return BytesIO(b'original')
        wrapped=runtime.wrap_native(original,{'recipe':recipe()})
        with patch.object(runtime,'prepare',return_value=None) as prepare:
            with runtime.shared_inputs(cache):
                for _ in range(9):self.assertEqual(wrapped([source],[],MemeArgsModel()).getvalue(),b'original')
            self.assertEqual(prepare.call_count,1)
            self.assertIsNone(runtime._shared_inputs.get())
            wrapped([source],[],MemeArgsModel())
            self.assertEqual(prepare.call_count,2)

    def test_native_policy_survives_bootstrap_and_client_cannot_bypass_it(self):
        from meme_generator.features.catalog import publish,refresh,loaded_versions,_native_functions,public_metadata
        from meme_generator.manager import get_meme
        from meme_generator.features.client_render import builtin_recipe
        policy={'mode':'A','visual_status':'pending-user-review','supported_regions':0}
        with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'GENSTICKER_STATE_DIR':directory}):
            loaded_versions.clear();_native_functions.clear()
            try:
                first=publish('always',{'name':'一直','origin':'bundled','expression_policy':policy})
                again=publish('always',{'name':'一直','origin':'bundled'})
                self.assertEqual(first['version'],again['version'])
                refresh();function=get_meme('always').function;refresh()
                self.assertIs(function,get_meme('always').function)
                self.assertIsNone(builtin_recipe('always'))
                self.assertNotIn('recipe',public_metadata({'expression_policy':{**policy,'recipe':recipe()}})['expression_policy'])
            finally:
                if 'always' in _native_functions:get_meme('always').function=_native_functions['always']
                loaded_versions.clear();_native_functions.clear()

    def test_missing_models_and_bad_inputs_do_not_launch_inference(self):
        with tempfile.TemporaryDirectory() as directory,patch.dict(os.environ,{'GENSTICKER_STATE_DIR':directory}),patch.object(runtime,'_detector',None),patch.object(runtime,'_segmenter',None):
            self.assertIsNone(runtime.prepare(Image.new('RGB',(64,64),'green')))
        from meme_generator.features.face_slot import FaceInputError
        for im in [Image.new('RGBA',(64,64)),Image.new('RGB',(2001,2000))]:
            with self.assertRaises(FaceInputError):runtime.prepare(im)

if __name__=='__main__':unittest.main()
