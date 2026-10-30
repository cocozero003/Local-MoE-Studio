# Thai FDA precedent mode

This optional mode integrates the V3.16/V3.17 precedent engine into the existing Local MoE Studio Team Hub.

## Runtime flow

New case -> conservative pre-decision extraction -> V3.16 Hybrid retrieval -> V3.17 Top-5 portfolio -> local llama.cpp reasoning -> human review.

Current law remains primary. Historical precedent is supporting evidence, not law.

## Install on Windows

1. Keep the controlled V3.17 local data ZIP on the host PC.
2. Drag the ZIP onto `SETUP_THAI_FDA_WINDOWS.bat`, or run:

```bat
SETUP_THAI_FDA_WINDOWS.bat "C:\path\to\Thai_FDA_Precedent_Assistant_Local_V317_20261030.zip"
```

The installer:
- installs the optional Python dependencies from `.[thai-fda]`;
- copies only runtime data to `%LOCALAPPDATA%\LocalMoEStudio\thai_fda_precedent`;
- keeps a previous data folder as `thai_fda_precedent.previous`.

Then start a GGUF model in the desktop application and run `START_TEAM_HUB_WINDOWS.bat`.

## Team Hub

Open `http://127.0.0.1:8765` and choose **Thai FDA precedent** in the Chat mode selector.

You can combine it with **Search my uploaded documents**. This is the recommended law-first workflow when the uploaded document library contains current laws, notifications or guidance: the model receives the current document excerpts plus the historical precedent portfolio and is explicitly instructed that current law outranks precedent.

## API

Authenticated browser endpoint:

```text
GET  /api/fda/status
POST /api/fda/analyze
```

Example analysis body:

```json
{
  "text": "รายละเอียดผลิตภัณฑ์...",
  "cutoff_year": 2026,
  "retrieval_mode": "classification",
  "top_k": 5
}
```

OpenAI-compatible chat requests can opt in using:

```json
{
  "model": "local",
  "messages": [{"role":"user","content":"ช่วยวินิจฉัย..."}],
  "thai_fda": true,
  "fda_cutoff_year": 2026,
  "fda_retrieval_mode": "classification"
}
```

## Data safety

The controlled historical corpus, decision table and fitted retrieval artifacts are not committed to GitHub. They remain under the Windows user profile unless `LOCALMOE_FDA_DATA` explicitly points elsewhere.

## Validation status

V3.17 post-hoc diagnostic Hit@5 proxy was 90.5% on 105 Silver cases. This is a same-historical-class proxy, not expert relevance Gold and not autonomous classification accuracy.
