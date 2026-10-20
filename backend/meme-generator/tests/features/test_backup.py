from pathlib import Path
import sqlite3
import stat
import tempfile
import unittest
from meme_generator.features.backup import snapshot, verify


class BackupTests(unittest.TestCase):
    def test_snapshot_preserves_external_target_permissions_and_sqlite(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / "source"
            source.mkdir()
            external = base / "executable"
            external.write_text("test")
            external.chmod(0o755)
            (source / "external-link").symlink_to(external)
            db = sqlite3.connect(source / "state.sqlite3")
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE sample(value TEXT)")
            db.execute("INSERT INTO sample VALUES('retained')")
            db.commit()
            output = base / "backup"
            snapshot(source, output)
            self.assertEqual(stat.S_IMODE(external.stat().st_mode), 0o755)
            self.assertTrue((output / "state/external-link").is_symlink())
            self.assertEqual(verify(output)["status"], "passed")
            copied = sqlite3.connect(output / "state/state.sqlite3")
            self.assertEqual(
                copied.execute("SELECT value FROM sample").fetchone()[0], "retained"
            )
            copied.close()
            db.close()
            (output / "state/state.sqlite3").write_bytes(b"corrupt")
            self.assertEqual(verify(output)["status"], "failed")

    def test_snapshot_refuses_destination_inside_source_or_existing_link(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "source"
            source.mkdir()
            with self.assertRaises(ValueError):
                snapshot(source, source / "nested")
            linked = Path(temp) / "linked"
            linked.symlink_to(source)
            with self.assertRaises(ValueError):
                snapshot(source, linked)
