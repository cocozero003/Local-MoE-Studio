"""User-first memory presets; they do not guarantee loading or performance."""
from pathlib import Path

PROFILES = {
 'Fast (small model)': {'description': 'Prefer speed for models that mostly fit GPU memory.',
   'moe':'disabled','dense_ffn':'0','gpu_layers':'auto','context':'4096',
   'kv':'q8_0','fit':True,'fit_margin':'1024','flash':True},
 'Balanced': {'description': 'Allow llama.cpp to distribute a model between CPU and GPU.',
   'moe':'disabled','dense_ffn':'0','gpu_layers':'auto','context':'4096',
   'kv':'q8_0','fit':True,'fit_margin':'1024','flash':True},
 'Large Dense (low VRAM)': {'description': 'Keep dense feed-forward (FFN) weights in system RAM '
   'while using the GPU for eligible tensors. For quantized Qwen3.5 27B and similar dense models; '
   'requires llama.cpp --n-cpu-ffn support. CPU-heavy generation can be slow.',
   'moe':'disabled','dense_ffn':'999','gpu_layers':'auto','context':'4096',
   'kv':'q8_0','fit':True,'fit_margin':'1024','flash':True},
 'Large MoE (low VRAM)': {'description': 'Keep MoE expert weights in system RAM. '
   'For MoE architectures, not dense Qwen3.5 27B.',
   'moe':'all','dense_ffn':'0','gpu_layers':'auto','context':'4096',
   'kv':'q8_0','fit':True,'fit_margin':'1024','flash':True},
 'CPU only': {'description': 'Place model weights on CPU; useful for GPU compatibility checks.',
   'moe':'disabled','dense_ffn':'0','gpu_layers':'0','context':'2048',
   'kv':'q8_0','fit':False,'fit_margin':'1024','flash':False},
}
def apply_profile(vars, profile):
    for key, value in PROFILES[profile].items():
        if key != 'description':
            vars[key].set(value)

def infer_profile(model_name):
    name=Path(model_name).name.lower()
    if any(word in name for word in ('a3b','a22b','moe','mixtral','gpt-oss')):
        return 'Large MoE (low VRAM)'
    if any(word in name for word in ('27b','32b','70b','72b','34b','30b')):
        return 'Large Dense (low VRAM)'
    return 'Balanced'

def recommendation(name, size_bytes, moe_mode):
    from .model_support import memory_advice
    import os
    from tempfile import NamedTemporaryFile
    # Compatibility for callers that know the model size but not its full path.
    gb=size_bytes/2**30
    hints=[f'Model: {name}', f'Weights: {gb:.1f} GiB on disk (runtime uses more).']
    if gb > 48:
        hints.append('Very high system RAM demand; consider smaller quantization.')
    elif gb > 14:
        hints.append('Significant system RAM is likely needed on a small GPU.')
    if moe_mode=='all' and infer_profile(name) != 'Large MoE (low VRAM)':
        hints.append('MoE expert offload does not apply to ordinary dense models.')
    hints.append('Use Check model fit for GGUF header detection and more advice.')
    return '\n'.join(hints)
