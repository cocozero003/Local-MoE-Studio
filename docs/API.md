# Local MoE Studio Team Hub API (v0.7 alpha)

## Authentication

Log into the local Team Hub web interface at `http://127.0.0.1:8765`; open **API access → Create API key**. The raw key appears **once** and starts with `lms_`. Use `Authorization: Bearer <API_KEY>` when calling the API. Keys can be revoked in the web UI. **Never commit an API key to Git.**

The OpenAI-compatible subset is:

- `GET /v1/models`
- `POST /v1/chat/completions` with text-based `messages` and optional `stream` flag
- Experimental extension: `"rag": true` to include the caller's indexed private document excerpts

The API does not yet implement multimodal requests, embeddings, responses, tools/functions, or all OpenAI parameters.

## Example using Python standard library

Set an environment variable `LOCAL_MOE_API_KEY` to your key. Then:

```python
import json
import os
import urllib.request

base = "http://127.0.0.1:8765/v1/chat/completions"
payload = {
    "model": "local",  # the currently loaded GGUF model on the server
    "messages": [{"role": "user", "content": "Explain MoE CPU offloading."}],
    "stream": False,
    "rag": False,
}
request = urllib.request.Request(
    base,
    data=json.dumps(payload).encode("utf-8"),
    headers={
        "Authorization": "Bearer " + os.environ["LOCAL_MOE_API_KEY"],
        "Content-Type": "application/json",
    },
    method="POST",
)
with urllib.request.urlopen(request, timeout=300) as response:
    print(json.load(response)["choices"][0]["message"]["content"])
```

Chat requests are serialized so only one runs on the shared inference backend at a time. If the queue times out, the server returns HTTP 503.

**Security:** The API defaults to localhost; a remote HTTP connection may expose the API key to passive observers. Use a trusted private network only and HTTPS in any production deployment.
