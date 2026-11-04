import hashlib
from io import BytesIO
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from PIL import Image

from meme_generator.features.store import connect, root
from meme_generator.features.template_examples import example_response


class TemplateExampleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'GENSTICKER_STATE_DIR': self.temp.name})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def declared(self, status='published'):
        output = BytesIO()
        Image.new('RGB', (320, 240), 'red').save(output, 'GIF', save_all=True,
            append_images=[Image.new('RGB', (320, 240), 'blue')], duration=[80, 120], loop=0)
        raw = output.getvalue()
        digest = hashlib.sha256(raw).hexdigest()
        folder = root() / 'template_assets'
        folder.mkdir()
        (folder / (digest + '.gif')).write_bytes(raw)
        spec = {'width': 320, 'height': 240, 'frames': [
            {'asset': digest, 'asset_format': 'gif', 'source_index': i, 'duration_ms': ms,
             'layers': []} for i, ms in enumerate([80, 120])]}
        db = connect()
        with db:
            db.execute('INSERT INTO templates VALUES(?,?,?,?,?,?,?)',
                ('id', 'auto_example', 1, 'fingerprint', '{}', json.dumps(spec), status))
        db.close()
        return raw

    def test_original_dimensions_all_frames_timing_and_loop(self):
        self.declared()
        response = example_response('auto_example')
        self.assertEqual(response.media_type, 'image/gif')
        with Image.open(BytesIO(response.body)) as image:
            self.assertEqual(image.size, (320, 240))
            self.assertEqual(image.n_frames, 2)
            self.assertEqual(image.info['loop'], 0)
            timings = []
            for i in range(image.n_frames):
                image.seek(i)
                timings.append(image.info['duration'])
            self.assertEqual(timings, [80, 120])

    def test_withdrawn_and_blocked_examples_cannot_use_stale_registry(self):
        self.declared('withdrawn')
        with patch('meme_generator.features.template_examples.get_meme') as registry:
            with self.assertRaises(HTTPException) as error:
                example_response('auto_example')
            self.assertEqual(error.exception.status_code, 404)
            registry.assert_not_called()
        db = connect()
        with db:
            db.execute("UPDATE templates SET status='published'")
            db.execute('INSERT INTO template_blocks VALUES(?,?,?)', ('auto_example', 'test', 0))
        db.close()
        with self.assertRaises(HTTPException) as error:
            example_response('auto_example')
        self.assertEqual(error.exception.status_code, 404)


if __name__ == '__main__':
    unittest.main()
