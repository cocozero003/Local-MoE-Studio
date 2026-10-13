"""User-first performance presets. Advisory only; llama.cpp fit is authoritative."""
from pathlib import Path
PROFILES = {
 'Fast (small model)': {'description': 'Prefer low latency for small dense models.', 'moe':'disabled','gpu_layers':'auto','context':'4096','kv':'q8_0','fit':True,'fit_margin':'1024','flash':True},
 'Balanced': {'description': 'Automatic GPU fit and conservative context for most GGUF models.', 'moe':'disabled','gpu_layers':'auto','context':'4096','kv':'q8_0','fit':True,'fit_margin':'1024','flash':True},
 'Large MoE (low VRAM)': {'description': 'Keep MoE expert weights in system RAM and accelerate other layers on your GPU. Requires a MoE model.', 'moe':'all','gpu_layers':'auto','context':'4096','kv':'q8_0','fit':True,'fit_margin':'1024','flash':True},
 'CPU only': {'description': 'CPU-only inference, best for troubleshooting or systems without compatible GPUs.', 'moe':'disabled','gpu_layers':'0','context':'2048','kv':'q8_0','fit':False,'fit_margin':'1024','flash':False},
}
def apply_profile(vars, profile):
    values=PROFILES[profile]
    for key, value in values.items(): vars[key].set(value)

def infer_profile(model_name):
    name=model_name.lower()
    return 'Large MoE (low VRAM)' if any(word in name for word in ('a3b','a22b','moe','mixtral','gpt-oss')) else 'Balanced'

def recommendation(name, size_bytes, moe_mode):
    gb=size_bytes/(1024**3)
    hints=[f'Model: {name}',f'Weights: {gb:.1f} GiB on disk (not total memory use).']
    if gb > 48: hints.append('Very high RAM demand: ensure enough unused physical RAM and expect slow CPU inference.')
    elif gb > 14: hints.append('Likely requires substantial system RAM on a 6 GB GPU. Prefer MoE expert offload for MoE models.')
    elif gb > 5: hints.append('May use CPU/GPU split on a 6 GB GPU.')
    else: hints.append('May fit mostly on a 6 GB GPU depending on context and buffers.')
    if moe_mode == 'all' and infer_profile(name) != 'Large MoE (low VRAM)':
        hints.append('Warning: All-CPU MoE expert placement is for MoE models, not dense models.')
    hints.append('Estimates only. GPU capacity, architecture, cache, and OS memory affect actual fit.')
    return '\n'.join(hints)
