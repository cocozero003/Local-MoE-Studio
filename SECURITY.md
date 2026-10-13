# Security — Local MoE Studio

This repository remains **alpha software** and has not undergone an external security assessment. Team Hub is designed for local development and controlled pilot testing, not internet exposure or clinical/regulated-data production.

## Security protections in the Team Hub prototype

- Inference backend restricted to `127.0.0.1`, with no direct unauthenticated LAN API.
- First administrator setup permitted only from the server computer's loopback address.
- Per-user accounts with salted PBKDF2-SHA256 password hashes (390,000 iterations).
- Hashed login session tokens and personal API keys; HttpOnly/SameSite cookies.
- CSRF token on browser write requests and Origin/Host validation.
- Login throttling, size limits for uploads, separate user-owned conversations and documents.
- Documents treated as **untrusted reference material** for model prompts, not commands.
- No analytics or intentional upload of chat contents to external AI APIs.

## Limitations

- Team Hub on a LAN is **HTTP, not HTTPS**. Never expose port 8765 to the internet or untrusted Wi-Fi. Provide TLS reverse proxy / firewall rules before broader use.
- Conversations and extracted document text in the SQLite database are **not encrypted at rest**; machine accounts and backups must be protected.
- No enterprise SSO, recovery flow, password reset, MFA, audit system, tenant isolation or formal penetration test.
- Current document retrieval is lexical and may miss relevant evidence; document-grounded answers still require verification.
- Remote inference time and resources are shared; memory constraints and host availability apply.
- The one-click engine installer downloads and executes upstream release binaries. Verify sources, release digests and licensing.
- Hugging Face and GitHub network requests occur for catalog/engine downloads; disable catalog auto-refresh if offline-only operation is required.

Please report vulnerabilities using a private GitHub security advisory rather than a public issue.
