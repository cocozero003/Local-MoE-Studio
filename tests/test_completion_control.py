"""Output-length and continuation behavior, tested without an actual GPU."""
import io
import json
import queue
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from localmoestudio.backend import Application
from localmoestudio.completion_control import (
    finish_reason, wants_auto_continue, append_answer, continuation_messages,
    MAX_AUTO_EXTRA_REQUESTS,
)
from localmoestudio.performance import GenerationMetrics
from localmoestudio.sessions import SessionStore


class FakeVar:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class FakeResponse:
    def __init__(self, chunks):
        self.chunks = chunks

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def __iter__(self):
        for chunk in self.chunks:
            yield b'data: ' + json.dumps(chunk).encode('utf-8') + b'\n'
        yield b'data: [DONE]\n'


def streamed_reply(content, reason):
    return FakeResponse([
        {'choices': [{'delta': {'content': content}, 'finish_reason': None}]},
        {'choices': [{'delta': {}, 'finish_reason': reason}],
         'usage': {'completion_tokens': max(1, len(content) // 3)}},
    ])


class HelpersTests(unittest.TestCase):
    def test_finish_reason_distinguishes_length_and_stop(self):
        self.assertEqual(finish_reason({'choices': [{'finish_reason': 'length'}]}), 'length')
        self.assertEqual(finish_reason({'choices': [{'finish_reason': 'stop'}]}), 'stop')
        self.assertIsNone(finish_reason({'choices': []}))
        self.assertIsNone(finish_reason({'choices': [{'delta': {'content': 'hi'}}]}))

    def test_bounded_auto_continuation(self):
        for i in range(MAX_AUTO_EXTRA_REQUESTS):
            self.assertTrue(wants_auto_continue('length', True, i))
        self.assertFalse(wants_auto_continue('length', True, MAX_AUTO_EXTRA_REQUESTS))
        self.assertFalse(wants_auto_continue('stop', True, 0))
        self.assertFalse(wants_auto_continue('length', False, 0))
        self.assertFalse(wants_auto_continue(None, True, 0))

    def test_accumulation_preserves_text_without_duplicate_overlap(self):
        self.assertEqual(append_answer('A complete paragraph.', ' Next section'),
                         'A complete paragraph. Next section')
        self.assertEqual(append_answer('A long partial sentence', 'partial sentence continues'),
                         'A long partial sentence continues')
        dialog = [{'role': 'user', 'content': 'question'}]
        followup = continuation_messages(dialog, 'first part')
        self.assertEqual(followup[-2], {'role': 'assistant', 'content': 'first part'})
        self.assertEqual(followup[-1]['role'], 'user')


class GenerationTests(unittest.TestCase):
    def run_case(self, replies, auto):
        class SimulatedApp:
            def __init__(self):
                self.events = queue.Queue()
                self.metrics = GenerationMetrics('test.gguf')
                self.vars = {'auto_continue': FakeVar(auto)}

            def endpoint(self, route):
                return 'http://127.0.0.1:8081' + route

        app = SimulatedApp()
        requests = []

        def fake_open(req, timeout):
            body = json.loads(req.data)
            requests.append(body)
            return replies[len(requests) - 1]

        with patch('urllib.request.urlopen', side_effect=fake_open):
            Application.chat_request(app, 'test question',
                                     [{'role': 'user', 'content': 'test question'}], 0.7, 5)
        return requests, list(app.events.queue)

    def test_full_finish_does_not_repeat(self):
        requests, events = self.run_case([streamed_reply('Complete answer.', 'stop')], True)
        self.assertEqual(len(requests), 1)
        info = next(d for k, d in events if k == 'chat_finish_state')
        self.assertEqual(info['reason'], 'stop')
        self.assertEqual(next(d for k, d in events if k == 'chat_done')[1], 'Complete answer.')

    def test_limit_causes_automatic_bounded_continuation(self):
        requests, events = self.run_case([
            streamed_reply('First part.', 'length'),
            streamed_reply(' Second part.', 'length'),
            streamed_reply(' Third part.', 'stop'),
        ], True)
        self.assertEqual(len(requests), 3)
        self.assertEqual(len([k for k, _ in events if k == 'chat_continuing']), 2)
        self.assertEqual(next(d for k, d in events if k == 'chat_done')[1],
                         'First part. Second part. Third part.')
        self.assertEqual(next(d for k, d in events if k == 'chat_finish_state')['reason'], 'stop')
        self.assertEqual(requests[1]['messages'][-2]['role'], 'assistant')
        self.assertEqual(requests[1]['messages'][-1]['role'], 'user')

    def test_limit_stops_after_budget_and_offers_continue(self):
        requests, events = self.run_case([
            streamed_reply('part one', 'length'),
            streamed_reply('part two', 'length'),
            streamed_reply('part three', 'length'),
        ], True)
        self.assertEqual(len(requests), 3)
        state = next(d for k, d in events if k == 'chat_finish_state')
        self.assertEqual(state['reason'], 'length')
        self.assertEqual(state['segments'], 3)

    def test_disabled_auto_mode_stays_single_request(self):
        requests, events = self.run_case([streamed_reply('incomplete', 'length')], False)
        self.assertEqual(len(requests), 1)
        self.assertEqual(next(d for k, d in events if k == 'chat_finish_state')['reason'], 'length')

    def test_no_finish_reason_is_not_called_complete(self):
        requests, events = self.run_case([streamed_reply('unknown', None)], True)
        self.assertEqual(len(requests), 1)
        self.assertEqual(next(d for k, d in events if k == 'chat_finish_state')['reason'], 'unknown')


class PersistenceTests(unittest.TestCase):
    def test_continue_updates_last_assistant_without_new_pair(self):
        with tempfile.TemporaryDirectory() as directory:
            sessions = SessionStore(Path(directory))
            sid = sessions.create()
            sessions.append_pair(sid, 'Question', 'First sentence.')
            sessions.extend_last_assistant(sid, ' Second sentence.')
            record = sessions.read(sid)
            self.assertEqual(len(record['messages']), 2)
            self.assertEqual(record['messages'][-1]['content'],
                             'First sentence. Second sentence.')
            self.assertEqual(record['title'], 'Question')
            with self.assertRaises(ValueError):
                empty_sid = sessions.create()
                sessions.extend_last_assistant(empty_sid, 'Orphaned continuation')


if __name__ == '__main__':
    unittest.main()
