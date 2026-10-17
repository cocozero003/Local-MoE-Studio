# RTX 5060 8 GB tuning for Local MoE Studio

This is a conservative performance update for Windows, NVIDIA RTX 5060
(8 GB dedicated VRAM), Intel i5 10th generation and 32 GB DDR4 RAM.
It also applies to other NVIDIA GPUs with similarly limited VRAM.

## What this can and cannot do

- **Can:** reduce out-of-memory errors and wasted CPU RAM, give sensible
  single-user llama.cpp defaults, preserve prefix caching where the
  installed engine supports it, adjust prompt-batch sizes, and benchmark.
- **Cannot:** reproduce Strata's custom MoE expert caching or specialized
  CUDA kernels, or guarantee Strata's reported throughput on 12/24 GB cards.
- **No benchmark was executed on the user's RTX 5060** as part of this
  source-only change. Measure on the actual machine before claiming gains.
- GPU layer offload, dense CPU FFN offload and MoE CPU expert offload are
  already supported by Local MoE Studio. They remain available.

## 1. Update the engine and choose a suitable model

1. Update your local copy of Local MoE Studio and start `START_WINDOWS.bat`.
2. Open **Models** and install/update a current official CUDA-enabled
   llama.cpp binary compatible with the RTX 50 series. Prefer CUDA 13
   when supported by your driver and the app's release selector.
3. Select an existing **3B-8B Q4 GGUF** as the initial speed baseline.
   A Q4 model around 4B-8B parameters is a *starting range*, not
   proof that every model with that label will fit in 8 GB.
4. Keep model weights and RAG source data on D: if you prefer. The
   executable and Python project can remain on C:.
5. Do not run two GPU-serving engines at once during benchmarking.

For any larger dense model, GPU and CPU split is unavoidable on 8 GB.
For large MoE models, `--cpu-moe` makes the host CPU/RAM do substantial
work. On 32 GB DDR4 it may be very slow, and some models will not fit.

## 2. Apply a performance preset

From **Settings > Easy setup**, select a preset, click **Apply preset**,
return to **Models** and start the model.

| Preset | Context | KV | Batch / microbatch | Free VRAM target | Best for |
| --- | ---: | --- | --- | ---: | --- |
| RTX 5060 8GB - Fast | 4096 | q8_0 | 1024 / 256 | 768 MiB | Small GGUF chat and coding |
| RTX 5060 8GB - RAG | 8192 | q8_0 | 512 / 128 | 1024 MiB | Thai FDA FAQ / regulatory PDF RAG |

Both presets use one server slot, Flash Attention, auto GPU fit,
prefix prompt caching and **0 MiB of additional server RAM prompt cache**
on supported llama.cpp releases.

### If you run out of VRAM

1. Reduce context to 4096, then 2048 if needed.
2. Reduce physical batch from 256 to 128 or 64.
3. Increase free VRAM target from 768 to 1024 or 1536 MiB.
4. Try Q4 KV for longer context **only after checking response quality**.
5. Select a smaller quantized model. For speed, prefer a model mostly
   resident in VRAM over a much larger model split across DDR4.

A larger batch is *not* automatically faster. It can improve prompt
prefill but also increase peak memory. Measure both latency and throughput.

### If the output is slow even though the model starts

- Stop Ollama, Strata, other llama.cpp servers and GPU applications.
- Check NVIDIA driver compatibility and CUDA engine build.
- Measure actual dedicated GPU memory with `nvidia-smi`.
- Reduce CPU-offloaded weights by choosing a smaller model.
- Prefer an NVMe SSD for large model weights.
- Use Windows High performance power mode if appropriate.
- Do not mistake GPU model speed for large-LLM quality; a 4B model
  may be faster but weaker than a large MoE.

## 3. Runtime flags and backward compatibility

Desktop and headless Team Hub now use the **same**
`performance_flags()` implementation:

- `--parallel 1`: reserve one main inference slot for individual use.
- `--batch-size` and `--ubatch-size`: control logical/physical batches.
- `--cache-ram 0`: where supported, avoid the recent llama.cpp
  default server RAM prompt checkpoint pool, which can be several GiB.
- `--no-cache-idle-slots`: where supported, avoid idle-slot caching.
- `--cache-prompt`: keep per-request prefix reuse if supported.
- `--cache-reuse 0`: disabled by default; set 256 only if you test
  the benefit for your workload and the engine advertises the flag.

Optional cache flags are emitted only if the chosen `llama-server.exe
--help` advertises them. Older engines still receive the standard
batch/slot arguments. Existing GGUFs, sessions and settings are retained.

For **multi-user regulated or confidential information**, this is
not a security boundary: Team Hub remains a pilot without a completed
security review, TLS, auditability or verified isolation of model
internal caches. Never expose 8765 or 8081 to the public internet.

## 4. Benchmark the actual 5060

From your Local MoE Studio repository:

```powershell
# Baseline after loading a model in Local MoE Studio (default port 8081)
py -3.11 scripts\benchmark_local.py --url http://127.0.0.1:8081 --model auto --runs 3 --output baseline.json

# Stop the model, apply RTX 5060 8GB - Fast, start the SAME GGUF and repeat
py -3.11 scripts\benchmark_local.py --url http://127.0.0.1:8081 --model auto --runs 3 --output tuned.json
```

The script detects the loaded model ID via /v1/models and sends the same fixed synthetic prompts each time, including
a Thai question and a longer RAG-style input. Reports include observed
wall seconds and, when returned by the engine, prompt/decode tok/s.
**No input prompt or model response is saved in the JSON report.**

To compare against Strata, you can run the same script at
`http://127.0.0.1:8080` with its model identifier; this measures
**end-to-end experience, not an apples-to-apples engine performance
comparison** if the models or quantizations differ.

Do not claim gains without a before/after benchmark under the same
conditions: same model, quantization, context, input, output limit,
warmup condition, driver and background GPU load.

## 5. Connect the existing regulatory RAG

Your separate repository
[`Local-RAG-for-Local-MoE-Studio`](https://github.com/cocozero003/Local-RAG-for-Local-MoE-Studio)
already uses a configurable OpenAI-compatible local inference endpoint.
No RAG re-indexing is required after changing only the inference model.

```powershell
$env:LOCAL_AI_ROOT="D:\LocalAI"
$env:LOCAL_RAG_LLM_URL="http://127.0.0.1:8081/v1/chat/completions"
$env:LOCAL_RAG_MODEL="local"
& ".\.venv\Scripts\python.exe" scripts\rag.py ask "อธิบายหลักฐานความปลอดภัยจากเอกสารที่มี"
```

For Thai FDA legal work, improving retrieval, exact source citations,
version dates and evaluation often matters more than model parameter size.
Use only trusted, nonconfidential test documents until application
security and legal traceability have been validated.

## 6. Tests

```powershell
py -3.11 -m unittest discover -s tests -v
py -3.11 -m compileall -q src scripts
```

Tests are synthetic: they check presets, argument validation and
desktop/headless parity. They **cannot** verify 5060 CUDA correctness
or real throughput without running on the target Windows PC.

### References

- [llama.cpp server documentation](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
- [Strata project](https://github.com/Niko1221/Strata)
- [Local MoE Studio](https://github.com/cocozero003/Local-MoE-Studio)
