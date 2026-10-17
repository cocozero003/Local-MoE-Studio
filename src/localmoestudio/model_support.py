"""Read GGUF metadata to select safe CPU/GPU memory arguments.

This reader scans metadata only; it never loads tensor weights into memory.
"""
from __future__ import annotations
from functools import lru_cache
from pathlib import Path
import re
import struct
import subprocess

_SCALARS = {0: ('B', 1), 1: ('b', 1), 2: ('H', 2), 3: ('h', 2),
            4: ('I', 4), 5: ('i', 4), 6: ('f', 4), 7: ('?', 1),
            10: ('Q', 8), 11: ('q', 8), 12: ('d', 8)}

def _exact(fp, count):
    data = fp.read(count)
    if len(data) != count:
        raise ValueError('Truncated GGUF metadata')
    return data

def _u32(fp):
    return struct.unpack('<I', _exact(fp, 4))[0]

def _u64(fp):
    return struct.unpack('<Q', _exact(fp, 8))[0]

def _string(fp, max_length=65536):
    count = _u64(fp)
    if count > max_length:
        raise ValueError('Unusually large GGUF metadata string')
    return _exact(fp, count).decode('utf-8', errors='replace')

def _value(fp, kind):
    if kind in _SCALARS:
        code, width = _SCALARS[kind]
        return struct.unpack('<' + code, _exact(fp, width))[0]
    if kind == 8:
        return _string(fp)
    if kind == 9:
        item_type = _u32(fp)
        count = _u64(fp)
        if item_type in _SCALARS:
            fp.seek(count * _SCALARS[item_type][1], 1)
        elif item_type == 8 and count <= 4096:
            for _ in range(count):
                _string(fp, max_length=1048576)
        else:
            raise ValueError('Unsupported or exceptionally large GGUF metadata array')
        return None
    raise ValueError('Unsupported GGUF metadata type')

def inspect_gguf(model_path):
    """Return kind, architecture, expert_count, source. File hints are labeled unverified."""
    path = Path(model_path)
    kind, architecture, experts, source = 'unknown', '', 0, 'filename (unverified)'
    try:
        with path.open('rb') as fp:
            if _exact(fp, 4) != b'GGUF':
                raise ValueError('Not a GGUF header')
            if _u32(fp) not in (2, 3):
                raise ValueError('Unsupported GGUF header version')
            _u64(fp)
            count = _u64(fp)
            if count > 100000:
                raise ValueError('Invalid GGUF metadata count')
            metadata = {}
            for _ in range(count):
                key = _string(fp, 4096)
                value = _value(fp, _u32(fp))
                if key == 'general.architecture' or key.endswith('.expert_count'):
                    metadata[key] = value
            architecture = str(metadata.get('general.architecture') or '')
            values = [int(value) for key, value in metadata.items()
                      if key.endswith('.expert_count') and isinstance(value, int)]
            experts = max(values, default=0)
            kind = 'moe' if experts > 1 or architecture.endswith('moe') else 'dense'
            source = 'gguf-header'
    except (ValueError, OSError, OverflowError, struct.error):
        name = path.name.lower()
        if re.search(r'(?:a\d+b|moe|mixtral|gpt-oss)', name):
            kind = 'moe'
        elif re.search(r'(?:qwen3[._-]?5|qwen3|gemma|llama|mistral|phi|deepseek)', name):
            kind = 'dense'
    return {'kind': kind, 'architecture': architecture, 'experts': experts, 'source': source}

@lru_cache(maxsize=16)
def engine_supports_cpu_ffn(executable, mtime_ns):
    """Avoid flags unknown to older downloaded llama.cpp binaries."""
    try:
        result = subprocess.run([str(executable), '--help'], capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=15,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except (OSError, subprocess.TimeoutExpired):
        return False
    return '--n-cpu-ffn' in (result.stdout + result.stderr)

def memory_flags(config, model_path, executable=None):
    info = inspect_gguf(model_path)
    moe = str(config.get('moe', 'disabled'))
    raw_ffn = str(config.get('dense_ffn', '0')).strip()
    if not raw_ffn.isdecimal() or not 0 <= int(raw_ffn) <= 999:
        raise ValueError('Dense CPU FFN layers must be a number from 0 to 999.')
    ffn = int(raw_ffn)
    if moe not in ('all', 'first N layers', 'disabled'):
        raise ValueError('Invalid MoE expert placement option.')
    if info['kind'] == 'dense' and moe != 'disabled':
        raise ValueError('This appears to be a dense model. Disable MoE expert placement, '
                         'or apply the Large Dense (low VRAM) preset.')
    if info['kind'] == 'moe' and ffn:
        raise ValueError('This appears to be a MoE model. Set Dense CPU FFN layers to 0.')
    if moe != 'disabled' and ffn:
        raise ValueError('Select either MoE expert offloading or dense FFN offloading, not both.')
    flags = []
    if moe == 'all':
        flags.append('--cpu-moe')
    elif moe == 'first N layers':
        count = str(config.get('moe_layers', '0')).strip()
        if not count.isdecimal() or int(count) > 999:
            raise ValueError('MoE CPU layers must be a number from 0 to 999.')
        flags.extend(['--n-cpu-moe', count])
    if ffn:
        if executable:
            path = Path(executable)
            if not engine_supports_cpu_ffn(str(path), path.stat().st_mtime_ns):
                raise ValueError('Your llama.cpp build does not support --n-cpu-ffn. '
                                 'Stop the model and use Models > Install / Update llama.cpp.')
        flags.extend(['--n-cpu-ffn', str(ffn)])
    return flags

def memory_advice(model_path, ram_gib=None, vram_gib=None):
    """Conservative size advice; runtime usage also depends on buffers and context."""
    path = Path(model_path)
    info = inspect_gguf(path)
    gib = path.stat().st_size / 2**30
    lines = [f'Model: {path.name}', f'Architecture: {info["kind"]} ({info["source"]})',
             f'Model file: {gib:.1f} GiB; runtime memory will be higher.']
    if ram_gib:
        lines.append(f'System RAM: {ram_gib:.0f} GiB.')
        if gib > .75 * ram_gib:
            lines.append('Caution: weights use most of RAM; consider smaller quantization.')
    if vram_gib:
        lines.append(f'Dedicated GPU memory: {vram_gib:.1f} GiB.')
    if info['kind'] == 'dense':
        lines.append('For large dense models on small GPUs, try Large Dense (low VRAM) '
                     'and CPU FFN offload. The CPU portion may generate slowly.')
    elif info['kind'] == 'moe':
        lines.append('For large MoE models on small GPUs, try Large MoE (low VRAM).')
    else:
        lines.append('Model type is unconfirmed. Check GGUF metadata and choose a preset manually.')
    lines.append('Model file size does not include KV cache, activation buffers or Windows overhead.')
    return '\n'.join(lines)
