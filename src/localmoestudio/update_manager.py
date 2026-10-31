"""Safe Thai FDA data-pack and Local MoE Studio update management."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path

from .backend import USER_DATA
from .thai_fda import FDA_DATA, get_service

GITHUB_REPO = "cocozero003/Local-MoE-Studio"
MAX_DATA_PACK = 32 * 1024 * 1024
MAX_PATCH_PACK = 20 * 1024 * 1024
DATA_REQUIRED = [
    "retrieval_index.csv",
    "predecision_features.csv",
    "cases.csv",
    "precedent_decisions_sanitized.csv",
    "model_config_v316.json",
    "artifacts/case_order.csv",
    "artifacts/tfidf_vectorizer.joblib",
    "artifacts/tfidf_matrix.npz",
]
DATA_CSV_HEADERS = {
    "retrieval_index.csv": {"case_id","product_case_id","year"},
    "predecision_features.csv": {"case_id","agenda_predecision","details_predecision"},
    "cases.csv": {"case_id","product_case_id"},
    "precedent_decisions_sanitized.csv": {"case_id","decision_status","final_class_auto_silver"},
}
SOFTWARE_BACKUPS = USER_DATA / "software_backups"
INCOMING = USER_DATA / "thai_fda_incoming"


def _safe_extract(raw: bytes, destination: Path, *, max_files: int = 2000, max_unpacked: int = 512 * 1024 * 1024):
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        infos=zf.infolist()
        if len(infos)>max_files:
            raise ValueError("Archive contains too many files")
        total=sum(max(0,i.file_size) for i in infos)
        if total>max_unpacked:
            raise ValueError("Archive expands beyond the allowed size")
        root=destination.resolve()
        for info in infos:
            target=(destination / info.filename).resolve()
            if root not in target.parents and target != root:
                raise ValueError("Archive contains an unsafe path")
        zf.extractall(destination)


def _find_data_root(extracted: Path) -> Path:
    candidates=[extracted]
    candidates.extend(p for p in extracted.rglob("*") if p.is_dir())
    for root in candidates:
        if all((root / rel).is_file() for rel in DATA_REQUIRED):
            return root
    raise ValueError("Not a Thai FDA runtime data pack: required files are missing")


def _csv_header(path: Path) -> set[str]:
    with path.open("r",encoding="utf-8-sig",newline="") as f:
        return set(next(csv.reader(f),[]))


def validate_data_root(root: Path) -> dict:
    missing=[rel for rel in DATA_REQUIRED if not (root/rel).is_file()]
    if missing:
        raise ValueError("Missing runtime files: "+", ".join(missing))
    for rel,required in DATA_CSV_HEADERS.items():
        actual=_csv_header(root/rel)
        absent=required-actual
        if absent:
            raise ValueError(f"{rel} is missing columns: {', '.join(sorted(absent))}")
    for rel in ("artifacts/tfidf_vectorizer.joblib","artifacts/tfidf_matrix.npz"):
        if (root/rel).stat().st_size < 128:
            raise ValueError(rel+" is unexpectedly small")
    manifest={}
    for name in ("DATA_MANIFEST.json","manifest.json","MANIFEST.json"):
        p=root/name
        if p.is_file():
            try:
                manifest=json.loads(p.read_text(encoding="utf-8-sig"))
            except (OSError,ValueError):
                manifest={}
            break
    return {
        "ok":True,
        "version":str(manifest.get("data_version") or manifest.get("version") or "unversioned"),
        "manifest":manifest,
    }


def data_status(data_dir: Path | None = None) -> dict:
    root=Path(data_dir or FDA_DATA)
    manifest={}
    p=root/"DATA_MANIFEST.json"
    if p.is_file():
        try:manifest=json.loads(p.read_text(encoding="utf-8"))
        except (OSError,ValueError):manifest={}
    return {
        "data_dir":str(root),
        "installed":all((root/x).is_file() for x in DATA_REQUIRED),
        "data_version":manifest.get("data_version","unversioned"),
        "installed_at":manifest.get("installed_at"),
        "source":manifest.get("source",""),
        "backup_available":root.with_name(root.name+".previous").is_dir(),
        "incoming_dir":str(INCOMING),
    }


def install_data_pack(raw: bytes, filename: str = "data-pack.zip", data_dir: Path | None = None) -> dict:
    if not raw or len(raw)>MAX_DATA_PACK:
        raise ValueError("Data pack must be 1 byte to 32 MiB")
    root=Path(data_dir or FDA_DATA)
    root.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="lms_fda_data_") as td:
        extracted=Path(td)/"extract"
        extracted.mkdir()
        _safe_extract(raw,extracted,max_unpacked=512*1024*1024)
        source=_find_data_root(extracted)
        checked=validate_data_root(source)
        staging=root.with_name(root.name+".staging")
        if staging.exists():shutil.rmtree(staging)
        shutil.copytree(source,staging)
        manifest={
            "type":"thai_fda_runtime_data",
            "data_version":checked["version"] if checked["version"]!="unversioned" else time.strftime("%Y.%m.%d.%H%M%S"),
            "installed_at":time.strftime("%Y-%m-%dT%H:%M:%S"),
            "source":Path(filename).name,
            "sha256":hashlib.sha256(raw).hexdigest(),
        }
        (staging/"DATA_MANIFEST.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
        validate_data_root(staging)
        previous=root.with_name(root.name+".previous")
        if previous.exists():shutil.rmtree(previous)
        if root.exists():root.replace(previous)
        staging.replace(root)
    get_service.cache_clear()
    return data_status(root)


def rollback_data(data_dir: Path | None = None) -> dict:
    root=Path(data_dir or FDA_DATA)
    previous=root.with_name(root.name+".previous")
    if not previous.is_dir():
        raise ValueError("No previous Thai FDA data pack is available")
    validate_data_root(previous)
    failed=root.with_name(root.name+".rollback_replaced")
    if failed.exists():shutil.rmtree(failed)
    if root.exists():root.replace(failed)
    previous.replace(root)
    if failed.exists():failed.replace(previous)
    get_service.cache_clear()
    return data_status(root)


def stage_source_file(raw: bytes, filename: str) -> dict:
    if not raw or len(raw)>32*1024*1024:
        raise ValueError("Source file must be 1 byte to 32 MiB")
    name=Path(filename).name
    if Path(name).suffix.lower() not in {".csv",".xlsx",".zip",".json"}:
        raise ValueError("Accepted source files: CSV, XLSX, JSON or ZIP")
    INCOMING.mkdir(parents=True,exist_ok=True)
    dest=INCOMING/(time.strftime("%Y%m%d_%H%M%S")+"_")+name
    dest.write_bytes(raw)
    return {"staged":True,"path":str(dest),"note":"Staged only; rebuild a validated data pack before it affects retrieval."}


def _repo_root() -> Path:
    override=os.getenv("LOCALMOE_SOURCE_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


def _local_version() -> str:
    try:
        from . import __version__
        return str(__version__)
    except Exception:
        return "unknown"


def software_status() -> dict:
    root=_repo_root()
    commit=""
    git_dir=root/".git"
    if git_dir.exists():
        try:
            commit=subprocess.check_output(["git","-C",str(root),"rev-parse","HEAD"],text=True,timeout=5).strip()
        except Exception:
            commit=""
    return {
        "version":_local_version(),
        "source_root":str(root),
        "git_checkout":git_dir.exists(),
        "commit":commit,
        "backup_count":len(list(SOFTWARE_BACKUPS.glob("*"))) if SOFTWARE_BACKUPS.exists() else 0,
    }


def check_online_update() -> dict:
    url=f"https://api.github.com/repos/{GITHUB_REPO}/commits/main"
    req=urllib.request.Request(url,headers={"User-Agent":"Local-MoE-Studio-Updater"})
    with urllib.request.urlopen(req,timeout=12) as r:
        payload=json.load(r)
    local=software_status()
    remote=str(payload.get("sha",""))
    return {
        **local,
        "remote_commit":remote,
        "update_available":bool(remote and remote!=local.get("commit")),
        "remote_message":payload.get("commit",{}).get("message",""),
    }


def _backup_paths(root: Path, paths: list[Path]) -> Path:
    SOFTWARE_BACKUPS.mkdir(parents=True,exist_ok=True)
    backup=SOFTWARE_BACKUPS/time.strftime("%Y%m%d_%H%M%S")
    for src in paths:
        if not src.exists():continue
        rel=src.relative_to(root)
        dest=backup/rel
        dest.parent.mkdir(parents=True,exist_ok=True)
        if src.is_dir():shutil.copytree(src,dest)
        else:shutil.copy2(src,dest)
    return backup


def _apply_source_tree(source_root: Path, target_root: Path) -> dict:
    allowed=[
        Path("src/localmoestudio"),
        Path("START_WINDOWS.bat"),
        Path("START_TEAM_HUB_WINDOWS.bat"),
        Path("START_THAI_FDA_TEAM_HUB_WINDOWS.bat"),
        Path("pyproject.toml"),
        Path("README.md"),
    ]
    existing=[target_root/p for p in allowed if (target_root/p).exists()]
    backup=_backup_paths(target_root,existing)
    copied=[]
    for rel in allowed:
        src=source_root/rel
        if not src.exists():continue
        dest=target_root/rel
        if src.is_dir():
            if dest.exists():shutil.rmtree(dest)
            dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copytree(src,dest)
        else:
            dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(src,dest)
        copied.append(str(rel).replace("\\","/"))
    return {"backup":str(backup),"copied":copied,"restart_required":True}


def apply_online_update() -> dict:
    root=_repo_root()
    url=f"https://github.com/{GITHUB_REPO}/archive/refs/heads/main.zip"
    req=urllib.request.Request(url,headers={"User-Agent":"Local-MoE-Studio-Updater"})
    with urllib.request.urlopen(req,timeout=30) as r:
        raw=r.read(25*1024*1024+1)
    if len(raw)>25*1024*1024:
        raise ValueError("Online source archive is unexpectedly large")
    with tempfile.TemporaryDirectory(prefix="lms_update_") as td:
        dest=Path(td)/"extract";dest.mkdir()
        _safe_extract(raw,dest,max_files=5000,max_unpacked=200*1024*1024)
        roots=[p for p in dest.iterdir() if p.is_dir()]
        if len(roots)!=1 or not (roots[0]/"src/localmoestudio").is_dir():
            raise ValueError("Downloaded source archive is invalid")
        result=_apply_source_tree(roots[0],root)
    return {**result,"source":"github-main","sha256":hashlib.sha256(raw).hexdigest()}


def apply_patch_pack(raw: bytes, filename: str = "software-patch.zip") -> dict:
    if not raw or len(raw)>MAX_PATCH_PACK:
        raise ValueError("Software patch must be 1 byte to 20 MiB")
    root=_repo_root()
    with tempfile.TemporaryDirectory(prefix="lms_patch_") as td:
        dest=Path(td)/"extract";dest.mkdir()
        _safe_extract(raw,dest,max_files=5000,max_unpacked=200*1024*1024)
        candidates=[dest]+[p for p in dest.iterdir() if p.is_dir()]
        source=next((p for p in candidates if (p/"src/localmoestudio").is_dir()),None)
        if source is None:
            raise ValueError("Patch does not contain src/localmoestudio")
        result=_apply_source_tree(source,root)
    return {**result,"source":Path(filename).name,"sha256":hashlib.sha256(raw).hexdigest()}
