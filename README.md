# Local MoE Studio

**A beginner-friendly Windows desktop GUI for running GGUF language models with llama.cpp, including MoE expert offloading to system RAM.**

> **Status: v0.8.3 alpha / multi-user preview.** Source and unit tests are available. It has **not** completed Windows CUDA hardware validation or public-distribution security testing.

## Visible Stop model controls (v0.7.6)

The desktop now exposes a **Stop model** button in the sidebar (available on
Chat, Models, Settings, and Logs) and in the pinned **Easy setup** toolbar at the
bottom of Settings. Both buttons indicate disabled when this application has no
running model and enabled when its managed llama.cpp server is running. The
sidebar shows **Model running** or **Model stopped**.

Applying a different easy preset while the model is active now offers to stop
the managed model and apply the settings, rather than displaying a dead-end
instruction with no visible way to stop. Stopping during an active generation
asks for confirmation. The UI controls stop only the llama.cpp process launched
by this application; they do not stop Ollama or other unrelated server processes.

After stopping, select **Models → Installed models → Use and start** to restart
with new settings. Existing GGUF downloads, conversations and installed llama.cpp
engines remain unchanged.

## Installed GGUF library (v0.7.3)

The previous **Open models folder** action opened Explorer only. It could not select or load
a GGUF file into the app. The Models page now lists downloaded GGUFs (including nested folders)
under **Installed models**. Use **Use selected** or **Use and start**; choose an external
GGUF with **Choose a GGUF file...**. **Manage files in Explorer** now clearly means file
management only. The list refreshes automatically after a model download or on demand.
Incomplete GGUF shards are marked and prevented from being selected.

No local model files, downloaded engines, or conversations are deleted or moved.

## Desktop chat composer fix (v0.7.2)

The desktop chat editor now remains pinned to the bottom of the Chat screen, even in smaller windows or at higher display scaling. Type into **Message your local model** and click **Send** or press Enter; Shift+Enter inserts a line break. **Attach text** inserts the contents of a local UTF-8 text file up to 16 KB into the prompt. Larger documents should use the Team Hub library. This version does not implement voice input.

The fixed composer and existing chat sessions work with the same settings and downloaded GGUF models. Windows/NVIDIA end-to-end validation is still required.

## Safe engine updates (v0.7.4)

Fixes Windows **WinError 32** caused by attempting to rename the existing `llama.cpp-cuda12` directory while `llama-server.exe` or a CUDA DLL is in use.

- New downloads install in a separate versioned folder (for example, `llama.cpp-cuda12-b11580`), without renaming or removing the version being used.
- A release is published only after all binary archives have been downloaded, extracted, and validated; the app then switches its selected executable path.
- The desktop app prevents starting a model during an engine installation and refuses installing/updating an engine while its own model server is active.
- Older engine directories, saved models, and conversations are preserved. Running older engines continue to work.
- This does **not** restart or interrupt a running external llama.cpp process. Stop active inference before updating if you want to switch immediately.

After updating the source, close the app, reopen it via `START_WINDOWS.bat`, and load your existing GGUF using **Models → Installed models → Use and start**. You do not need to click **Install / Update llama.cpp** to chat if the installed server is already working.

## Live performance dashboard (v0.7.5)

The Windows desktop Chat page now includes a compact, non-blocking performance panel. It tracks:

- **Generation speed (tok/s)** from llama.cpp `timings.predicted_per_second` when the server reports it.
- If the server reports only token usage, the generation speed is labeled as an **estimate** using observed wall generation time.
- For streams that report neither, the app asks the **local** llama.cpp `/tokenize` endpoint for the output token count after completion. The resulting wall-clock tok/s is marked **estimated**.
- While a stream is in progress, the app shows **chunks/s** rather than misleadingly treating every streaming chunk as one token.
- Time to first content, response duration, generated tokens, dedicated NVIDIA GPU VRAM and system physical RAM.
- A local **History** dialog listing previous per-model measurements. History is stored at `%LOCALAPPDATA%\LocalMoEStudio\performance_history.jsonl` with no chat prompts or responses.

The dashboard polls physical memory through Windows and NVIDIA VRAM via `nvidia-smi` approximately every 3 seconds, in background threads. CUDA model inference itself must still be tested on NVIDIA hardware. Automated streaming and GUI tests cover the metrics and display.

## Long-answer completion handling (v0.8.3)

Local llama.cpp responses that stop with `finish_reason=length` are now
reported as truncated, not complete. The **Auto-continue** option in Chat
(default on) performs at most two additional, bounded requests when needed.
The **Continue answer** button allows another extension when the output limit
is reached, or when a server response ends without a finish signal. The
button is disabled during generation.

Manual continuation extends the last assistant message in the saved session
without adding a duplicate user question. Stopped, truncated, interrupted
and unknown-finish responses have distinct status text. To reduce repeated
extensions, raise **Tokens/request** from 1024 to 2048 if the model and
context can accommodate it; larger values cost additional generation time
and context memory. Automatic continuation is deliberately bounded so
an unexpectedly long response cannot run forever.

## Rich conversational chat (v0.8.2)

Chat now presents user prompts in blue right-aligned bubbles and renders the
assistant's completed answer as readable, left-aligned paragraphs, headings,
bullets, inline emphasis, code and simple Markdown tables. Live generation
continues to stream in the transcript; once the response is complete, the
saved conversation is re-rendered in the richer format.

The same renderer is used for previously saved conversations, avoiding
inconsistent transcript styles. The view uses standard-library Tkinter,
does not execute HTML or model-generated code, and preserves the existing
llama.cpp engine, model downloader, GPU/MoE controls and Team Hub.

## Sidebar navigation and metrics (v0.8.1)

The Chat page now has a **New chat** subitem in the sidebar. Models has a
**Select a model** dropdown populated from complete local GGUF downloads,
plus a link to browse the full Models page. Changing the selected model does
not silently stop or start an inference server; the existing running-model
warning still applies.

Generation speed, time to first token, output tokens, response duration, and
GPU/System RAM readings are now grouped at the bottom of the sidebar.
The upper navigation/sidebar area scrolls independently, keeping metrics
visible and preventing saved chats, Team Hub and Stop model controls from
being hidden on shorter displays. The Chat composer remains pinned at the
bottom. Existing chat histories, settings and model files are untouched.

## Minimal desktop UI (v0.8.0)

Refined white/gray desktop styling inspired by streamlined local model interfaces. The sidebar, chat transcript, composer and performance strip have more consistent spacing and typography. No inference, download, Team Hub or Stop model functionality was intentionally changed. Local MoE Studio is independent of Ollama.

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

## CI portability fix (v0.7.1)

Fixes SQLite connection cleanup on Windows (open file handles prevented temporary database cleanup) and makes high-DPI Tk layout assertions portable to headless Windows test runners. These are reliability fixes; Team Hub remains an alpha pilot.

## Team Hub (new in v0.7.0)

The optional **Team Hub** adds a browser interface for multiple local users while keeping **llama.cpp** as the inference engine. It does not use Docker, Ollama, or cloud model APIs.

- Desktop **Open Team Hub** button; optional explicit **Share on private LAN** checkbox.
- Separate administrator/member accounts, authenticated sessions, local chat history, and per-user document isolation.
- Private document upload/search for TXT, Markdown, DOCX and optional text-based PDFs (requires `pypdf`). Document retrieval is **keyword/trigram-based**, not yet semantic vector RAG.
- Protected OpenAI-compatible `/v1/models` and `/v1/chat/completions` endpoints with personal bearer API keys; response streaming supported.
- One active generation at a time, with bounded wait for shared limited-VRAM hardware.
- Headless launch scripts that start llama.cpp from saved desktop settings and serve the same browser UI.

**Start:** Open a GGUF model in the Windows desktop app, click **Open Team Hub**, then create an administrator account on the host PC. By default it is available only at `http://127.0.0.1:8765`. For details read [Team Hub setup](docs/TEAM_HUB.md) and [API guide](docs/API.md).

**Security caution:** Optional LAN mode uses unencrypted HTTP. It is intended for a **trusted private LAN pilot only**, not public internet access or sensitive regulated documents. A security review, TLS, robust auditing, SSO and data-at-rest encryption are not yet complete. **Do not expose ports 8765 or 8081 to the internet.**

## Screenshots

![Settings interface](docs/images/settings.png)

## Model discovery update (v0.6.0)

The original model browser had a closed four-model Qwen list. This version adds public Hugging Face GGUF discovery, model-family filtering, free-text search, sorting, and locally saved catalog metadata. New GGUF repos can appear on the next launch without changing the app code. **Startup refresh transfers only model metadata, not model weights.** Searches require internet access; cached results remain usable offline. Gated and private repositories are excluded from the automatic catalog, and model compatibility/licensing should be checked before downloading.

The starter catalog includes tested repository URLs for examples from Qwen, Gemma, Llama, Mistral, DeepSeek, Microsoft Phi and GPT-OSS. They are examples, not endorsements or a guarantee that the repository supports your hardware. Downloads and llama.cpp inference have not been end-to-end validated on Windows/NVIDIA hardware.

## Settings readability and GPU-first preset (v0.6.1)

- Fix clipped settings labels on high-DPI Windows displays. The settings row height now follows the full height of its helper text, and mouse-wheel scrolling is supported.
- The default configuration for new installs is **GPU first (RAM fallback)**. The preset uses automatic GPU layers (`-ngl auto`), llama.cpp memory fitting (`-fit on`), an initial 512 MiB headroom (`-fitt 512`), 4096 context and Q8 KV cache. GPU layers and CPU RAM usage are determined by llama.cpp and the actual hardware.
- **Existing installations keep saved settings.** Open Settings, select **GPU first (RAM fallback)**, click **Apply preset**, and restart the model to adopt the new configuration.
- **Large MoE (low VRAM)** remains a separate preset that forces MoE expert tensors into CPU RAM (`--cpu-moe`). Because that can leave GPU memory unused, it is *not* the default maximize-VRAM preset.
- A 512 MiB reserve is a starting point, not a guarantee of zero out-of-memory errors. Raise it to 1024 MiB or reduce context length if needed. Close other GPU applications first.

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

## Feature comparison and release status

| Capability | v0.7 availability |
| --- | --- |
| GUI / local chat / model downloader / GPU offloading / MoE controls | Existing desktop features |
| Hugging Face GGUF catalog refresh | Existing desktop feature |
| Multi-user browser chat / private sessions / personal API keys | New Team Hub alpha |
| Document chat | Keyword-based retrieval (TXT/MD/DOCX, optional text PDF) |
| OpenAI-compatible local API and Python integration | Basic chat and model endpoints |
| Offline inference and optional headless operation | Supported with downloaded engine/model |
| Docker | Not required |
| Native no-Python signed installer | Not yet available |
| Production-grade HTTPS, SSO, vector RAG | Not yet available |

## Roadmap

- [ ] Fully bundled and signed Windows installer
- [ ] Verified automatic MoE benchmarking and memory advisor
- [ ] Split GGUF shard management and cryptographic download verification
- [ ] Model licenses and compatibility information in the browser
- [ ] Tested inference builds across 4–12 GB NVIDIA VRAM
- [ ] Optional local RAG/document chat

## Documents

[Team Hub](docs/TEAM_HUB.md) · [API](docs/API.md) · [Architecture](docs/ARCHITECTURE.md) · [Product audit](docs/PRODUCT_AUDIT.md) · [Release checklist](docs/RELEASE_CHECKLIST.md) · [Contributing](docs/CONTRIBUTING.md) · [Security](SECURITY.md)

## Licensing

Original Local MoE Studio application code in this repository is offered under the [MIT License](LICENSE). Redistribution of llama.cpp, drivers/runtime libraries, or model weights is governed by their separate license obligations.
