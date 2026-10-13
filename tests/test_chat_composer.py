"""Chat composer must stay visible at normal and high-DPI window sizes."""
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from localmoestudio.gui_v2 import LocalMoEStudio


@unittest.skipIf(sys.platform != 'win32' and not os.environ.get('DISPLAY'),
                 'A Tk graphical display is required')
class ChatComposerLayoutTests(unittest.TestCase):
    def test_message_entry_visible_when_resizing(self):
        for scale in (1.0, 1.5, 2.0):
            with self.subTest(scaling=scale):
                window = LocalMoEStudio()
                try:
                    window.tk.call('tk', 'scaling', scale)
                    window.geometry('1000x680')
                    window.navigate('chat')
                    window.update()
                    self.assertGreater(window.prompt.winfo_height(), 40)
                    self.assertGreater(window.transcript.winfo_height(), 120)
                    self.assertGreater(window.chat_send_button.winfo_height(), 20)
                    self.assertLessEqual(
                        window.compose_shell.winfo_rooty() + window.compose_shell.winfo_height(),
                        window.winfo_rooty() + window.winfo_height() - 5)
                finally:
                    window.destroy()

    def test_keyboard_shortcuts(self):
        window = LocalMoEStudio()
        try:
            class Event:
                state = 0
            sent = []
            window.send_message = lambda: sent.append(True)
            self.assertEqual(window._composer_enter(Event()), 'break')
            Event.state = 1
            self.assertIsNone(window._composer_enter(Event()))
            self.assertEqual(len(sent), 1)
        finally:
            window.destroy()


if __name__ == '__main__':
    unittest.main()
