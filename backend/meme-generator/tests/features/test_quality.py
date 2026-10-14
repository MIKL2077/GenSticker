import os
import tempfile
import unittest
from io import BytesIO
from unittest.mock import patch
from PIL import Image, ImageDraw, ImageFont
from meme_generator.features.ingest import convert
from meme_generator.features.store import connect
from meme_generator.features.discovery import discover


class QualityTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'GENSTICKER_STATE_DIR':self.directory.name});self.env.start()
        image=Image.new('RGB',(320,256),'white');draw=ImageDraw.Draw(image)
        draw.ellipse((70,20,250,180),fill='#ffa87c');draw.ellipse((110,70,130,90),fill='black');draw.ellipse((190,70,210,90),fill='black')
        draw.text((20,208),'WHY NO?',font=ImageFont.load_default(size=24),fill='black')
        buf=BytesIO();image.save(buf,'PNG');self.raw=buf.getvalue()
        self.meta={'name':'sample','source_url':'https://commons.wikimedia.org/wiki/File:Test.png','author':'fixture','license':'CC0','license_url':'https://creativecommons.org/publicdomain/zero/1.0/'}
        self.box=[[20,208],[170,208],[170,235],[20,235]]

    def tearDown(self):self.env.stop();self.directory.cleanup()

    def test_preserved_scene_and_duplicate_gate(self):
        with patch('meme_generator.features.quality.recognize',return_value=[(self.box,'WHY NO?',.99)]):
            spec=convert(self.raw,self.meta)
            self.assertFalse(any(l['type']=='subject' for l in spec['layers']))
            self.assertEqual(spec['defaults'],['WHY NO?'])
            db=connect();row=db.execute('SELECT metadata FROM templates').fetchone();db.close()
            self.assertIn('caption-preserved-v2',row['metadata'])
            with self.assertRaisesRegex(ValueError,'duplicate'):convert(self.raw,self.meta)

    def test_uncertain_and_animated_intent_is_pending(self):
        with patch('meme_generator.features.quality.recognize',return_value=[(self.box,'WHY NO?',.8)]):
            with self.assertRaisesRegex(ValueError,'intent'):convert(self.raw,self.meta)
        buf=BytesIO();Image.new('RGB',(128,128),'red').save(buf,'GIF',save_all=True,append_images=[Image.new('RGB',(128,128),'blue')])
        with self.assertRaisesRegex(ValueError,'animated'):convert(buf.getvalue(),self.meta)
        with self.assertRaisesRegex(ValueError,'license'):convert(self.raw,{**self.meta,'license':'unknown'})

    def test_discovery_metadata_only_and_idempotent(self):
        listing=[{'type':'dir','name':'010Cat_猫BQB','path':'010Cat_猫BQB'}]
        files=[{'type':'file','name':'one.png','path':'010Cat_猫BQB/one.png','size':100}]
        db=connect()
        with db:db.execute('INSERT INTO budgets(day) VALUES(date("now","+8 hours"))')
        db.close()
        with patch('meme_generator.features.discovery.fetch_json',side_effect=[listing,files,listing,files]):
            self.assertEqual(discover()['discovered'],1)
            self.assertEqual(discover()['discovered'],0)
        db=connect();row=db.execute('SELECT * FROM candidates').fetchone();db.close()
        self.assertEqual(row['status'],'license-pending')
        self.assertIn('未下载素材',row['reason'])

    def test_legacy_subject_replacement_excluded_from_ai(self):
        from meme_generator.features.catalog import publish
        from meme_generator.features.worker import candidates
        spec={'width':128,'height':128,'layers':[{'type':'subject','box':[0,0,128,128]}]}
        meta={'name':'sample','min_images':1,'max_images':1,'min_texts':0,'max_texts':0,'default_texts':[],'tags':['general']}
        publish('auto_legacy',{**meta,'conversion':'foreground-slot-v1'},spec)
        publish('auto_reviewed',{**meta,'conversion':'emoji-frame-v1'},spec)
        keys=[r['key'] for r in candidates({'user_id':'user','id':'job','day':'2026-10-14'},{'expression':'general','confidence':.9,'aspect':1})]
        self.assertNotIn('auto_legacy',keys)
        self.assertIn('auto_reviewed',keys)


    def test_user_template_preserves_scene_and_retirement(self):
        import json
        import numpy as np
        from pathlib import Path
        from meme_generator.features.seed import restore
        from meme_generator.features import seed
        from meme_generator.features.catalog import rows, publish
        from meme_generator.features.declarative import render, TemplateSpec
        from meme_generator.features.ingest import run_openmoji
        self.assertEqual(restore(),1)
        row=rows()[0];meta=json.loads(row['metadata']);spec=json.loads(row['spec'])
        self.assertEqual(meta['name'],'笑不出来');self.assertEqual(meta['min_images'],1)
        self.assertIn('sad',meta['tags']);self.assertNotIn('happy',meta['tags'])
        self.assertEqual(spec['layers'][-1]['color'],'#ffffff');self.assertEqual(spec['layers'][-1]['weight'],'bold')
        original=np.array(Image.open(render(spec,[],['笑不出来'],preview=True)))
        changed=np.array(Image.open(render(spec,[],['今天不想上班'],preview=True)))
        self.assertEqual(original.shape,changed.shape)
        self.assertLess(np.abs(original[:240].astype(float)-changed[:240]).mean(),.1)
        self.assertGreater(np.abs(original[259:304].astype(float)-changed[259:304]).mean(),1)
        self.assertEqual(run_openmoji()['downloaded'],0)
        retired=json.loads(Path(seed.__file__).with_name('template_policy.json').read_text())['retired_keys']
        with self.assertRaisesRegex(ValueError,'withdrawn'):publish(retired[0],meta,spec)
        db=connect()
        with db:db.execute('INSERT INTO templates(id,key,version,fingerprint,metadata,spec) VALUES(?,?,?,?,?,?)',('retired',retired[0],1,'old','{}',None))
        db.close();restore()
        self.assertFalse(any(r['key'] in retired for r in rows()))
        invalid={**spec,'layers':[dict(l) for l in spec['layers']]};invalid['layers'][-1]['stroke_width']=10
        with self.assertRaises(ValueError):TemplateSpec.model_validate(invalid)


if __name__=='__main__':unittest.main()
