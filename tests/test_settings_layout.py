"""Regression test: Settings help text must remain visible at high DPI."""
import os
import sys
import tkinter as tk
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from localmoestudio.gui_v2 import LocalMoEStudio


class SettingsLayoutTests(unittest.TestCase):
    @unittest.skipIf(sys.platform != 'win32' and not os.environ.get('DISPLAY'),
                     'Tk display is unavailable in headless CI')
    def test_hint_labels_are_not_clipped_at_multiple_dpi_scales(self):
        for scale in (1.0, 1.5, 2.0):
            with self.subTest(scale=scale):
                root = tk.Tk()
                try:
                    root.tk.call('tk', 'scaling', scale)
                    root.geometry('960x720')
                    frame = tk.Frame(root)
                    frame.pack(fill='x', padx=20)
                    right = LocalMoEStudio._line(
                        None, frame, 'MoE expert placement',
                        'Disabled: GPU first with RAM overflow. All: every MoE expert stays in system RAM.')
                    tk.Entry(right).pack(fill='x', expand=True)
                    root.update_idletasks()
                    row = frame.winfo_children()[0]
                    left = row.grid_slaves(row=0, column=0)[0]
                    title, hint = left.winfo_children()
                    self.assertGreaterEqual(left.winfo_height(), title.winfo_height() + hint.winfo_height())
                    self.assertGreaterEqual(hint.winfo_height(), hint.winfo_reqheight())
                    self.assertGreaterEqual(row.winfo_height(), left.winfo_height())
                finally:
                    root.destroy()


if __name__ == '__main__':
    unittest.main()
