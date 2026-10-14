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


if __name__=='__main__':unittest.main()
