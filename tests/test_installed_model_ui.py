"""GUI regression: select an existing GGUF directly in Local MoE Studio."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from localmoestudio.app import LocalMoEStudio


class InstalledModelUITests(unittest.TestCase):
    @unittest.skipIf(sys.platform != 'win32' and not os.environ.get('DISPLAY'),
                     'Tk display required')
    def test_select_downloaded_gguf_in_app(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            model = root / 'models' / 'Qwen__Demo' / 'Qwen3-Q4_K_M.gguf'
            model.parent.mkdir(parents=True)
            model.write_bytes(b'GGUF' + b'0' * 32)
            with patch('localmoestudio.app.USER_DATA', root), \
                 patch('localmoestudio.app.LocalMoEStudio._schedule_hardware', return_value=None), \
                 patch('localmoestudio.app.LocalMoEStudio.refresh_catalog', return_value=None):
                window = LocalMoEStudio()
                try:
                    window.update_idletasks()
                    window.refresh_installed_models()
                    self.assertEqual(len(window.installed_paths), 1)
                    window.installed_tree.selection_set('0')
                    window.use_installed_model()
                    self.assertTrue(Path(window.vars['model'].get()).samefile(model))
                    self.assertEqual(window.model_name.cget('text'), model.name)
                finally:
                    window.destroy()
