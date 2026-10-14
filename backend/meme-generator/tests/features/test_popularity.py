import os
import tempfile
import unittest
from unittest.mock import patch
from meme_generator.features.store import connect
from meme_generator.features.popularity import record, snapshot, maintenance


class PopularityTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'GENSTICKER_STATE_DIR': self.directory.name})
        self.env.start()
        db = connect()
        with db:
            db.execute("INSERT INTO templates VALUES('id','test',1,'hash','{}',NULL,'published')")
        db.close()

    def tearDown(self):
        self.env.stop()
        self.directory.cleanup()

    def test_replays_and_success_counts(self):
        self.assertTrue(record('test', 'user:a', 'click'))
        self.assertFalse(record('test', 'user:a', 'click'))
        self.assertTrue(record('test', 'user:b', 'click'))
        for _ in range(2):
            self.assertTrue(record('test', 'user:a', 'generate'))
        self.assertTrue(record('test', 'user:a', 'ai_generate', dedup='job:0'))
        self.assertFalse(record('test', 'user:a', 'ai_generate', dedup='job:0'))
        stats = snapshot()['test']
        self.assertEqual(stats['counts']['click'], 2)
        self.assertEqual(stats['counts']['generate'], 2)
        self.assertEqual(stats['counts']['ai_generate'], 1)
        self.assertGreater(stats['heat'], 0)
        self.assertFalse(record('unknown', 'user:a', 'click'))

    def test_retention_keeps_aggregates(self):
        record('test', 'user:a', 'favorite')
        db = connect()
        with db:
            db.execute('UPDATE popularity_seen SET created=0')
            db.execute("UPDATE popularity_daily SET day='2000-01-01'")
            maintenance(db)
        self.assertEqual(db.execute('SELECT COUNT(*) FROM popularity_seen').fetchone()[0], 0)
        self.assertEqual(db.execute('SELECT COUNT(*) FROM popularity_daily').fetchone()[0], 0)
        self.assertEqual(db.execute('SELECT count FROM popularity_totals').fetchone()[0], 1)
        db.close()


if __name__ == '__main__':
    unittest.main()
