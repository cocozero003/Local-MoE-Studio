"""Privacy-preserving performance measurements for the local llama.cpp desktop chat.

Streaming deltas are not guaranteed to contain one token. Until the inference
server reports usage/timings, report chunks per second rather than claim exact
live token speed. Completion token rate prefers llama.cpp server timings.
"""
from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def _nonnegative_number(value):
    if isinstance(value, bool):
        return None
    try:
        n = float(value)
        return n if 0 <= n < 1e12 else None
    except (TypeError, ValueError, OverflowError):
        return None


class GenerationMetrics:
    def __init__(self, model, started_at=None):
        self.model = str(model)
        self.started = time.perf_counter() if started_at is None else float(started_at)
        self.first_content = None
        self.last_content = None
        self.fragments = 0
        self.usage = {}
        self.timings = {}
        self.finished_at = None
        self.error = None

    def ingest(self, chunk, now=None):
        now = time.perf_counter() if now is None else float(now)
        if isinstance(chunk, dict):
            if isinstance(chunk.get('timings'), dict):
                self.timings.update(chunk['timings'])
            if isinstance(chunk.get('usage'), dict):
                self.usage.update(chunk['usage'])
            # llama.cpp provides SSE content in delta.content; count chunks as
            # stream fragments, NEVER as tokens.
            choices = chunk.get('choices') or []
            if choices and isinstance(choices[0], dict):
                delta = choices[0].get('delta') or {}
                text = delta.get('content') if isinstance(delta, dict) else None
                if text:
                    if self.first_content is None:
                        self.first_content = now
                    self.last_content = now
                    self.fragments += 1
                    return text
        return ''

    def finish(self, now=None, error=None):
        self.finished_at = time.perf_counter() if now is None else float(now)
        self.error = error
        return self.snapshot(self.finished_at)

    def snapshot(self, now=None):
        now = time.perf_counter() if now is None else float(now)
        end = self.finished_at if self.finished_at is not None else now
        elapsed = max(0, end - self.started)
        ttft = None if self.first_content is None else max(0, self.first_content - self.started)
        generation_duration = (max(0, end - self.first_content) if self.first_content is not None else None)
        chunks_per_second = None if not generation_duration or generation_duration < 0.01 else self.fragments / generation_duration
        tokens = _nonnegative_number(self.timings.get('predicted_n'))
        if tokens is None:
            tokens = _nonnegative_number(self.usage.get('completion_tokens'))
        prompt_tokens = _nonnegative_number(self.timings.get('prompt_n'))
        if prompt_tokens is None:
            prompt_tokens = _nonnegative_number(self.usage.get('prompt_tokens'))
        tok_per_sec = _nonnegative_number(self.timings.get('predicted_per_second'))
        precision = 'server' if tok_per_sec is not None else 'unavailable'
        if tok_per_sec is None and tokens is not None and generation_duration and generation_duration > 0.05:
            tok_per_sec = tokens / generation_duration
            precision = 'estimated'
        return {
            'model': self.model,
            'timestamp': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'active': self.finished_at is None,
            'elapsed_s': round(elapsed, 3),
            'ttft_s': round(ttft, 3) if ttft is not None else None,
            'generation_s': round(generation_duration, 3) if generation_duration is not None else None,
            'fragments': self.fragments,
            'chunks_per_second': round(chunks_per_second, 2) if chunks_per_second is not None else None,
            'completion_tokens': int(tokens) if tokens is not None else None,
            'prompt_tokens': int(prompt_tokens) if prompt_tokens is not None else None,
            'generation_tok_s': round(tok_per_sec, 2) if tok_per_sec is not None else None,
            'prompt_tok_s': _nonnegative_number(self.timings.get('prompt_per_second')),
            'source': precision,
            'error': self.error,
        }


def sample_hardware():
    """Snapshot system physical RAM and dedicated NVIDIA VRAM, when available.

    Never confuse Windows shared GPU memory with CPU-resident model weights.
    """
    sample = {'ram_used_gib': None, 'ram_total_gib': None,
              'gpu_used_mib': None, 'gpu_total_mib': None, 'gpu_util_pct': None}
    if os.name == 'nt':
        class MemoryStatus(ctypes.Structure):
            _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong),
                        ('total_phys', ctypes.c_ulonglong), ('available_phys', ctypes.c_ulonglong),
                        ('total_page', ctypes.c_ulonglong), ('available_page', ctypes.c_ulonglong),
                        ('total_virtual', ctypes.c_ulonglong), ('available_virtual', ctypes.c_ulonglong),
                        ('available_extended', ctypes.c_ulonglong)]
        stat = MemoryStatus()
        stat.length = ctypes.sizeof(stat)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            sample['ram_total_gib'] = round(stat.total_phys / 1024**3, 2)
            sample['ram_used_gib'] = round((stat.total_phys - stat.available_phys)/1024**3, 2)
    elif hasattr(os, 'sysconf'):
        try:
            pages = os.sysconf('SC_PHYS_PAGES')
            avail = os.sysconf('SC_AVPHYS_PAGES')
            size = os.sysconf('SC_PAGE_SIZE')
            sample['ram_total_gib'] = round(pages * size / 1024**3, 2)
            sample['ram_used_gib'] = round((pages - avail)*size/1024**3, 2)
        except (ValueError, OSError, TypeError):
            pass
    try:
        kwargs = {'stderr':subprocess.DEVNULL, 'timeout':3, 'text':True}
        if sys.platform == 'win32':
            kwargs['creationflags'] = getattr(subprocess,'CREATE_NO_WINDOW',0)
        raw = subprocess.check_output([
            'nvidia-smi', '--query-gpu=memory.used,memory.total,utilization.gpu',
            '--format=csv,noheader,nounits'], **kwargs)
        line = raw.strip().splitlines()[0]
        used, total, util = (float(x.strip()) for x in line.split(',')[:3])
        sample.update(gpu_used_mib=used, gpu_total_mib=total, gpu_util_pct=util)
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
        pass
    return sample



def tokenize_output_count(endpoint, text):
    """Best-effort fallback to count output tokens using the local llama.cpp tokenizer.

    This counts the completed text after generation; the resulting wall-clock
    rate is estimated (not the backend's exact generation timing).
    """
    if not text:
        return None
    request = urllib.request.Request(
        endpoint, data=json.dumps({'content': text, 'add_special': False}).encode('utf-8'),
        headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(request, timeout=10) as response:
        data = json.load(response)
    tokens = data.get('tokens') if isinstance(data, dict) else None
    return len(tokens) if isinstance(tokens, list) else None


def append_history(file_path, report, limit=500):
    """Store only per-request metrics; never store chat prompts or responses."""
    file_path = Path(file_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    allowed = {'timestamp', 'model', 'elapsed_s', 'ttft_s', 'generation_s',
               'completion_tokens', 'prompt_tokens', 'generation_tok_s',
               'prompt_tok_s', 'source', 'error'}
    safe = {key: report.get(key) for key in allowed}
    with file_path.open('a', encoding='utf-8') as f:
        f.write(json.dumps(safe, ensure_ascii=False) + '\n')
    # Rotate infrequently to prevent unbounded disk growth.
    if file_path.stat().st_size > 1024 * 256:
        lines = file_path.read_text(encoding='utf-8').splitlines()
        file_path.write_text('\n'.join(lines[-limit:]) + '\n', encoding='utf-8')


def read_history(file_path, limit=50):
    file_path = Path(file_path)
    if not file_path.is_file():
        return []
    rows = []
    for line in file_path.read_text(encoding='utf-8').splitlines()[-limit:]:
        try:
            data = json.loads(line)
            if isinstance(data, dict):
                rows.append(data)
        except ValueError:
            continue
    return list(reversed(rows))
