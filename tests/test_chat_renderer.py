"""Tests for minimal user bubbles and Markdown-rich assistant replies."""
import os
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from localmoestudio.chat_renderer import parse_table


class MarkdownTests(unittest.TestCase):
    def test_table_rows_and_separator(self):
        sample = ["| Model | GB |", "| --- | ---: |", "| Qwen | 18.6 |"]
        self.assertEqual(parse_table(sample), (['Model','GB'], [['Qwen','18.6']]))

    def test_malformed_table_falls_back(self):
        self.assertIsNone(parse_table(['| A | B |', '| not a divider | x |']))


@unittest.skipIf(sys.platform != 'win32' and not os.environ.get('DISPLAY'),
                 'Tk display unavailable in headless CI')
class RendererTests(unittest.TestCase):
    def test_reopen_saved_chat_and_new_chat(self):
        from unittest.mock import patch
        from localmoestudio.app import LocalMoEStudio
        with patch.object(LocalMoEStudio, '_schedule_hardware', return_value=None), \
             patch.object(LocalMoEStudio, 'refresh_catalog', return_value=None):
            app = LocalMoEStudio()
            try:
                app.history = [
                    {'role': 'user', 'content': 'Compare local models'},
                    {'role': 'assistant', 'content': (
                        '## Recommended models\n\n| Model | RAM |\n| --- | --- |\n'
                        '| Qwen | 64 GB |\n\nChoose a model.')},
                ]
                app._render_history()
                app.update_idletasks()
                self.assertIn('Recommended models', app.transcript.get('1.0', 'end'))
                self.assertNotIn('ASSISTANT', app.transcript.get('1.0', 'end'))
                self.assertEqual(len(app._chat_bubbles), 1)
                self.assertEqual(len(app._chat_widgets), 2)
                app._begin_chat_request_ui('What else?')
                app._append_assistant_token('One more option.')
                app.history.extend([
                    {'role': 'user', 'content': 'What else?'},
                    {'role': 'assistant', 'content': 'One more option.'},
                ])
                app._finalize_chat_ui()
                self.assertIn('One more option.', app.transcript.get('1.0', 'end'))
                self.assertEqual(len(app._chat_bubbles), 2)
                app.new_chat()
                self.assertEqual(len(app._chat_widgets), 0)
                self.assertEqual(len(app.history), 0)
            finally:
                app.destroy()

if __name__ == '__main__':
    unittest.main()