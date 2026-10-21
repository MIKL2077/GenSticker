import json,os,tempfile,unittest,hashlib
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from PIL import Image,ImageDraw,ImageSequence
from meme_generator.features import reaction_templates as stories,storage,client_render
from meme_generator.features.declarative import render,TemplateSpec
from meme_generator.features.store import root


class ReactionTemplatesTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.env=patch.dict(os.environ,{'GENSTICKER_STATE_DIR':self.temp.name,'GENSTICKER_BOOTSTRAP_SEEDS':'0'});self.env.start()
        self.photo=Image.new('RGB',(180,150),'#459bbc')
    def tearDown(self):self.env.stop();self.temp.cleanup()
    def source(self,animated):
        frames=[Image.new('RGB',(100,80),c) for c in ['red','green','blue']];out=BytesIO()
        if animated:frames[0].save(out,'GIF',save_all=True,append_images=frames[1:],duration=[80,1200,220],loop=0)
        else:frames[0].save(out,'PNG')
        return out.getvalue()
    def prepare(self,kind='mixed',animated=True,layout='reply'):
        spec,assets,intent=stories.make_story(self.source(animated),kind=kind,layout=layout,context='看到这张照片的时候',animated=animated)
        directory=root()/'template_assets';directory.mkdir(exist_ok=True)
        for digest,data in assets.items():(directory/(digest+('.gif' if digest==spec['animation_asset'] else '.png'))).write_bytes(data)
        meta={'intent':intent,'animated':animated,'min_images':int(kind!='text'),'max_images':int(kind!='text'),'min_texts':int(kind!='image'),'max_texts':int(kind!='image')}
        stories.validate_story(spec,meta)
        return spec,meta
    def test_animation_keeps_frame_count_full_timing_and_uploaded_photo(self):
        spec,_=self.prepare();output=render(spec,[self.photo],['今天又发生什么了'])
        with Image.open(output) as image:
            self.assertEqual(image.format,'GIF');self.assertEqual(image.n_frames,3)
            self.assertEqual([f.info['duration'] for f in ImageSequence.Iterator(image)],[80,1200,220])
            image.seek(2);rgb=image.convert('RGB');self.assertLess(sum(abs(a-b) for a,b in zip(rgb.getpixel((100,170)),(69,155,188))),30)
        with Image.open(render(spec,[self.photo],preview=True)) as image:self.assertEqual(image.format,'JPEG');self.assertEqual(image.size,(480,560))
    def test_all_input_kinds_and_layouts_are_real_editable_templates(self):
        for kind in ['image','mixed','text']:
            for layout in ['reply','contrast','after','comment']:
                spec,_=self.prepare(kind,False,layout)
                with Image.open(render(spec,[self.photo] if kind!='text' else [],['新的触发场景'] if kind!='image' else [])) as im:self.assertGreater(im.width,300)
        spec,_=self.prepare('image');self.assertIsNotNone(spec['animation_box'])
        with self.assertRaises(ValueError):render(spec,[])
    def test_no_photo_or_text_can_cover_the_original_reaction(self):
        spec,meta=self.prepare();spec['layers'][0]['box']=list(spec['animation_box'])
        with self.assertRaisesRegex(ValueError,'overlaps'):stories.validate_story(spec,meta)
        with self.assertRaises(ValueError):TemplateSpec(width=200,height=200,layers=[{'type':'text','box':[0,0,100,50]}],animation_asset='a'*64)
    def test_animated_recipes_fall_back_and_gc_preserves_referenced_gifs(self):
        spec,meta=self.prepare();self.assertIsNone(client_render.public_recipe({'key':'auto_story_test','version':1,'spec':json.dumps(spec),'metadata':json.dumps(meta)}))
        self.assertIn(spec['animation_asset'],storage.asset_refs(spec))
    def test_oversized_animation_is_rejected_before_decoding_the_timeline(self):
        spec,_=self.prepare();path=root()/'template_assets'/(spec['animation_asset']+'.gif')
        frames=[Image.new('RGB',(40,40),(i*5,0,0)) for i in range(41)];frames[0].save(path,'GIF',save_all=True,append_images=frames[1:],duration=100)
        with self.assertRaisesRegex(ValueError,'frame budget'):render(spec,[self.photo])

    def test_multiline_context_changes_both_lines_in_every_animation_frame(self):
        import numpy as np
        spec,_=self.prepare('mixed');box=spec['layers'][-1]['box'];x,y,w,h=box
        before=render(spec,[self.photo],['甲甲甲\n乙乙乙'])
        after=render(spec,[self.photo],['丙丙丙\n丁丁丁'])
        with Image.open(before) as a,Image.open(after) as b:
            self.assertEqual(a.n_frames,b.n_frames)
            for index in range(a.n_frames):
                a.seek(index);b.seek(index)
                left=np.asarray(a.convert('RGB'));right=np.asarray(b.convert('RGB'))
                for top,bottom in [(y,y+h//2),(y+h//2,y+h)]:
                    self.assertGreater(np.abs(left[top:bottom,x:x+w].astype(int)-right[top:bottom,x:x+w]).sum(),100)
        with self.assertRaisesRegex(ValueError,'overflows'):render(spec,[self.photo],['一\n二\n三'])

    def test_two_independent_captions_use_both_slots(self):
        from PIL import ImageChops
        spec={'width':240,'height':160,'layers':[{'type':'text','slot':0,'box':[10,5,220,60],'font_size':28,'max_lines':2},{'type':'text','slot':1,'box':[10,85,220,60],'font_size':28,'max_lines':2}]}
        def picture(texts):return Image.open(render(spec,[],texts)).convert('RGB')
        original=picture(['上方原句','下方原句']);changed=picture(['上方换新','下方换新'])
        for box in [(0,0,240,75),(0,80,240,160)]:self.assertIsNotNone(ImageChops.difference(original.crop(box),changed.crop(box)).getbbox())
