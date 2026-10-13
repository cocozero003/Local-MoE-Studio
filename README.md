# Local MoE Studio

**A beginner-friendly Windows desktop GUI for running GGUF language models with llama.cpp, including MoE expert offloading to system RAM.**

> **Status: v0.6.1 alpha / developer preview.** Source and unit tests are available. It has **not** completed Windows CUDA hardware validation or public-distribution security testing.

## Features

- One-click installation/update of official llama.cpp Windows releases (CUDA or CPU mode).
- **Expanded live GGUF catalog**: Gemma, Qwen, Llama, Mistral, DeepSeek, Phi, GPT-OSS and other families.
- **Auto-refresh of model listings at startup** (default on), with an offline cache and a manual Refresh button.
- Search Hugging Face directly, filter by model family and sort by newest changes or download popularity.
- Browse repository GGUF files and download a selected **single-file** quantization only after confirmation.
- Beginner presets: Fast, Balanced, Large MoE (low VRAM), CPU only.
- Advanced MoE CPU expert placement, GPU layers, context length, Flash Attention, KV cache controls.
- Local streaming chat and saved conversations.
- NVIDIA memory/status information and server log window.
- Python standard-library runtime for source use; **no Docker**.

## Screenshots

![Settings interface](docs/images/settings.png)

## Settings text readability fix (v0.6.1)

Fixes truncated help descriptions and overlapping settings rows on Windows high-DPI displays (including 125%, 150% and 200% scaling). The Settings form now sizes each row to its content instead of constraining the description to the height of the adjacent input. Helper text also uses a larger readable font and additional vertical spacing. No llama.cpp configuration, model files, or chat history are changed.

To update: close the app, download the latest source, extract it into a new folder, and run `START_WINDOWS.bat`. The saved settings and models in your Windows local application-data folder will remain in place.

The layout is covered by a Tk geometry regression test at three display-scaling levels; tests run with a graphical display and skip when CI is headless. Windows hardware validation is still pending.

## Model discovery update (v0.6.0)

The original model browser had a closed four-model Qwen list. This version adds public Hugging Face GGUF discovery, model-family filtering, free-text search, sorting, and locally saved catalog metadata. New GGUF repos can appear on the next launch without changing the app code. **Startup refresh transfers only model metadata, not model weights.** Searches require internet access; cached results remain usable offline. Gated and private repositories are excluded from the automatic catalog, and model compatibility/licensing should be checked before downloading.

The starter catalog includes tested repository URLs for examples from Qwen, Gemma, Llama, Mistral, DeepSeek, Microsoft Phi and GPT-OSS. They are examples, not endorsements or a guarantee that the repository supports your hardware. Downloads and llama.cpp inference have not been end-to-end validated on Windows/NVIDIA hardware.

## Installer fix (v0.5.1)

The one-click installer now detects official llama.cpp Windows packages from upstream GitHub *pre-release* builds (such as `b11580`). It also recognizes both historical and current CUDA runtime filenames and strictly pairs matching CUDA versions. A previous release incorrectly skipped these builds, causing `No matching official Windows archive found`.

Existing v0.5.0 users: replace your app files with the latest source from GitHub, keep your existing per-user models and chat history, then retry **Models → Install / Update llama.cpp**. Downloads are several hundred MB; an NVIDIA driver compatible with the chosen CUDA release is still required.

## Quick start (Windows)

1. Install Python 3.11 or 3.12.
2. Click **Code → Download ZIP** on GitHub; extract the repository.
3. Double-click `START_WINDOWS.bat`.
4. In **Models**, click **Install / Update llama.cpp**.
5. Let **Discover GGUF models** refresh its list (or click **Refresh latest**), filter by family such as Gemma or Qwen, choose a repository, then click **Find GGUF files** and download a quantized model.
6. Apply the **Large MoE (low VRAM)** preset for compatible MoE models and click **Start model**.

Full instructions: [Windows installation](docs/INSTALL_WINDOWS.md).

## Alternative developer install

```powershell
py -3 -m pip install -e .
py -3 -m localmoestudio
```

## Repository structure

```text
local-moe-studio/
├── src/localmoestudio/       # Windows GUI, backend, downloads, installer
├── tests/                    # Automated unit tests
├── docs/                     # Install, architecture, audit, release criteria
├── scripts/                  # Build/test scripts for Windows
├── .github/workflows/        # Cross-platform unit-test CI
├── pyproject.toml            # Python packaging metadata
├── START_WINDOWS.bat         # Source launcher
├── LICENSE                   # MIT (original application code)
└── README.md
```

## Supported platform and constraints

- Primarily Windows 10/11. NVIDIA CUDA support requires a compatible NVIDIA driver and correct upstream llama.cpp build.
- Model size on disk is **not** total inference RAM consumption. Large MoE models require free system RAM and may be slow with CPU expert offloading.
- The current model downloader does **not** automatically retrieve multipart GGUF shards.
- Existing Ollama installations may remain installed, but avoid loading large models in both at once.
- llama.cpp itself, upstream CUDA DLLs and GGUF models are downloaded separately and have their **own** license terms.

## Privacy

Chat history and preferences are kept on the device in the current user's application-data folder (unencrypted local files). By default, app startup contacts **Hugging Face** to refresh public model **metadata**. You can disable this on the Models page. Search, model-file downloads, and optional llama.cpp engine updates contact Hugging Face or GitHub when requested. Model weights are **not** downloaded automatically. The app does not add analytics/telemetry.

## Tests and builds

```powershell
py -3 -m unittest discover -s tests -v
```

On Windows, `scripts\build_windows.bat` creates an **unsigned developer EXE** with PyInstaller. This is not a one-click installer suitable for public release.

## Roadmap

- [ ] Fully bundled and signed Windows installer
- [ ] Verified automatic MoE benchmarking and memory advisor
- [ ] Split GGUF shard management and cryptographic download verification
- [ ] Model licenses and compatibility information in the browser
- [ ] Tested inference builds across 4–12 GB NVIDIA VRAM
- [ ] Optional local RAG/document chat

## Documents

[Architecture](docs/ARCHITECTURE.md) · [Product audit](docs/PRODUCT_AUDIT.md) · [Release checklist](docs/RELEASE_CHECKLIST.md) · [Contributing](docs/CONTRIBUTING.md) · [Security](SECURITY.md)

## Licensing

Original Local MoE Studio application code in this repository is offered under the [MIT License](LICENSE). Redistribution of llama.cpp, drivers/runtime libraries, or model weights is governed by their separate license obligations.
