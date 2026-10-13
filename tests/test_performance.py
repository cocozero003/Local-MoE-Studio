"""Performance dashboard and streaming-accounting regression tests."""
import io
import json
import os
import queue
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from localmoestudio.performance import GenerationMetrics, append_history, read_history, sample_hardware, tokenize_output_count
from localmoestudio.backend import Application


class MetricsTests(unittest.TestCase):
    def test_server_timing_preferred_over_stream_chunk_count(self):
        perf = GenerationMetrics('demo.gguf', started_at=10)
        perf.ingest({'choices':[{'delta': {'content':'Hello there'}}]}, now=11)
        perf.ingest({'choices':[{'delta': {'content':' world'}}]}, now=11.2)
        perf.ingest({'timings': {'predicted_n':14,'predicted_per_second':8.75,
                                 'prompt_n':35,'prompt_per_second':46.4}}, now=11.5)
        data = perf.finish(now=12.5)
        self.assertEqual(data['source'], 'server')
        self.assertEqual(data['completion_tokens'], 14)
        self.assertEqual(data['fragments'], 2)
        self.assertEqual(data['generation_tok_s'], 8.75)
        self.assertEqual(data['ttft_s'], 1)
        self.assertEqual(data['prompt_tok_s'], 46.4)

    def test_no_false_token_claim_without_reported_usage(self):
        perf=GenerationMetrics('thai.gguf',started_at=0)
        perf.ingest({'choices':[{'delta':{'content':'สวัสดี ยินดีครับ'}}]},now=2)
        running=perf.snapshot(3)
        self.assertIsNone(running['generation_tok_s'])
        self.assertEqual(running['fragments'],1)
        self.assertIsNone(running['completion_tokens'])
        done=perf.finish(now=5)
        self.assertEqual(done['source'],'unavailable')
        self.assertIsNone(done['generation_tok_s'])

    def test_usage_fallback_is_explicit_estimate(self):
        perf=GenerationMetrics('demo',started_at=0)
        perf.ingest({'choices':[{'delta': {'content':'text'}}]},now=1)
        perf.ingest({'usage':{'completion_tokens':20,'prompt_tokens':10}},now=3)
        report=perf.finish(now=5)
        self.assertEqual(report['completion_tokens'],20)
        self.assertEqual(report['source'],'estimated')
        self.assertEqual(report['generation_tok_s'],5)

    def test_history_does_not_save_prompt_or_response(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'history.jsonl'
            append_history(path,{'model':'local.gguf','generation_tok_s':7.7,
                                 'prompt':'highly confidential','response':'private answer'})
            saved=path.read_text(encoding='utf-8')
            self.assertNotIn('confidential',saved)
            self.assertNotIn('private answer',saved)
            self.assertEqual(read_history(path)[0]['generation_tok_s'],7.7)

    def test_local_tokenizer_fallback(self):
        response = io.BytesIO(b'{"tokens":[11,12,13,14,15]}')
        with patch('urllib.request.urlopen',return_value=response) as mock:
            count=tokenize_output_count('http://127.0.0.1:8081/tokenize','Hello world')
        self.assertEqual(count,5)
        self.assertEqual(json.loads(mock.call_args.args[0].data)['add_special'],False)

    def test_hardware_metrics_shape(self):
        data = sample_hardware()
        self.assertIn('ram_total_gib',data)
        self.assertIn('gpu_used_mib',data)


class FakeResponse:
    def __init__(self,lines): self.lines=lines
    def __enter__(self): return self
    def __exit__(self,*args): return False
    def __iter__(self):
        for line in self.lines:
            yield b'data: '+json.dumps(line).encode('utf-8')+b'\n'
        yield b'data: [DONE]\n'


class StreamingTests(unittest.TestCase):
    def _run(self, urlopen):
        class MockApp:
            events=queue.Queue()
            metrics=GenerationMetrics('demo.gguf')
            endpoint=lambda self, route:'http://127.0.0.1:8081'+route
        app=MockApp()
        with patch('urllib.request.urlopen',side_effect=urlopen):
            Application.chat_request(app,'question',[{'role':'user','content':'question'}],0.7,100)
        evs=list(app.events.queue)
        self.assertIn('chat_done',[x[0] for x in evs])
        return evs

    def test_incoming_stream_includes_exact_server_timings(self):
        response=FakeResponse([
            {'choices':[{'delta':{'content':'Hello'}}]},
            {'choices':[{'delta':{'content':' world'}}]},
            {'choices':[],'timings':{'predicted_n':6,'predicted_per_second':12.5}}
        ])
        events=self._run(lambda *_args,**_kw:response)
        done=next(v for k,v in events if k=='perf_done')
        self.assertEqual(done['source'],'server')
        self.assertEqual(done['generation_tok_s'],12.5)
        self.assertEqual(next(v for k,v in events if k=='chat_done')[1],'Hello world')

    def test_older_llama_retries_without_usage_option(self):
        attempts=[]
        def fake(req,**kwargs):
            data=json.loads(req.data)
            attempts.append(data)
            if 'stream_options' in data:
                raise urllib.error.HTTPError(req.full_url,400,'unsupported',{},None)
            return FakeResponse([{'choices':[{'delta':{'content':'OK'}}]}])
        self._run(fake)
        self.assertGreaterEqual(len(attempts), 2)
        self.assertIn('stream_options', attempts[0])
        self.assertNotIn('stream_options', attempts[1])


if __name__=='__main__': unittest.main()
