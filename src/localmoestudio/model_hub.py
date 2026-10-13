"""GGUF model discovery and resumable downloads. Standard library only.
Network access: huggingface.co for user-requested model queries/downloads.
"""
import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path

CATALOG = [
    ("Qwen3 30B-A3B (MoE)", "Qwen/Qwen3-30B-A3B-GGUF", "30B total / 3B active; recommend Q4"),
    ("Qwen3 8B (dense)", "Qwen/Qwen3-8B-GGUF", "Smaller model; fewer CPU offloaded weights"),
    ("Qwen3 14B (dense)", "Qwen/Qwen3-14B-GGUF", "Mid-size model"),
    ("Qwen3 32B (dense)", "Qwen/Qwen3-32B-GGUF", "Large dense model; CPU-heavy on 6 GB"),
    ("Custom Hugging Face repo", "", "Enter namespace/repository below"),
]

UA = "LocalMoEStudio/3 (local desktop model manager)"

def _get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=25) as response:
        return json.load(response)

def validate_repo(repo):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*", repo):
        raise ValueError("Enter a Hugging Face repository like Qwen/Qwen3-30B-A3B-GGUF")
    return repo

def list_gguf_files(repo):
    repo = validate_repo(repo)
    url = "https://huggingface.co/api/models/" + repo + "/tree/main?recursive=true&expand=false"
    result = _get_json(url)
    files = []
    for item in result:
        p = item.get("path", "")
        if item.get("type") == "file" and p.lower().endswith(".gguf"):
            if p.startswith("/") or ".." in Path(p).parts:
                continue
            size = item.get("size") or (item.get("lfs") or {}).get("size") or 0
            files.append({"path": p, "size": size})
    return sorted(files, key=lambda f: f['path'].lower())

def human_size(n):
    if not n:
        return "Unknown size"
    return f"{n / (1024 ** 3):.2f} GiB"

def download_file(repo, file_path, target_dir, progress, cancel):
    repo = validate_repo(repo)
    rel = Path(file_path)
    if rel.is_absolute() or ".." in rel.parts or rel.suffix.lower() != ".gguf":
        raise ValueError("Invalid GGUF path")
    dest_dir = Path(target_dir).resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)
    # Use one folder per repo, flatten the repository-relative filename with safe basename.
    subdir = dest_dir / repo.replace('/', '__')
    subdir.mkdir(parents=True, exist_ok=True)
    dest = subdir / rel.name
    temp = dest.with_name(dest.name + '.part')
    url = "https://huggingface.co/" + repo + "/resolve/main/" + urllib.parse.quote(file_path, safe='/') + "?download=true"
    existing = temp.stat().st_size if temp.exists() else 0
    headers = {"User-Agent": UA}
    if existing:
        headers["Range"] = f"bytes={existing}-"
    req = urllib.request.Request(url, headers=headers)
    try:
        resp = urllib.request.urlopen(req, timeout=60)
    except urllib.error.HTTPError as exc:
        if exc.code == 416 and temp.exists():
            raise RuntimeError("Partial file is not resumable. Delete the .part file, then retry.") from exc
        raise
    with resp:
        # Server may ignore the range request. Restart instead of duplicating bytes.
        continuing = resp.status == 206 and existing > 0
        pos = existing if continuing else 0
        total_header = resp.headers.get('Content-Range', '')
        try:
            total = int(total_header.split('/')[-1]) if continuing and '/' in total_header else int(resp.headers.get('Content-Length', '0'))
        except ValueError:
            total = 0
        mode = 'ab' if continuing else 'wb'
        with open(temp, mode) as out:
            while True:
                if cancel.is_set():
                    progress('cancelled', pos, total)
                    return None
                chunk = resp.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                pos += len(chunk)
                progress('progress', pos, total)
    if total and pos != total:
        raise IOError(f"Incomplete download: {pos} of {total} bytes; retry to resume")
    os.replace(temp, dest)
    progress('complete', pos, total)
    return dest
