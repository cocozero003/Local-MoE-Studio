"""Measure locally-served llama.cpp models without saving prompts or responses.

Usage:
  python scripts/benchmark_local.py --url http://127.0.0.1:8081 --model local
  python scripts/benchmark_local.py --url http://127.0.0.1:8080 --model strata

Compare the SAME model, quantization, context, and prompt lengths whenever
claiming an engine performance improvement.
"""
import argparse
import json
import statistics
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


TESTS = (
    ("short_en", "Explain the difference between a dense model and a mixture-of-experts model."),
    ("short_th", "อธิบายความแตกต่างระหว่างการประเมินความปลอดภัยและประสิทธิผลของผลิตภัณฑ์สุขภาพ"),
    ("long_context", (
        "Read the following synthetic verification note and summarize its validation "
        "steps without inventing evidence.\n" +
        ("Section: identity, quality, risk, version and source checks. "
         "Evidence must be confirmed against the original record.\n" * 120)
    )),
)


def run_request(url, model, prompt):
    data = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "stream": False,
        "max_tokens": 192,
    }, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url.rstrip("/") + "/v1/chat/completions", data=data,
        headers={"Content-Type": "application/json"}, method="POST"
    )
    begin = time.perf_counter()
    with urllib.request.urlopen(request, timeout=600) as response:
        result = json.load(response)
    elapsed = time.perf_counter() - begin
    timings = result.get("timings") or {}
    usage = result.get("usage") or {}
    return {
        "wall_seconds": round(elapsed, 3),
        "prompt_tokens": usage.get("prompt_tokens", timings.get("prompt_n")),
        "output_tokens": usage.get("completion_tokens", timings.get("predicted_n")),
        "prompt_tokens_per_second": timings.get("prompt_per_second"),
        "generation_tokens_per_second": timings.get("predicted_per_second"),
    }


def discover_model(url):
    """Resolve the actual model identifier advertised by the local server."""
    endpoint = url.rstrip("/") + "/v1/models"
    with urllib.request.urlopen(endpoint, timeout=15) as response:
        payload = json.load(response)
    items = payload.get("data") or []
    if not items or not isinstance(items[0].get("id"), str):
        raise ValueError("No model listed by the local server.")
    return items[0]["id"]


def main():
    parser = argparse.ArgumentParser(description="Local 8GB inference benchmark")
    parser.add_argument("--url", default="http://127.0.0.1:8081")
    parser.add_argument("--model", default="auto", help="auto reads /v1/models")
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--output", default="benchmark_local.json")
    args = parser.parse_args()
    if not 1 <= args.runs <= 20:
        parser.error("--runs must be from 1 to 20")
    try:
        model = discover_model(args.url) if args.model == "auto" else args.model
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError) as exc:
        raise SystemExit(f"Cannot discover local model: {exc}") from exc
    data = {
        "time_utc": datetime.now(timezone.utc).isoformat(),
        "endpoint": args.url,
        "model": model,
        "runs_per_case": args.runs,
        "note": "No prompt text or generated content is persisted. "
                "Wall time includes request overhead and is not pure decode speed.",
        "cases": [],
    }
    for label, prompt in TESTS:
        observations = []
        for number in range(args.runs):
            try:
                item = run_request(args.url, model, prompt)
            except (urllib.error.URLError, TimeoutError, ValueError, KeyError) as exc:
                raise SystemExit(f"Benchmark stopped during {label}: {exc}") from exc
            observations.append(item)
            print(f"{label} run {number + 1}: {item['wall_seconds']} s")
        output = {"name": label, "observations": observations}
        for key in ("wall_seconds", "prompt_tokens_per_second",
                    "generation_tokens_per_second"):
            values = [x[key] for x in observations
                      if isinstance(x.get(key), (float, int)) and x[key] > 0]
            output[key + "_median"] = round(statistics.median(values), 3) if values else None
        data["cases"].append(output)
    Path(args.output).write_text(json.dumps(data, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
    print(f"Saved statistics only: {args.output}")


if __name__ == "__main__":
    main()
