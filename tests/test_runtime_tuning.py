"""Regression tests for RTX 5060 8 GB settings and launch parity."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from localmoestudio.backend import DEFAULTS
from localmoestudio.profiles import PROFILES, apply_profile
from localmoestudio.runtime_tuning import performance_flags


class FakeVar:
    def __init__(self):
        self.value = None

    def set(self, value):
        self.value = value


class RuntimeTuningTests(unittest.TestCase):
    def test_8gb_presets_have_supported_gui_keys(self):
        for name in ("RTX 5060 8GB - Fast", "RTX 5060 8GB - RAG"):
            profile = PROFILES[name]
            self.assertTrue(set(profile) - {"description"} <= set(DEFAULTS))
            variables = {key: FakeVar() for key in DEFAULTS}
            apply_profile(variables, name)
            self.assertEqual(variables["parallel"].value, "1")
            self.assertEqual(variables["cache_ram"].value, "0")
            self.assertTrue(variables["flash"].value)

    def test_safe_defaults_and_consistent_batching(self):
        flags = performance_flags({})
        self.assertEqual(flags, [
            "--parallel", "1", "--batch-size", "1024",
            "--ubatch-size", "256",
        ])

    def test_optional_flags_require_engine_support(self):
        config = dict(
            parallel="1", batch_size="512", ubatch_size="128",
            cache_ram="0", cache_reuse="256", prompt_cache=True,
        )
        with tempfile.TemporaryDirectory() as folder:
            exe = Path(folder) / "llama-server.exe"
            exe.write_bytes(b"")
            with patch("localmoestudio.runtime_tuning.supported_options",
                       return_value=frozenset({
                           "--cache-ram", "--cache-reuse", "--cache-prompt",
                           "--no-cache-idle-slots",
                       })):
                args = performance_flags(config, exe)
        self.assertIn("--cache-ram", args)
        self.assertEqual(args[args.index("--cache-ram") + 1], "0")
        self.assertIn("--no-cache-idle-slots", args)
        self.assertEqual(args[args.index("--cache-reuse") + 1], "256")

    def test_unsupported_optional_flags_not_sent(self):
        with tempfile.TemporaryDirectory() as folder:
            exe = Path(folder) / "llama-server.exe"
            exe.write_bytes(b"")
            with patch("localmoestudio.runtime_tuning.supported_options",
                       return_value=frozenset()):
                args = performance_flags({"cache_reuse": "256"}, exe)
        self.assertNotIn("--cache-reuse", args)
        self.assertNotIn("--cache-ram", args)

    def test_rejects_invalid_memory_settings(self):
        bad_configs = (
            {"parallel": "0"},
            {"parallel": "nine"},
            {"ubatch_size": "2048", "batch_size": "512"},
            {"cache_ram": "-1"},
            {"cache_reuse": "9000"},
            {"cache_reuse": "256", "prompt_cache": False},
            {"prompt_cache": "not a boolean"},
        )
        for config in bad_configs:
            with self.subTest(config=config), self.assertRaises(ValueError):
                performance_flags(config)

    def test_headless_includes_same_tuning(self):
        from localmoestudio.headless import build_backend_command
        with tempfile.TemporaryDirectory() as folder:
            exe = Path(folder) / "llama-server.exe"
            model = Path(folder) / "test.gguf"
            exe.write_bytes(b"")
            model.write_bytes(b"")
            config = dict(DEFAULTS, server=str(exe), model=str(model),
                          moe="disabled", dense_ffn="0", parallel="1",
                          batch_size="512", ubatch_size="128")
            with patch("localmoestudio.headless.memory_flags", return_value=[]), \
                 patch("localmoestudio.runtime_tuning.supported_options",
                       return_value=frozenset()):
                args, port = build_backend_command(config)
        self.assertEqual(port, 8081)
        self.assertEqual(args[args.index("--parallel") + 1], "1")
        self.assertEqual(args[args.index("--ubatch-size") + 1], "128")


if __name__ == "__main__":
    unittest.main()
