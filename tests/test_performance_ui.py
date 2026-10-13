"""Tk regression: performance strip and composer remain visible together."""
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from localmoestudio.gui_v2 import LocalMoEStudio

@unittest.skipIf(sys.platform != 'win32' and not os.environ.get('DISPLAY'), 'No graphical display')
class PerfUITests(unittest.TestCase):
    def test_dashboard_stays_visible_on_small_laptop_window(self):
        for scale in (1.,1.5,2.):
            with self.subTest(scale=scale):
                w=LocalMoEStudio()
                try:
                    w.tk.call('tk','scaling',scale)
                    w.geometry('990x720')
                    w.navigate('chat')
                    w.update()
                    self.assertTrue(w.perf_panel.winfo_ismapped())
                    self.assertGreater(w.perf_panel.winfo_height(),30)
                    self.assertGreater(w.prompt.winfo_height(),30)
                    self.assertLessEqual(w.compose_shell.winfo_rooty()+w.compose_shell.winfo_height(),w.winfo_rooty()+w.winfo_height())
                    w._on_performance_update({'active':False,'generation_tok_s':8.7,'source':'server','ttft_s':1.25,'completion_tokens':100,'elapsed_s':15.})
                    self.assertEqual(w.perf_vars['speed'].get(),'8.70 tok/s')
                    w._on_performance_hardware({'gpu_used_mib':3072,'gpu_total_mib':6144,'ram_used_gib':28.5,'ram_total_gib':64})
                    self.assertIn('3.0/6.0',w.perf_vars['vram'].get())
                finally:w.destroy()
