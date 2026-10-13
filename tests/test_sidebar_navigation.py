"""Navigation layout and local-model selection regression tests."""
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from localmoestudio.gui_v2 import LocalMoEStudio


@unittest.skipIf(sys.platform != 'win32' and not os.environ.get('DISPLAY'),
                 'A Tk desktop display is required')
class SidebarNavigationTests(unittest.TestCase):
    def test_chat_and_model_submenus_are_accessible(self):
        w = LocalMoEStudio()
        try:
            w.navigate('chat')
            w.update_idletasks()
            self.assertTrue(w.sidebar_new_chat.winfo_ismapped())
            self.assertTrue(w.sidebar_model_combo.winfo_ismapped())
            self.assertEqual(w.perf_panel.winfo_parent(), str(w.sidebar_shell))
            w._new_chat_from_sidebar()
            w.update_idletasks()
            self.assertTrue(w.views['chat'].winfo_ismapped())
            w.sidebar_model_paths = {'Qwen Test': '/tmp/Qwen_Test.gguf'}
            w.sidebar_model_combo.configure(values=['Qwen Test'])
            w.sidebar_model_choice.set('Qwen Test')
            w._sidebar_choose_model()
            self.assertEqual(w.vars['model'].get(), '/tmp/Qwen_Test.gguf')
        finally:
            w.destroy()

    def test_performance_metrics_are_in_sidebar(self):
        w = LocalMoEStudio()
        try:
            self.assertEqual(set(w.perf_vars),
                             {'speed', 'ttft', 'tokens', 'elapsed', 'vram', 'ram'})
            w._on_performance_update({
                'active': False, 'generation_tok_s': 8.1, 'source': 'server',
                'ttft_s': 2.1, 'completion_tokens': 120, 'elapsed_s': 18.5})
            self.assertEqual(w.perf_vars['speed'].get(), '8.10 tok/s')
            w._on_performance_hardware({
                'gpu_used_mib': 3072, 'gpu_total_mib': 6144,
                'ram_used_gib': 30., 'ram_total_gib': 64.})
            self.assertEqual(w.perf_vars['vram'].get(), '3.0/6.0 GiB')
        finally:
            w.destroy()
