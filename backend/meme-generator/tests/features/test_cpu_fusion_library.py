import base64
from collections import Counter
import hashlib
import json
from pathlib import Path
import unittest
from meme_generator.features.element_templates import validate_elements
from meme_generator.features.storage import asset_refs


class FusionLibraryTests(unittest.TestCase):
    def test_every_current_template_has_a_disposition_and_enabled_recipes_are_bound(self):
        project=Path(__file__).resolve().parents[4]
        audit=json.loads((project/'docs/template-audit/20261027-compositing.json').read_text())
        rows=audit['records'];self.assertEqual(len(rows),958)
        self.assertEqual(len({r['key'] for r in rows}),len(rows))
        self.assertEqual(dict(Counter(r['decision'] for r in rows)),audit['counts'])
        enabled={r['key']:r for r in rows if r['decision']=='fusion'}
        features=Path(__file__).resolve().parents[2]/'meme_generator/features'
        actual={}
        for path in (features/'template_batches').glob('20261027-cpu-fusion-*.json'):
            batch=json.loads(path.read_text());self.assertLess(path.stat().st_size,32*1024*1024)
            for item in batch['templates']:
                validate_elements(item['spec'],item['metadata'])
                self.assertNotIn(item['key'],actual);actual[item['key']]=item
                self.assertEqual(item['version'],enabled[item['key']]['version'])
                self.assertEqual(item['metadata']['quality']['spec_sha256'],enabled[item['key']]['spec_sha256'])
                for digest in asset_refs(item['spec']):
                    raw=base64.b64decode(batch['assets'][digest],validate=True)
                    self.assertEqual(hashlib.sha256(raw).hexdigest(),digest)
                tampered={**item['metadata'],'quality':{**item['metadata']['quality'],'fusion_checked_frames':-1}}
                with self.assertRaises(ValueError):validate_elements(item['spec'],tampered)
        self.assertEqual(set(actual),set(enabled))


if __name__=='__main__':unittest.main()
