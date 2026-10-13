"""Regression tests for WinError 32 engine updates.

An engine running on Windows owns DLL file handles, so old installation
directories must never be renamed or removed during an update.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from localmoestudio.engine_installer import publish_engine_version


class EnginePublishingTests(unittest.TestCase):
    def test_older_running_installation_is_never_renamed(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            previous = base / 'llama.cpp-cuda12'
            previous.mkdir()
            (previous / 'llama-server.exe').write_bytes(b'old runnable binary')
            (previous / 'ggml-cuda.dll').write_bytes(b'old DLL')
            staged = base / 'staging'
            staged.mkdir()
            (staged / 'llama-server.exe').write_bytes(b'new executable')
            path = publish_engine_version(staged, base, 'cuda12', 'b11580')
            self.assertEqual(Path(path).name, 'llama-server.exe')
            self.assertTrue((base / 'llama.cpp-cuda12-b11580' / 'llama-server.exe').is_file())
            self.assertEqual((previous / 'llama-server.exe').read_bytes(), b'old runnable binary')
            self.assertEqual((previous / 'ggml-cuda.dll').read_bytes(), b'old DLL')
            self.assertFalse(staged.exists())

    def test_existing_matching_version_is_reused_without_overwriting(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d)
            old=base / 'llama.cpp-cuda12-b11580'
            old.mkdir()
            (old / 'llama-server.exe').write_bytes(b'installed')
            staged=base / 'new-staging'
            staged.mkdir()
            (staged / 'llama-server.exe').write_bytes(b'other')
            path=publish_engine_version(staged,base,'cuda12','b11580')
            self.assertEqual(Path(path),old/'llama-server.exe')
            self.assertEqual((old/'llama-server.exe').read_bytes(),b'installed')
            self.assertTrue(staged.exists())

    def test_incomplete_existing_version_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d)
            bad=base / 'llama.cpp-cuda12-b11580'
            bad.mkdir()
            staged=base / 'staging'
            staged.mkdir()
            (staged / 'llama-server.exe').write_bytes(b'new')
            with self.assertRaisesRegex(IOError, 'incomplete engine'):
                publish_engine_version(staged,base,'cuda12','b11580')
            self.assertFalse((bad / 'llama-server.exe').exists())

    def test_untrusted_tag_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d)
            staged=base / 'staging'
            staged.mkdir()
            (staged / 'llama-server.exe').write_bytes(b'new')
            for tag in ('../escape','bad/slash','', 'a'*82):
                with self.subTest(tag=tag):
                    with self.assertRaises(ValueError):
                        publish_engine_version(staged,base,'cuda12',tag)


if __name__ == '__main__':
    unittest.main()
