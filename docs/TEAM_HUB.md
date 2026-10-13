# Local MoE Studio Team Hub (v0.7 alpha)

Team Hub is a lightweight self-hosted web application using **the same llama.cpp server** as the Windows desktop GUI. It is intended for one desktop administrator and a small number of colleagues on a trusted private network. No Docker is needed. The desktop interface remains responsible for installing llama.cpp, downloading GGUF files, configuring offloading, and choosing the active model.

## Start: personal/private (default)

1. In the desktop application, **Models → Install llama.cpp**, then download a GGUF model.
2. Use **Settings → Large MoE (low VRAM)** if appropriate; start the model, and wait until it is ready.
3. Click **Open Team Hub** in the sidebar. Team Hub opens at `http://127.0.0.1:8765`.
4. On the server computer, create the first administrator account (minimum password length: 12).
5. In **Team members**, create separate usernames and temporary passwords. Share credentials through a secure channel.
6. Each colleague can use their own private chat and document library.

## Share with another computer on the same trusted network

1. **Do not enable this for confidential data** without a protected network and appropriate transport security.
2. On the host computer, tick **Share on private LAN** before clicking **Open Team Hub**; confirm the warning. Restart the desktop app to change the binding mode later.
3. Find the host computer's private IPv4 address with `ipconfig` (example `192.168.1.40`).
4. If appropriate, configure a Windows Firewall rule allowing TCP port **8765** *only from the trusted LAN*. Do not expose the llama.cpp backend port (default 8081); it stays bound to `127.0.0.1`.
5. On a client, navigate to `http://192.168.1.40:8765`, replacing the example IP. Sign in with an account the admin created.

**Security limitations:** Team Hub currently uses **HTTP, not HTTPS**. Do not expose it to the public internet, use on untrusted Wi-Fi, or rely on it for sensitive regulated data. Use an authenticated reverse proxy with TLS and carry out a proper security review before broader deployment. Sessions and API tokens are hashed in SQLite, while chats and document contents are **not encrypted at rest**. Local administrators who can read the SQLite database or backups can read those records.

## Headless mode

For background hosting without opening the desktop GUI, first configure and save the model and llama.cpp path from the desktop app. Then use:

- `START_TEAM_HUB_WINDOWS.bat` — host-only, localhost access.
- `START_TEAM_HUB_LAN_WINDOWS.bat` — opt-in private LAN mode, HTTP only.

Both scripts start llama.cpp with the saved GPU/MoE settings and then start Team Hub. Stop the batch script with Ctrl+C. The scripts require Python already installed; a signed consumer installer is future work. Do not run the desktop server and headless server simultaneously on the same ports.

## Features and limitations

| Capability | v0.7 status |
|---|---|
| Local multi-user accounts | Implemented (admin and member) |
| User-isolated conversation history | Implemented |
| Text and Markdown documents | Implemented |
| DOCX document extraction | Implemented, text only |
| PDF extraction | Optional `pypdf` (`py -m pip install pypdf`); scanned PDF/OCR not included |
| Local document search | Implemented, SQLite trigram/keyword; **not embedding/vector RAG** |
| Document-grounded AI answers | Supported with retrieved excerpts and source labels, not guaranteed factual accuracy |
| OpenAI-compatible API | Basic `/v1/models` and `/v1/chat/completions`, bearer API key |
| Streaming responses | Browser chat + OpenAI SSE |
| GPU concurrency control | One inference request at a time; waiting request times out |
| MoE CPU expert offloading | Via existing llama.cpp desktop controls |
| Auto-refresh model catalog | Existing desktop feature; model metadata only |
| Per-user storage encryption | Not implemented |
| HTTPS / SSO / enterprise access control | Not implemented |
| Vector RAG, hybrid ranking and OCR | Not implemented |
| Signed installer / automatic app updater | Not implemented |

## Data and backup

By default, Windows user data lives under `%LOCALAPPDATA%\LocalMoEStudio`:

- `team/team.sqlite3`: users, hashed sessions/API tokens, conversations, document text/chunks
- `models/`: user-downloaded models managed by the desktop app
- `settings.json`: selected engine and inference settings

Backup while the application is **stopped** to avoid copying a SQLite database without its current WAL. If running, use SQLite's backup API instead. Treat backups as sensitive documents.
