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
    def test_frontal_source_adoption_preserves_key_and_retires_rejected_profile(self):
        author=module('tenor_source_adoptions','tools/collect/author_tenor_faces.py')
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp);key='tenor_face_'+'a'*24
            (p/'source_adoptions.json').write_text(json.dumps({'adopted':{'123':key},'retired_source_ids':['456']}))
            self.assertEqual(author.source_adoptions(p),({'123':key},{'456'}))
            (p/'source_adoptions.json').write_text(json.dumps({'123':'../outside'}))
            with self.assertRaisesRegex(ValueError,'adoption'):author.source_adoptions(p)

    def test_export_never_admits_stale_or_withdrawn_face_approval(self):
        exporter=module('tenor_face_export','tools/qa/export_tenor_faces.py')
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp);(p/'drafts').mkdir()
            (p/'reviews.json').write_text(json.dumps({'records':{'a':{'decision':'approved','spec_sha256':'main','method':'geometry','selected_spec_sha256':'old'}}}))
            (p/'drafts/a.json').write_text(json.dumps({'key':'a','status':'draft','spec_sha256':'main','variants':{'geometry':{'spec_sha256':'current'}}}))
            with self.assertRaisesRegex(ValueError,'stale/blocked'):exporter.export(p,p,p/'export')
            self.assertEqual(list((p/'export').glob('*approved*.json')),[])
            (p/'withdrawal.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'withdrawn'):exporter.export(p,p,p/'export')

    def test_selected_face_method_is_bound_and_failed_method_cannot_be_approved(self):
        server=module('face_method_review','tools/qa/serve_expansion_review.py')
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp);(directory/'drafts').mkdir()
            row={'key':'face','index':1,'status':'draft','spec_sha256':'primary','original_sha256':'source',
                 'outputs':[],'variants':{'geometry':{'spec_sha256':'geo','label':'geometry'},
                 'gan':{'spec_sha256':'bad','label':'GAN'}},'blocked_methods':{'gan':'artifact'}}
            (directory/'drafts/face.json').write_text(json.dumps(row))
            review=server.Review(directory)
            request={'key':'face','spec_sha256':'primary','decision':'approved','method':'geometry','portrait':'S03','selected_spec_sha256':'stale'}
            with self.assertRaisesRegex(ValueError,'当前版本'):review.save(request)
            request.update(method='gan',selected_spec_sha256='bad')
            with self.assertRaisesRegex(ValueError,'失败'):review.save(request)
            request.update(method='geometry',selected_spec_sha256='geo')
            saved=review.save(request)
            self.assertEqual(saved['method'],'geometry')
            self.assertEqual(saved['selected_spec_sha256'],'geo')
            row['variants']['geometry']['spec_sha256']='new-geometry'
            (directory/'drafts/face.json').write_text(json.dumps(row))
            item=server.Review(directory).data()['rows'][0]
            self.assertEqual(item['review'],{})
            self.assertEqual(item['previous_review']['selected_spec_sha256'],'geo')

    def test_tenor_uses_literal_state_and_rejects_unexpected_media_hosts(self):
        collect=module('tenor_collect','tools/collect/collect_tenor_faces.py')
        parser=collect.State();parser.feed('<script>throw Error("never run")</script><script id="store-cache">{"x":1}</script>')
        self.assertEqual(json.loads(''.join(parser.parts)),{'x':1})
        with self.assertRaisesRegex(ValueError,'host'):collect.get('https://attacker.example/face.gif',100)

    def test_measured_pose_keys_cover_loop_and_action_curves_are_bounded(self):
        import numpy as np
        author=module('tenor_author','tools/collect/author_tenor_faces.py')
        brief={'box':[10,10,50,50],'eyes':[[25,25],[45,25]],'action':'blink',
               'action_keys':[[0,0],[1,1],[2,0]],'pose_keys':[{'frame':0,'eyes':[[25,25],[45,25]]},
               {'frame':2,'eyes':[[29,25],[49,25]]}]}
        rows=author.track([np.zeros((80,80,3),np.uint8)]*3,brief)
        np.testing.assert_allclose(rows[1][1],[[27,25],[47,25]])
        self.assertTrue(all(0<=value<=1 for value in author.actions(brief,1)))
        self.assertNotEqual(author.actions(brief,0),author.actions(brief,1))
        brief['pose_keys'][-1]['frame']=1
        with self.assertRaisesRegex(ValueError,'complete loop'):author.track([np.zeros((80,80,3),np.uint8)]*3,brief)

    def test_withdrawal_revokes_previous_approval_without_destroying_history(self):
        server=module('expansion_withdrawn','tools/qa/serve_expansion_review.py')
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp);(directory/'drafts').mkdir()
            records={'a':{'decision':'approved','spec_sha256':'v1'}}
            (directory/'reviews.json').write_text(json.dumps({'records':records}))
            (directory/'withdrawal.json').write_text(json.dumps({'status':'withdrawn'}))
            review=server.Review(directory)
            self.assertEqual(review.data()['rows'],[])
            self.assertEqual(review.data()['records'],records)
            with self.assertRaisesRegex(ValueError,'撤销'):
                review.save({'key':'a','spec_sha256':'v1','decision':'approved'})
            self.assertEqual(json.loads((directory/'reviews.json').read_text())['records'],records)

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
