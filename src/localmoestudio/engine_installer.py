"""Install upstream llama.cpp Windows release archives with integrity and safe extraction.
Standard library only. No elevated permissions or shell scripts.
"""
import hashlib
import json
import os
import re
import shutil
import tempfile
import urllib.request
import urllib.error
import zipfile
from pathlib import Path

API = 'https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=15'
UA = 'LocalMoEStudio/4 (+https://github.com/ggml-org/llama.cpp)'


def choose_release_assets(releases, mode='cuda12'):
    if mode not in ('cuda12', 'cuda13', 'cpu'):
        raise ValueError('Unknown engine type')
    for release in releases:
        if release.get('draft') or release.get('prerelease'):
            continue
        assets = release.get('assets', [])
        names = [(a, a.get('name','').lower()) for a in assets]
        if mode == 'cpu':
            candidates = [a for a,n in names if re.search(r'^(?:llama-)?b\d+-bin-win-cpu-x64\.zip$', n)]
            if not candidates:
                candidates = [a for a,n in names if 'bin-win-cpu-x64.zip' in n and 'cudart' not in n]
            if candidates:
                return release.get('tag_name', 'unknown'), [candidates[0]]
        else:
            digit = '12' if mode=='cuda12' else '13'
            main = [a for a,n in names if ('bin-win-cuda-' + digit) in n and n.endswith('-x64.zip') and not n.startswith('cudart-')]
            runtime = [a for a,n in names if n.startswith('cudart-') and ('bin-win-cuda-' + digit) in n and n.endswith('-x64.zip')]
            if main and runtime:
                # Prefer matching minor CUDA versions.
                def ver(a):
                    m = re.search(r'cuda-(\d+(?:\.\d+)?)', a['name'].lower())
                    return m.group(1) if m else ''
                runtime = [a for a in runtime if ver(a)==ver(main[0])] or runtime
                return release.get('tag_name','unknown'), [main[0], runtime[0]]
    raise RuntimeError('No matching official Windows archive found. Try another backend or check GitHub releases.')


def releases_json():
    req = urllib.request.Request(API,headers={'User-Agent':UA,'Accept':'application/vnd.github+json'})
    with urllib.request.urlopen(req,timeout=25) as resp:
        return json.load(resp)


def sha256_expected(asset):
    # GitHub release API includes digest on newer uploads; older assets may omit it.
    d = asset.get('digest') or ''
    return d.partition(':')[2].lower() if d.startswith('sha256:') else None


def stream_archive(asset, dest, progress, cancel):
    url = asset.get('browser_download_url','')
    if not url.startswith('https://github.com/ggml-org/llama.cpp/releases/download/'):
        raise ValueError('Refusing an asset URL outside official llama.cpp releases')
    request=urllib.request.Request(url,headers={'User-Agent':UA})
    expected = asset.get('size') or 0
    check = hashlib.sha256()
    actual = 0
    with urllib.request.urlopen(request,timeout=90) as resp, open(dest,'wb') as output:
        while True:
            if cancel.is_set():
                raise InterruptedError('Installation cancelled')
            chunk=resp.read(1024*1024)
            if not chunk: break
            output.write(chunk)
            check.update(chunk)
            actual+=len(chunk)
            progress('Downloading '+asset['name'], actual, expected)
    if expected and expected != actual:
        raise IOError(f'Incomplete download: got {actual} bytes, expected {expected}')
    digest=sha256_expected(asset)
    if digest and digest != check.hexdigest():
        raise IOError('SHA-256 mismatch for '+asset['name'])
    return digest is not None


def unzip_safe(zip_path,target,cancel):
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            if cancel.is_set(): raise InterruptedError('Installation cancelled')
            name=member.filename.replace('\\','/')
            p=Path(name)
            if p.is_absolute() or '..' in p.parts or ':' in name or name.startswith('/'):
                raise ValueError('Unsafe path in downloaded archive')
            # Reject symlinks.
            if (member.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('Symlink in archive')
            if member.is_dir():
                (target/p).mkdir(parents=True,exist_ok=True)
                continue
            destination=target/p
            destination.parent.mkdir(parents=True,exist_ok=True)
            with archive.open(member) as src,open(destination,'wb') as dst:
                shutil.copyfileobj(src,dst,1024*1024)


def install_engine(base, mode, progress, cancel, releases=None):
    """Install alongside the app, returns (exe_path, tag, checked_asset_count)."""
    if os.name != 'nt':
        raise RuntimeError('Automatic engine installation is currently Windows-only.')
    release_list=releases if releases is not None else releases_json()
    tag,assets=choose_release_assets(release_list,mode)
    base=Path(base).resolve()
    base.mkdir(parents=True,exist_ok=True)
    # Never override the currently installed engine if an interrupted download occurs.
    with tempfile.TemporaryDirectory(prefix='.engine-setup-', dir=base) as tmp:
        temp=Path(tmp)
        staging=temp/'extracted'
        staging.mkdir()
        verified=0
        for asset in assets:
            progress('Preparing '+asset['name'],0,asset.get('size',0))
            archive=temp/asset['name']
            if stream_archive(asset,archive,progress,cancel): verified+=1
            progress('Extracting '+asset['name'],0,0)
            unzip_safe(archive,staging,cancel)
            archive.unlink()
        found=list(staging.rglob('llama-server.exe'))
        if len(found)!=1:
            raise IOError('llama-server.exe not found uniquely in official release')
        # Archive often nests executable in build/bin. Flatten the executable directory's contents
        # and CUDA runtime DLLs so DLL loading works from executable's own directory.
        target=temp/'engine'
        target.mkdir()
        bindir=found[0].parent
        for f in bindir.iterdir():
            if f.is_file(): shutil.copy2(f,target/f.name)
        for f in staging.rglob('*.dll'):
            dest=target/f.name
            if not dest.exists(): shutil.copy2(f,dest)
        exe=target/'llama-server.exe'
        if not exe.is_file(): raise IOError('llama-server.exe missing after extraction')
        final=base / ('llama.cpp-'+mode)
        old=base / ('llama.cpp-'+mode+'-backup')
        if old.exists(): shutil.rmtree(old)
        if final.exists(): final.rename(old)
        try:
            shutil.move(str(target),str(final))
        except Exception:
            if old.exists() and not final.exists(): old.rename(final)
            raise
        if old.exists(): shutil.rmtree(old)
        return str(final/'llama-server.exe'),tag,verified
