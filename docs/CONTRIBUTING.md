# Contributing

This is an alpha-stage reference application. Please open an issue before large changes.

## Local development

```powershell
py -3 -m venv .venv
.venv\Scripts\python -m pip install -e .
.venv\Scripts\python -m unittest discover -s tests -v
.venv\Scripts\python -m localmoestudio
```

Do not commit GGUF files, downloads, user conversations, credentials, release archives or GPU-specific caches.
Submit tests for bug fixes. Avoid copying LM Studio/Ollama branding or UI assets.
