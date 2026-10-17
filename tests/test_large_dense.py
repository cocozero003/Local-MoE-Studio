"""Regression tests for dense/MoE classification and llama.cpp argument selection."""
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from localmoestudio.model_support import inspect_gguf, memory_flags, memory_advice
from localmoestudio.profiles import PROFILES, apply_profile, infer_profile

def make_gguf(path, architecture, experts=None):
    items = [('general.architecture', 8, architecture)]
    if experts is not None:
        items.append((architecture + '.expert_count', 4, experts))
    with path.open('wb') as f:
        f.write(b'GGUF' + struct.pack('<IQQ', 3, 0, len(items)))
        for key, kind, value in items:
            raw = key.encode('utf-8')
            f.write(struct.pack('<Q', len(raw)) + raw + struct.pack('<I', kind))
            if kind == 8:
                text = value.encode('utf-8')
                f.write(struct.pack('<Q', len(text)) + text)
            else:
                f.write(struct.pack('<I', value))

class FakeVar:
    def __init__(self):
        self.value = None
    def set(self, value):
        self.value = value

class LargeModelTests(unittest.TestCase):
    def test_dense_qwen35_metadata(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'Qwen3.5-27B-Q4_K_M.gguf'
            make_gguf(path, 'qwen35')
            self.assertEqual(inspect_gguf(path)['kind'], 'dense')
            self.assertEqual(memory_flags({'moe':'disabled','dense_ffn':'999'}, path),
                             ['--n-cpu-ffn', '999'])
            with self.assertRaisesRegex(ValueError, 'dense model'):
                memory_flags({'moe':'all','dense_ffn':'0'}, path)
            self.assertIn('Large Dense', memory_advice(path))

    def test_moe_model_requires_moe_flags(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'Qwen3-30B-A3B.gguf'
            make_gguf(path, 'qwen3moe', 128)
            self.assertEqual(inspect_gguf(path)['kind'], 'moe')
            self.assertEqual(memory_flags({'moe':'all','dense_ffn':'0'}, path),
                             ['--cpu-moe'])
            with self.assertRaisesRegex(ValueError, 'MoE model'):
                memory_flags({'moe':'disabled','dense_ffn':'8'}, path)

    def test_old_binary_gets_clear_error(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'Qwen3.5-27B.gguf'
            make_gguf(path, 'qwen35')
            exe = Path(d) / 'llama-server.exe'
            exe.write_bytes(b'')
            with patch('localmoestudio.model_support.engine_supports_cpu_ffn', return_value=False):
                with self.assertRaisesRegex(ValueError, 'does not support'):
                    memory_flags({'moe':'disabled','dense_ffn':'8'}, path, exe)

    def test_invalid_settings_and_unknown_file(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'random.gguf'
            path.write_bytes(b'not gguf')
            self.assertEqual(inspect_gguf(path)['kind'], 'unknown')
            with self.assertRaises(ValueError):
                memory_flags({'moe':'disabled','dense_ffn':'-1'}, path)

    def test_dense_profile_values(self):
        profile = 'Large Dense (low VRAM)'
        self.assertIn(profile, PROFILES)
        variables = {key: FakeVar() for key in PROFILES[profile] if key != 'description'}
        apply_profile(variables, profile)
        self.assertEqual(variables['dense_ffn'].value, '999')
        self.assertEqual(variables['moe'].value, 'disabled')
        self.assertEqual(infer_profile('Qwen3.5-27B-Q4_K_M.gguf'), profile)
        self.assertEqual(infer_profile('Qwen3-30B-A3B-Q4_K_M.gguf'), 'Large MoE (low VRAM)')

    def test_headless_uses_dense_flags(self):
        from localmoestudio.headless import build_backend_command
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            exe, model = folder / 'llama-server.exe', folder / 'Qwen3.5-27B.gguf'
            exe.write_bytes(b'')
            make_gguf(model, 'qwen35')
            config = dict(server=str(exe), model=str(model), moe='disabled',
                          dense_ffn='4', context=4096, gpu_layers='auto')
            with patch('localmoestudio.model_support.engine_supports_cpu_ffn', return_value=True):
                args, port = build_backend_command(config)
            self.assertIn('--n-cpu-ffn', args)
            self.assertEqual(args[args.index('--n-cpu-ffn')+1], '4')
            self.assertNotIn('--cpu-moe', args)

if __name__ == '__main__':
    unittest.main()
