# Windows setup (development preview)

1. Install **Python 3.11 or 3.12** (with the Windows `py` launcher).
2. Download this repository as a ZIP and extract it.
3. Double-click `START_WINDOWS.bat` or run `py -3 -m pip install -e .` then `local-moe-studio`.
4. Go to **Models** and choose **Install / Update llama.cpp**. Choose the CUDA package compatible with your NVIDIA driver or CPU mode.
5. Choose a public Hugging Face repository, discover GGUF files and download a **single-file** model.
6. Go to **Settings** and apply **Large MoE (low VRAM)** for supported MoE GGUF models. Then start the model.

The app only contacts GitHub or Hugging Face when you initiate online install/model discovery/download. Local model inference uses llama.cpp bound to localhost.

**Important:** The source-based launcher still requires Python. The developer EXE build in `scripts/build_windows.bat` is unsigned and is not a production-grade installer. Actual GPU inference and full downloads remain unverified.

### When another app uses GPU memory

Stop heavy models in Ollama or LM Studio before testing a large llama.cpp MoE model. You do not need to uninstall either app.

### Diagnostics

Run `nvidia-smi` to inspect NVIDIA GPU/driver. See **Server logs** inside the app for llama.cpp startup failures. Start with context 4096 or lower if memory is tight.
