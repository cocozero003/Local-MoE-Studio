# Public-release checklist

## Required before public beta

- [ ] Full install and inference test on Windows 10/11 NVIDIA 4 GB, 6 GB, 8 GB and CPU-only systems.
- [ ] Pin/test compatible llama.cpp release versions and implement tested update rollback.
- [ ] Verify split GGUF downloads and file integrity using reliable cryptographic hashes where provided.
- [ ] Model eligibility check and model license disclosure before downloading.
- [ ] Sign binaries and installer; test SmartScreen behavior on clean Windows systems.
- [ ] Add test coverage for failed/cancelled downloads, interrupted upgrades, safe extraction, subprocess shutdown, and API error handling.
- [ ] Independent security review (local API binding, archive handling, file access, update trust).
- [ ] Accessible onboarding, startup diagnostics, and actionable out-of-memory errors.
- [ ] Confirm third-party licensing and bundled notices (llama.cpp/CUDA/etc.).
- [ ] Publish privacy policy, support channels, security disclosure policy and versioned release notes.

## Not in v0.5

- Production Windows setup.exe/msi, automatic app self-updates, automatic model benchmarking, robust GGUF shard support.
- Guaranteed MoE/GPU load success across NVIDIA cards.
- RAG, file indexing, secured multi-user API, telemetry or crash reporting.
