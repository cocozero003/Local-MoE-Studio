"""Tests for the installed GGUF library."""
import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from localmoestudio.local_library import list_installed_models


class InstalledModelTests(unittest.TestCase):
    def test_nested_repositories_and_partials(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            p = root / 'Qwen__Qwen3' / 'Qwen3-Q4_K_M.gguf'
            p.parent.mkdir()
            p.write_bytes(b'GGUF' + b'0' * 24)
            (root / 'gemma.gguf').write_bytes(b'GGUF')
            (root / 'incomplete.gguf.part').write_bytes(b'fake')
            got = list_installed_models(root)
            self.assertEqual(len(got), 2)
            self.assertTrue(all(item['complete'] for item in got))

    def test_external_and_deduplicate(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            p = root / 'external.gguf'
            p.write_bytes(b'GGUF')
            self.assertEqual(len(list_installed_models(root, p)), 1)
            self.assertEqual(len(list_installed_models(root / 'absent', p)), 1)

    def test_missing_shard_is_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / 'model-00001-of-00003.gguf').write_bytes(b'GGUF')
            (root / 'model-00002-of-00003.gguf').write_bytes(b'GGUF')
            self.assertFalse(list_installed_models(root)[0]['complete'])
            (root / 'model-00003-of-00003.gguf').write_bytes(b'GGUF')
            self.assertTrue(list_installed_models(root)[0]['complete'])

    def test_empty_model_excluded(self):
        with tempfile.TemporaryDirectory() as d:
            Path(d, 'empty.gguf').touch()
            self.assertFalse(list_installed_models(d))
