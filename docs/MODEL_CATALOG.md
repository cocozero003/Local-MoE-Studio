# GGUF model catalog

## User flow

1. Open Models: the cached or starter list appears immediately.
2. By default a background refresh searches public Hugging Face GGUF repositories, covering Gemma, Qwen, Llama, Mistral, DeepSeek, Phi, GPT-OSS, and other uploads.
3. Select a family, type a filter, or choose Sort: Newest updates / Most downloaded.
4. Search Hugging Face for other architectures or model names.
5. Select a repository, click **Find GGUF files**, select a quantization, and explicitly confirm its download.
6. Use **Start model** after loading llama.cpp (optional MoE expert offloading in Settings).

Model *catalog metadata* is downloaded on launch unless disabled by the checkbox. GGUF model weights are never downloaded automatically. Offline mode uses the cached catalog from a previous successful refresh; a set of example repos is available on first launch.

## Limitations

- Repositories listed by Hugging Face may have community-maintained, third-party quantizations. Publisher, license and model card need human review.
- Automatic catalog excludes gated/private repositories; those may require login and license acceptance. There is no Hugging Face authentication in this version.
- "Newest updates" sorts by repository `lastModified` from Hugging Face; README updates can move older models to the top. It is **not** a guaranteed model release-date ranking.
- Hugging Face rate limits, network outages and unavailable APIs can delay refresh. Cached results remain accessible.
- Some repos contain split GGUFs or require external vision/audio projection files; v0.6.0 does not automatically download those dependencies.
- Large GGUF files may require more system RAM than disk size implies, and not all GGUF variants are compatible with every llama.cpp build.
- Catalog search uses metadata; it does not execute files from other publishers. Download is a separate opt-in action.

## Technical implementation

- `src/localmoestudio/model_hub.py`: metadata normalization, concurrent Hugging Face REST queries, deduplication, cache, quantization listing and downloads.
- `src/localmoestudio/app.py`: Tkinter family and sort selectors, searchable catalog table, startup refresh in a background thread, offline fallback.
- `tests/test_catalog.py`: mocked-network discovery, filtering, family tags, gated/private exclusions and cache tests.

No new Python dependencies; everything uses the standard library.
