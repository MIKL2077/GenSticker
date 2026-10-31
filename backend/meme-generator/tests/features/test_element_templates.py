import hashlib
from io import BytesIO
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageDraw, ImageSequence

from meme_generator.features import client_render, storage
from meme_generator.features.declarative import TemplateSpec, render, font
from meme_generator.features.element_templates import compile_elements, fingerprint, validate_elements
from meme_generator.features.store import root


class ElementTemplateTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'GENSTICKER_STATE_DIR':self.directory.name})
        self.env.start()

    def tearDown(self):
        self.env.stop();self.directory.cleanup()

    def compile(self,animated=True):
        pictures=[];plans=[]
        for i in range(3 if animated else 1):
            image=Image.new('RGB',(128,128),'white');draw=ImageDraw.Draw(image)
            draw.text((3,3),'原文上',font=font(16),fill='black')
            draw.text((3,100),'原文下',font=font(16),fill='black')
            x=25+i*12;draw.rectangle((x,35,x+39,84),fill='red')
            draw.rectangle((x+15,35,x+23,84),fill='#00ff00')
            pictures.append(image)
            plans.append([
                {'type':'face','box':[x,35,40,50],'erase_polygon':[[0,0],[39,0],[39,49],[0,49]],
                 'protect_polygons':[[[15,0],[23,0],[23,49],[15,49]]],'tone':'original','fit':'cover'},
                {'type':'text','box':[3,3,122,28],'slot':0,'value':'原文上','font_size':16,'max_lines':2},
                {'type':'text','box':[3,100,122,28],'slot':1,'value':'原文下','font_size':16,'max_lines':2}])
        out=BytesIO()
        if animated:pictures[0].save(out,'GIF',save_all=True,append_images=pictures[1:],duration=[80,120,220],loop=0)
        else:pictures[0].save(out,'PNG')
        spec,assets,_=compile_elements(out.getvalue(),plans,['原文上','原文下'])
        directory=root()/'template_assets';directory.mkdir(exist_ok=True)
        for digest,data in assets.items():
            (directory/(digest+('.gif' if data.startswith(b'GIF') else '.png'))).write_bytes(data)
        return spec,pictures

    def test_moving_face_replaces_original_every_frame_and_keeps_occluding_prop(self):
        spec,sources=self.compile();photo=Image.new('RGB',(40,50),'blue')
        with Image.open(render(spec,[photo],['原文上','原文下'])) as output:
            self.assertEqual(output.n_frames,3)
            self.assertEqual([f.info['duration'] for f in ImageSequence.Iterator(output)],[80,120,220])
            for i in range(3):
                output.seek(i);frame=output.convert('RGB');x=25+i*12
                self.assertEqual(frame.getpixel((x+5,50)),(0,0,255))
                self.assertEqual(frame.getpixel((x+18,50)),(0,255,0))
                a=np.asarray(frame);b=np.asarray(sources[i]);mask=np.ones((128,128),dtype=bool);mask[35:85,x:x+40]=False
                # GIF's shared palette can quantize antialiased lettering.
                self.assertLess(np.abs(a.astype(int)-b.astype(int))[mask].mean(),3)
        with Image.open(render(spec,[],preview=True)) as preview:
            self.assertLess(np.abs(np.asarray(preview.convert('RGB')).astype(int)-np.asarray(sources[0]).astype(int)).mean(),1)

    def test_both_original_caption_regions_are_removed_and_multiline_is_visible(self):
        spec,_=self.compile(False);photo=Image.new('RGB',(40,50),'blue')
        with Image.open(render(spec,[photo],['',''])) as changed:
            array=np.asarray(changed.convert('RGB'))
            self.assertEqual(array[3:31,3:125].min(),255)
            self.assertEqual(array[100:128,3:125].min(),255)
        with Image.open(render(spec,[photo],['上下\n左右','新下'])) as changed:
            array=np.asarray(changed.convert('RGB'))
            for y1,y2 in [(3,17),(17,31),(100,128)]:
                self.assertLess(array[y1:y2,3:125].min(),100)
        with self.assertRaisesRegex(ValueError,'overflows'):
            render(spec,[photo],['一\n二\n三','新下'])

    def test_missing_empty_and_large_images_fail_without_a_face_detector(self):
        spec,_=self.compile(False)
        for photos in [[],[Image.new('RGBA',(30,40))],[Image.new('RGB',(2100,2100))]]:
            with self.assertRaises(Exception):render(spec,photos)
        render(spec,[Image.new('RGB',(40,60),'purple')])

    def test_bounded_frames_server_fallback_and_all_assets_remain_referenced(self):
        spec,_=self.compile()
        self.assertIsNone(client_render.public_recipe({'key':'face','version':2,'metadata':'{}','spec':json.dumps(spec)}))
        refs=storage.asset_refs(spec)
        for frame in spec['frames']:
            self.assertIn(frame['asset'],refs)
            for layer in frame['layers']:
                if layer['type']=='asset':self.assertIn(layer['value'],refs)
                if layer['original_asset']:self.assertIn(layer['original_asset'],refs)
        with self.assertRaises(ValueError):TemplateSpec.model_validate({**spec,'frames':spec['frames']*14})
        broken=json.loads(json.dumps(spec));broken['frames'][0]['source_index']=30
        with self.assertRaisesRegex(ValueError,'index missing'):render(broken,[Image.new('RGB',(10,10))])

    def test_review_is_bound_to_recipe_and_original_input_contract(self):
        spec,_=self.compile()
        meta={'conversion':'element-replacement-v1','source_canvas':[128,128],
              'min_images':1,'max_images':1,'min_texts':2,'max_texts':2,'default_texts':['原文上','原文下'],
              'review':{'visual_status':'approved'},'caption_inventory':[{'slot':0,'editable':True},{'slot':1,'editable':True}],
              'quality':{'spec_sha256':fingerprint(spec),'analyzed_frames':3,'protected_pixel_mae':0,
                         'actual_replacement_verified':True,'caption_inventory_complete':True,'motion_verified':True}}
        validate_elements(spec,meta)
        changed=json.loads(json.dumps(spec));changed['frames'][1]['layers'][1]['box'][0]+=1
        with self.assertRaisesRegex(ValueError,'evidence'):validate_elements(changed,meta)
        with self.assertRaisesRegex(ValueError,'input counts'):validate_elements(spec,{**meta,'max_images':2})

    def test_offline_ocr_partial_line_keeps_the_whole_source_paragraph_slot(self):
        import importlib.util
        path=Path(__file__).resolve().parents[4]/'tools/collect/rebuild_elements.py'
        module=importlib.util.module_from_spec(loader:=importlib.util.spec_from_file_location('element_proposals',path))
        loader.loader.exec_module(module)
        def caption(text,y):return {'text':text,'confidence':.99,'polygon':[[10,y],[100,y],[100,y+16],[10,y+16]]}
        tracks,frames=module.caption_tracks({'frames':[{'captions':[caption('上面一行',5),caption('下面一行',23)]},{'captions':[caption('下面一行',23)]}]},(128,128))
        self.assertEqual(len(tracks),1)
        self.assertEqual(frames[0][0][1]['box'],frames[1][0][1]['box'])
        self.assertIn('上面一行\n下面一行',[v['text'] for v in tracks[0]['variants']])

    def test_seed_upgrade_keeps_identity_and_withdraws_only_reviewed_legacy_rows(self):
        from meme_generator.features import seed, catalog
        from meme_generator.features.store import connect
        import base64
        spec,_=self.compile()
        meta={'name':'Original elements','tags':[],'conversion':'element-replacement-v1','source_canvas':[128,128],
              'origin':'weshine','source_url':'https://u.weshineapp.com/7','source_use':'explicit-user-request-with-attribution',
              'license':'unverified','original_hash':'a'*64,
              'min_images':1,'max_images':1,'min_texts':2,'max_texts':2,'default_texts':['原文上','原文下'],
              'review':{'visual_status':'approved'},'caption_inventory':[{'slot':0,'editable':True},{'slot':1,'editable':True}],
              'quality':{'spec_sha256':fingerprint(spec),'analyzed_frames':3,'protected_pixel_mae':0,
                         'actual_replacement_verified':True,'caption_inventory_complete':True,'motion_verified':True}}
        old={**meta,'conversion':'reaction-story-v1'}
        first=catalog.publish('auto_upgrade',old,spec)
        catalog.publish('auto_pending',old,spec)
        catalog.publish('auto_operator',{**meta,'conversion':'operator-replacement'},spec)
        folder=Path(self.directory.name)/'fixtures';(folder/'template_batches').mkdir(parents=True)
        (folder/'template_seed.json').write_text(json.dumps({'templates':[],'assets':{}}))
        (folder/'template_policy.json').write_text(json.dumps({'retired_keys':[]}))
        assets={}
        for digest in storage.asset_refs(spec):
            path=next(p for suffix in ['.png','.gif'] if (p:=root()/'template_assets'/(digest+suffix)).exists())
            assets[digest]=base64.b64encode(path.read_bytes()).decode()
        batch={'templates':[{'key':'auto_upgrade','version':2,'metadata':meta,'spec':spec}],'assets':assets,
               'withdrawals':[{'key':key,'original_hash':'a'*64} for key in ['auto_pending','auto_operator']]}
        (folder/'template_batches'/'reviewed.json').write_text(json.dumps(batch))
        # Assets may be in a later batch. Bounded loading must retain the
        # original cross-batch lookup and withdrawal/upgrade semantics.
        assets=batch.pop('assets');batch['assets']={}
        (folder/'template_batches'/'reviewed.json').write_text(json.dumps(batch))
        (folder/'template_batches'/'z-assets.json').write_text(json.dumps({'templates':[],'assets':assets}))
        # Exercise importing every nested asset, including the compressed GIF.
        for path in (root()/'template_assets').iterdir():path.unlink()
        with patch.object(seed,'Path',lambda _:folder/'seed.py'):
            self.assertEqual(seed.restore(),1)
            self.assertEqual(seed.restore(),0)
        rows={r['key']:r for r in catalog.rows()}
        self.assertEqual(rows['auto_upgrade']['id'],first['id'])
        self.assertEqual(rows['auto_upgrade']['version'],2)
        self.assertNotIn('auto_pending',rows);self.assertIn('auto_operator',rows)
        self.assertTrue((root()/'template_assets'/(spec['frames'][0]['asset']+'.gif')).exists())
        with connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM template_versions WHERE template_id=?',(first['id'],)).fetchone()[0],2)

    def test_crop_guide_uses_an_authored_frame_and_keeps_foreground_props(self):
        from fastapi import Request
        from meme_generator.features import catalog,editor
        spec,_=self.compile()
        catalog.publish('auto_guide',{'name':'Guide','tags':[],'min_images':1,'max_images':1,'min_texts':2,'max_texts':2},spec)
        result=editor.guide('auto_guide',Request({'type':'http','headers':[]}))
        self.assertFalse(result['generic']);self.assertEqual(result['windows'][0]['box'],[25,35,40,50])
        with Image.open(BytesIO(result['overlay'])) as overlay:
            self.assertEqual(overlay.getpixel((30,50))[3],0)
            self.assertEqual(overlay.getpixel((43,50))[3],255)


if __name__=='__main__':unittest.main()
