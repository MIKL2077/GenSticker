import importlib.util
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image


ROOT = Path(__file__).resolve().parents[4]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT/path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


class ExpansionReviewTests(unittest.TestCase):
    def test_semantic_preflight_holds_watermark_false_anchors_and_partial_captions(self):
        selector = module('expansion_select','tools/qa/select_expansion_review.py')
        row = {'defaults':['你好'],'text_slots':1,'canvas':[300,300],
               'caption_inventory':[{'editable':True,'box':[0,240,140,40],'original_text':'你好'}],
               'geometry':[]}
        self.assertEqual(selector.preflight(row), [])
        row['defaults']=['腾讯视频']
        self.assertIn('source-credit-is-not-an-editable-caption', selector.preflight(row))
        row['defaults']=['你好']
        row['caption_inventory'].append({'editable':False,'original_text':'晚上好','box':[0,0,80,30]})
        self.assertIn('caption-inventory-needs-completeness-review', selector.preflight(row))
        row['geometry']=[[{'type':'face','box':[240,245,30,30]}]]
        self.assertIn('small-or-low-face-anchor-needs-manual-check', selector.preflight(row))

    def test_selection_hides_reserves_and_blocks_changed_recipe(self):
        server = module('expansion_server_selection','tools/qa/serve_expansion_review.py')
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp);(directory/'drafts').mkdir()
            for key in ['a','b']:
                (directory/'drafts'/(key+'.json')).write_text(json.dumps({
                    'key':key,'index':0,'status':'draft','animated':True,'spec_sha256':'v1',
                    'original_sha256':'original','outputs':[]}))
            (directory/'selection.json').write_text(json.dumps({'keys':['a'],'recipes':{'a':'v0'}}))
            review=server.Review(directory)
            self.assertEqual([x['key'] for x in review.data()['rows']],['a'])
            with self.assertRaisesRegex(ValueError,'技术检查'):
                review.save({'key':'a','spec_sha256':'v1','decision':'approved'})
            self.assertFalse((directory/'reviews.json').exists())

    def test_full_timeline_is_decoded_and_resampling_preserves_duration(self):
        prepare = module('expansion_prepare','tools/collect/prepare_expansion_review.py')
        frames = [Image.new('RGB',(80,80),(i*6,0,255-i*6)) for i in range(36)]
        output=BytesIO()
        frames[0].save(output,'GIF',save_all=True,append_images=frames[1:],duration=40,loop=0)
        raw, info=prepare.normalize(output.getvalue())
        self.assertEqual(info['original_frames'],36)
        self.assertEqual(info['frames'],24)
        self.assertEqual(info['source_indices'][0],0)
        self.assertEqual(info['source_indices'][-1],35)
        self.assertEqual(info['duration_ms'],1440)
        self.assertEqual(sum(info['durations']),1440)
        self.assertEqual(Image.open(BytesIO(raw)).n_frames,24)

    def test_a_single_frame_gif_is_never_counted_as_animation(self):
        prepare=module('expansion_prepare','tools/collect/prepare_expansion_review.py')
        output=BytesIO();Image.new('RGB',(80,80),'red').save(output,'GIF',duration=40)
        _, info=prepare.normalize(output.getvalue())
        self.assertFalse(info['animated'])
        self.assertEqual(info['frames'],1)

    def test_source_identity_survives_repository_revision_and_thumbnail_changes(self):
        prepare=module('expansion_prepare','tools/collect/prepare_expansion_review.py')
        a=prepare.source_identity({'source_url':'https://github.com/zhaoolee/ChineseBQB/blob/abc/cat/a.gif'})
        b=prepare.source_identity({'source_url':'https://github.com/zhaoolee/ChineseBQB/blob/def/cat/a.gif'})
        self.assertEqual(a,b)
        name='a'*32
        self.assertEqual(prepare.source_identity({'image_url':f'https://dl5.weshineapp.com/gif/day/s_{name}.gif'}),
                         prepare.source_identity({'image_url':f'https://dl5.weshineapp.com/gif/day/{name}.gif'}))

    def test_review_is_durable_recipe_bound_and_cannot_publish(self):
        server=module('expansion_server','tools/qa/serve_expansion_review.py')
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp);(directory/'drafts').mkdir()
            row={'key':'auto_element_'+'a'*24,'status':'draft','spec_sha256':'b'*64,
                 'original_sha256':'c'*64,'index':0,'animated':True,'outputs':[{'sample':'S03'}]}
            (directory/'drafts/x.json').write_text(json.dumps(row))
            review=server.Review(directory)
            with self.assertRaises(ValueError):review.save({'key':row['key'],'spec_sha256':'stale','decision':'approved'})
            review.save({'key':row['key'],'spec_sha256':row['spec_sha256'],'decision':'approved','note':'检查过全循环','keywords':['猫','猫']})
            again=server.Review(directory)
            self.assertEqual(again.records[row['key']]['decision'],'approved')
            self.assertEqual(again.records[row['key']]['keywords'],['猫'])
            self.assertEqual(json.loads((directory/'reviews.json').read_text())['publication'],'not-published')
            self.assertFalse(list(directory.rglob('*.sqlite3')))
            self.assertEqual(json.loads((directory/'drafts/x.json').read_text())['status'],'draft')


if __name__=='__main__':unittest.main()
