"""llama.cpp runtime knobs for small NVIDIA GPUs.

Only standard llama-server flags are used. Strata's custom expert cache and
fused kernels are not part of llama.cpp and cannot be enabled by these flags.
No external Python dependencies and no background downloads.
"""
from functools import lru_cache
from pathlib import Path
import subprocess


def _integer(config, key, default, minimum, maximum):
    raw = str(config.get(key, default)).strip()
    if not raw.isdecimal():
        raise ValueError(f"{key} must be an integer between {minimum} and {maximum}.")
    value = int(raw)
    if not minimum <= value <= maximum:
        raise ValueError(f"{key} must be an integer between {minimum} and {maximum}.")
    return value


@lru_cache(maxsize=24)
def supported_options(executable, modified_ns):
    """Inspect installed llama-server help once per binary version."""
    try:
        result = subprocess.run(
            [str(executable), "--help"], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired):
        return frozenset()
    help_text = result.stdout + result.stderr
    return frozenset(
        flag for flag in (
            "--cache-ram", "--cache-reuse", "--no-cache-idle-slots",
            "--cache-prompt", "--no-cache-prompt",
        ) if flag in help_text
    )


def performance_flags(config, executable=None):
    """Build conservative, validated args shared by desktop and Team Hub.

    The two batch values trade peak memory against prompt ingestion speed.
    Settings that are unsupported by an older engine are not emitted.
    """
    parallel = _integer(config, "parallel", "1", 1, 8)
    batch = _integer(config, "batch_size", "1024", 128, 8192)
    ubatch = _integer(config, "ubatch_size", "256", 32, 2048)
    cache_ram = _integer(config, "cache_ram", "0", 0, 65536)
    cache_reuse = _integer(config, "cache_reuse", "0", 0, 8192)
    if ubatch > batch:
        raise ValueError("ubatch_size must not exceed batch_size.")
    raw_prompt_cache = config.get("prompt_cache", True)
    if isinstance(raw_prompt_cache, bool):
        prompt_cache = raw_prompt_cache
    elif str(raw_prompt_cache).lower() in ("true", "1", "yes", "on"):
        prompt_cache = True
    elif str(raw_prompt_cache).lower() in ("false", "0", "no", "off"):
        prompt_cache = False
    else:
        raise ValueError("prompt_cache must be enabled or disabled.")
    if cache_reuse and not prompt_cache:
        raise ValueError("cache_reuse requires prompt_cache to be enabled.")

    flags = [
        "--parallel", str(parallel),
        "--batch-size", str(batch),
        "--ubatch-size", str(ubatch),
    ]

    available = frozenset()
    if executable:
        executable_path = Path(executable)
        if executable_path.is_file():
            available = supported_options(str(executable_path),
                                          executable_path.stat().st_mtime_ns)

    # --cache-ram defaults to 8192 MiB on some recent llama.cpp releases.
    # For an 8 GB VRAM / 32 GB RAM machine, a 0 MiB RAM checkpoint
    # cache avoids holding an additional multi-gigabyte copy of prompts.
    if "--cache-ram" in available:
        flags.extend(["--cache-ram", str(cache_ram)])
    if "--no-cache-idle-slots" in available:
        flags.append("--no-cache-idle-slots")
    if prompt_cache and "--cache-prompt" in available:
        flags.append("--cache-prompt")
    elif not prompt_cache and "--no-cache-prompt" in available:
        flags.append("--no-cache-prompt")
    if cache_reuse and "--cache-reuse" in available:
        flags.extend(["--cache-reuse", str(cache_reuse)])
    return flags
