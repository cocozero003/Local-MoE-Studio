"""Hugging Face GGUF catalog and resumable downloads.

Catalog metadata refreshes on startup with explicit fallback to an offline cache.
Only a separate, user-confirmed action downloads model weights.
Standard-library only; no telemetry.
"""
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from collections import defaultdict
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path

FAMILIES = ('All', 'Gemma', 'Qwen', 'Llama', 'Mistral', 'DeepSeek', 'Phi', 'GPT-OSS', 'Other')
# Search terms rather than a closed model allowlist. New releases appear without app updates.
FAMILY_QUERIES = ('gemma', 'qwen', 'llama', 'mistral', 'deepseek', 'phi', 'gpt-oss', 'gguf')

CATALOG = [
    ("Qwen3 30B-A3B (MoE)", "Qwen/Qwen3-30B-A3B-GGUF", "30B total / 3B active; recommend Q4"),
    ("Qwen3 8B (dense)", "Qwen/Qwen3-8B-GGUF", "Smaller model; fewer CPU offloaded weights"),
    ("Qwen3 14B (dense)", "Qwen/Qwen3-14B-GGUF", "Mid-size model"),
    ("Qwen3 32B (dense)", "Qwen/Qwen3-32B-GGUF", "Large dense model; CPU-heavy on 6 GB"),
    ("Gemma 3 12B (Unsloth)", "unsloth/gemma-3-12b-it-GGUF", "Community quantization. Check the Gemma license."),
    ("Llama 3.1 8B (bartowski)", "bartowski/Meta-Llama-3.1-8B-Instruct-GGUF", "Community quantization. Check the Meta Llama license."),
    ("Mistral Small 3.1 24B", "bartowski/mistralai_Mistral-Small-3.1-24B-Instruct-2503-GGUF", "Community quantization of Mistral Small 3.1."),
    ("DeepSeek R1 Distill 14B", "unsloth/DeepSeek-R1-Distill-Qwen-14B-GGUF", "Community quantization; dense model."),
    ("Phi 4 14B (Microsoft)", "microsoft/phi-4-gguf", "Microsoft Phi 4 GGUF; check model requirements."),
    ("GPT-OSS 20B (Unsloth)", "unsloth/gpt-oss-20b-GGUF", "Community quantization. MoE reasoning model."),
    ("Custom Hugging Face repo", "", "Enter owner/repository below"),
]

UA = "LocalMoEStudio/0.6 (local desktop model browser)"

def _get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=25) as response:
        return json.load(response)

def validate_repo(repo):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*", repo):
        raise ValueError("Enter a Hugging Face repository like Qwen/Qwen3-30B-A3B-GGUF")
    return repo

def model_family(repo_id):
    """Classify by ID without relying on untrusted display metadata."""
    model = repo_id.split('/')[-1].lower()
    if 'gemma' in model: return 'Gemma'
    if 'qwen' in model: return 'Qwen'
    if 'llama' in model: return 'Llama'
    if 'mistral' in model or 'ministral' in model or 'mixtral' in model: return 'Mistral'
    if 'deepseek' in model: return 'DeepSeek'
    if re.search(r'(^|[-_])phi([0-9-_]|$)', model): return 'Phi'
    if 'gpt-oss' in model or 'gpt_oss' in model: return 'GPT-OSS'
    return 'Other'


def normalize_model(record):
    """Validate and normalize a public GGUF repository from Hugging Face API."""
    if not isinstance(record, dict): return None
    repo = record.get('id') or record.get('modelId')
    try: validate_repo(repo)
    except (ValueError, TypeError): return None
    if record.get('private') or record.get('gated') not in (None, False):
        return None  # No token/account flow in this version.
    tags = record.get('tags') or []
    if not isinstance(tags, list): tags = []
    if 'gguf' not in repo.lower() and not any('gguf' in str(tag).lower() for tag in tags):
        return None
    # lastModified may reflect a README update rather than new model weights.
    modified = str(record.get('lastModified') or '')[:10]
    try: downloads = max(0, int(record.get('downloads') or 0))
    except (TypeError, ValueError): downloads = 0
    return {'id': repo, 'family': model_family(repo), 'downloads': downloads,
            'updated': modified, 'source': 'Hugging Face', 'gated': False}


def seed_catalog():
    """Verified example repositories; shown until the first online refresh."""
    return [normalize_model({'id':repo, 'tags':['gguf'], 'downloads':0})
            for _,repo,_ in CATALOG if repo]


def search_hub_models(query, limit=80):
    """Search current public GGUF repositories; no weights are downloaded."""
    query = str(query or '').strip()
    if len(query) > 120: raise ValueError('Search phrase is too long')
    params = {'filter': 'gguf', 'sort': 'lastModified', 'direction': '-1',
              'limit': str(max(1, min(100, int(limit))))}
    if query: params['search'] = query
    url = 'https://huggingface.co/api/models?' + urllib.parse.urlencode(params)
    data = _get_json(url)
    if not isinstance(data, list): raise ValueError('Unexpected Hugging Face response')
    models = [normalize_model(x) for x in data]
    return [x for x in models if x is not None]


def discover_models(queries=FAMILY_QUERIES, per_query=60, max_models=350):
    """Refresh multiple model families concurrently to avoid family-specific blind spots.

    Returns (models, warnings), using successful queries even if another fails.
    Raises if *every* API query failed, allowing the UI to use a local cache.
    """
    unique = {}
    errors = []
    completed = 0
    query_list = list(dict.fromkeys(queries))
    if not query_list: return [], []
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = {pool.submit(search_hub_models, q, per_query): q for q in query_list}
        for future in as_completed(jobs):
            try:
                records = future.result()
                completed += 1
                for m in records:
                    unique.setdefault(m['id'].lower(), m)
            except Exception as exc:
                errors.append(f'{jobs[future]}: {exc}')
    if not completed:
        raise ConnectionError('Hugging Face model catalog unavailable: ' + '; '.join(errors[:3]))
    # Newest upload changes first. Choose Popular sort in the UI for downloads.
    models = sorted(unique.values(), key=lambda m:(m['updated'],m['downloads']),reverse=True)
    return models[:max_models], errors


def save_catalog_cache(path, models, fetched_at=None):
    """Atomically save harmless model *metadata* only, never credentials or weights."""
    p = Path(path)
    p.parent.mkdir(parents=True,exist_ok=True)
    payload = {'updated_at': fetched_at or datetime.now(timezone.utc).isoformat(),
               'models': [m for m in models if isinstance(m, dict)]}
    temp = p.with_name(p.name+'.tmp')
    temp.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    os.replace(temp,p)


def load_catalog_cache(path):
    p=Path(path)
    try:
        data=json.loads(p.read_text(encoding='utf-8'))
        if not isinstance(data,dict) or not isinstance(data.get('models'),list):
            return [], ''
        rows=[]
        for m in data['models'][:2000]:
            if not isinstance(m,dict): continue
            normalized=normalize_model({'id':m.get('id'), 'downloads':m.get('downloads'),
                                        'lastModified':m.get('updated'), 'tags':['gguf']})
            if normalized: rows.append(normalized)
        return rows, str(data.get('updated_at') or '')
    except (OSError,ValueError,TypeError):
        return [], ''


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
