"""Regression checks for the visible Stop model buttons on Windows."""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from localmoestudio.app import LocalMoEStudio


class StopModelUITests(unittest.TestCase):
    @unittest.skipIf(sys.platform != 'win32' and not os.environ.get('DISPLAY'),
                     'Desktop Tk environment is unavailable')
    def test_stop_buttons_appear_and_track_managed_process(self):
        with patch.object(LocalMoEStudio, '_schedule_hardware', return_value=None), \
             patch.object(LocalMoEStudio, 'refresh_catalog', return_value=None):
            window = LocalMoEStudio()
            try:
                window.update_idletasks()
                self.assertTrue(window.sidebar_stop_button.winfo_exists())
                self.assertTrue(window.settings_stop_button.winfo_exists())
                window.process = None
                window._refresh_runner_controls()
                self.assertEqual(str(window.sidebar_stop_button.cget('state')), 'disabled')
                self.assertEqual(str(window.settings_stop_button.cget('state')), 'disabled')
                fake_proc = Mock()
                fake_proc.poll.return_value = None
                window.process = fake_proc
                window._refresh_runner_controls()
                self.assertEqual(str(window.sidebar_stop_button.cget('state')), 'normal')
                self.assertEqual(str(window.settings_stop_button.cget('state')), 'normal')
                with patch.object(window, 'stop_server', return_value=None) as stop:
                    self.assertTrue(window._stop_model_from_ui())
                    stop.assert_called_once_with()
            finally:
                window.process = None
                window.destroy()

    @unittest.skipIf(sys.platform != 'win32' and not os.environ.get('DISPLAY'),
                     'Desktop Tk environment is unavailable')
    def test_preset_offers_to_stop_running_model(self):
        with patch.object(LocalMoEStudio, '_schedule_hardware', return_value=None), \
             patch.object(LocalMoEStudio, 'refresh_catalog', return_value=None):
            window = LocalMoEStudio()
            try:
                proc = Mock()
                proc.poll.return_value = None
                window.process = proc
                window.profile_choice.set('Large MoE (low VRAM)')
                with patch('localmoestudio.app.messagebox.askyesno', return_value=True), \
                     patch('localmoestudio.app.messagebox.showinfo'), \
                     patch.object(window, 'stop_server') as stop, \
                     patch.object(window, 'save_settings'):
                    window._apply_easy_profile()
                    stop.assert_called_once_with()
                    self.assertEqual(window.vars['moe'].get(), 'all')
            finally:
                window.process = None
                window.destroy()


if __name__ == '__main__':
    unittest.main()
