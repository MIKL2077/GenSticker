import unittest
from unittest.mock import patch
from meme_generator.features.render_cache import RenderCache


class RenderCacheTests(unittest.TestCase):
    def test_size_scope_and_expiry(self):
        cache=RenderCache(max_bytes=8,max_entries=2,ttl=3)
        with patch('meme_generator.features.render_cache.time.monotonic',return_value=0):
            cache.put('actor-a:input',b'1234');cache.put('actor-b:input',b'5678')
            self.assertIsNone(cache.get('actor-c:input'))
            self.assertEqual(cache.get('actor-a:input'),b'1234')
            cache.put('another',b'xxxx')
            self.assertIsNone(cache.get('actor-b:input'))
            self.assertLessEqual(cache.bytes,8)
        with patch('meme_generator.features.render_cache.time.monotonic',return_value=4):
            self.assertIsNone(cache.get('actor-a:input'));self.assertEqual(cache.bytes,0)


if __name__=='__main__':unittest.main()
