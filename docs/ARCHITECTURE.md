# Architecture

```text
Windows desktop (Tkinter)
   |-- Chat -> loopback HTTP -> llama-server.exe (llama.cpp CUDA / CPU)
   |-- Models -> Hugging Face public GGUF listing / downloader
   |-- Engine -> official GitHub llama.cpp release installer
   |-- Settings -> Windows user profile / LocalMoEStudio
   `-- Sessions -> local JSON conversation files
```

## Modules

- `app.py`: screens, workflows, background tasks.
- `gui_v2.py`: shared desktop widgets.
- `backend.py`: subprocess and local model API communication.
- `engine_installer.py`: GitHub release selection, download and extraction.
- `model_hub.py`: Hugging Face GGUF discovery and model downloads.
- `profiles.py`: beginner performance presets.
- `sessions.py`: local chat history.

## Known risks

See [Release checklist](RELEASE_CHECKLIST.md). The model browser currently supports single-file GGUF downloads; multi-file shards require additional engineering.
