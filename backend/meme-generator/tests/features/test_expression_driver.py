import hashlib
import os
from pathlib import Path
import tempfile
import threading
import time
import types
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import numpy as np
from PIL import Image
from pydantic import ValidationError

from meme_generator.features import expression_driver as driver, expression_runtime as rt
from meme_generator.features.declarative import ExpressionDriver, ExpressionRecipe
from tests.features.test_expression_fusion import recipe


def configuration(method='ganimation-emotionnet-v1', intensity=0):
    return ExpressionDriver(method=method, aus=[intensity] * 17)


class ExpressionDriverTests(unittest.TestCase):
    def tearDown(self):
        driver.close()

    def test_only_bounded_reviewed_protocols_are_accepted(self):
        for value in [configuration().model_dump() | {'aus': [0] * 16},
                      {'method': 'https://model.example', 'aus': [0] * 17},
                      {'method': 'geometry-v1', 'aus': [float('nan')] * 17},
                      {'method': 'geometry-v1', 'aus': [1.01] * 17},
                      {'method': 'geometry-v1', 'aus': [0] * 17, 'model': '/tmp/other.onnx'}]:
            with self.assertRaises(ValidationError):
                ExpressionDriver.model_validate(value)
        with self.assertRaises(ValidationError):
            ExpressionRecipe.model_validate(recipe() | {'driver': configuration().model_dump(), 'controls': {}})

    def test_model_integrity_is_checked_before_loading_any_runtime(self):
        with tempfile.TemporaryDirectory() as folder:
            model = Path(folder) / 'bad.onnx'
            model.write_bytes(b'not the reviewed model')
            with patch.dict(os.environ, {'GENSTICKER_EXPRESSION_DRIVER_MODEL': str(model)}):
                with self.assertRaisesRegex(ValueError, 'checksum'):
                    driver.warmup()
            model.unlink()
            with patch.dict(os.environ, {'GENSTICKER_EXPRESSION_DRIVER_MODEL': str(model)}):
                self.assertFalse(driver.warmup())

    def test_cpu_session_is_single_threaded_and_reused(self):
        class Options:
            def add_session_config_entry(self, key, value):
                self.entry = (key, value)
        calls = []
        sentinel = object()
        def create(path, options, providers):
            calls.append((options, providers))
            return sentinel
        fake = types.SimpleNamespace(SessionOptions=Options,
                                     ExecutionMode=types.SimpleNamespace(ORT_SEQUENTIAL=7),
                                     InferenceSession=create)
        with tempfile.TemporaryDirectory() as folder:
            model = Path(folder) / 'test.onnx'
            model.write_bytes(b'approved fixture')
            with patch.dict(os.environ, {'GENSTICKER_EXPRESSION_DRIVER_MODEL': str(model)}), \
                    patch.object(driver, 'MODEL_SHA256', hashlib.sha256(model.read_bytes()).hexdigest()), \
                    patch.dict('sys.modules', {'onnxruntime': fake}):
                self.assertTrue(driver.warmup())
                self.assertTrue(driver.warmup())
        self.assertEqual(len(calls), 1)
        options, providers = calls[0]
        self.assertEqual((options.intra_op_num_threads, options.inter_op_num_threads), (1, 1))
        self.assertEqual(providers, ['CPUExecutionProvider'])
        self.assertEqual(options.entry, ('session.intra_op.allow_spinning', '0'))

    def test_action_cache_is_request_scoped_and_shared_inference_is_serialized(self):
        state = {'calls': 0, 'active': 0, 'peak': 0}
        class Session:
            def run(self, *args):
                state['calls'] += 1
                state['active'] += 1
                state['peak'] = max(state['peak'], state['active'])
                time.sleep(.01)
                state['active'] -= 1
                return [np.zeros((1, 3, 128, 128), np.float32)]
        portrait = {'rgb': np.zeros((128, 128, 3), np.uint8)}
        cache = {}
        with patch.object(driver, '_session', Session()), patch.object(driver, 'align', return_value=portrait), \
                patch.object(driver, 'paste', side_effect=lambda rgb, *_: rgb):
            with ThreadPoolExecutor(max_workers=2) as executor:
                calls = [executor.submit(driver.render_frame, {}, {}, configuration(), cache, 0) for _ in range(2)]
                for call in calls:
                    call.result()
            self.assertEqual(state['calls'], 1)
            driver.render_frame({}, {}, configuration(intensity=.5), cache, 0)
            driver.render_frame({}, {}, configuration(), {}, 0)
        self.assertEqual(state['calls'], 3)
        self.assertEqual(state['peak'], 1)

    def test_invalid_outputs_and_inverted_meshes_do_not_escape(self):
        class Session:
            def run(self, *args):
                return [np.full((1, 3, 128, 128), np.nan, np.float32)]
        with patch.object(driver, '_session', Session()), \
                patch.object(driver, 'align', return_value={'rgb': np.zeros((128, 128, 3), np.uint8)}):
            with self.assertRaisesRegex(ValueError, 'model output'):
                driver.render_frame({}, {}, configuration(), {}, 0)
        pixels = np.zeros((128, 128, 3), np.uint8)
        points = np.zeros((478, 2), np.float32)
        with patch.object(driver.m, 'warp', return_value=(pixels, np.ones((128, 128), np.float32), 1)):
            with self.assertRaisesRegex(ValueError, 'folded'):
                driver.deform(pixels, points, points)

    def test_missing_model_keeps_existing_slot_fallback_and_old_recipes_keep_old_math(self):
        canvas = Image.new('RGBA', (64, 64), 'white')
        guide = {'base': np.zeros((64, 64, 3), np.uint8), 'mask': np.ones((64, 64), np.uint8) * 255}
        cache = {}
        with patch.object(rt, 'prepare', return_value={}), patch.object(rt, 'guide', return_value=guide), \
                patch.object(driver, 'render_frame', return_value=None), \
                patch.object(rt.math, 'render_frame', return_value=(canvas.convert('RGB'), {})) as old:
            self.assertFalse(rt.composite(canvas, canvas, ExpressionRecipe.model_validate(recipe() | {'driver': configuration().model_dump()}), 0, cache))
            self.assertEqual(cache['expression_stats'][0]['reason'], 'expression_driver_unavailable')
            self.assertTrue(rt.composite(canvas, canvas, ExpressionRecipe.model_validate(recipe()), 0, cache))
            self.assertEqual(old.call_count, 1)


if __name__ == '__main__':
    unittest.main()
