"""Discover installed GGUFs without invoking Windows file associations."""
import re
from pathlib import Path

_SHARD = re.compile(r"^(?P<base>.+)-(?P<part>\d{5})-of-(?P<total>\d{5})\.gguf$", re.IGNORECASE)


def list_installed_models(models_dir, selected_path=None):
    """Return installed model records; split GGUF models require all shards."""
    root = Path(models_dir)
    paths = []
    if root.is_dir():
        paths.extend(p for p in root.rglob('*')
                     if p.is_file() and p.suffix.lower() == '.gguf')
    if selected_path:
        p = Path(selected_path)
        if p.is_file() and p.suffix.lower() == '.gguf':
            paths.append(p)
    unique = {}
    for path in paths:
        try:
            if path.stat().st_size > 0:
                unique[str(path.resolve()).casefold()] = path.resolve()
        except OSError:
            continue
    results = []
    processed = set()
    for path in sorted(unique.values(), key=lambda p: str(p).lower()):
        key = str(path).casefold()
        if key in processed:
            continue
        match = _SHARD.match(path.name)
        if match:
            part_no = int(match.group('part'))
            total = int(match.group('total'))
            if not 1 <= part_no <= total <= 1024:
                continue
            base = match.group('base')
            parts = [path.parent / f'{base}-{i:05d}-of-{total:05d}.gguf'
                     for i in range(1, total + 1)]
            first = parts[0]
            if part_no != 1 and first.is_file():
                continue
            for sub in parts:
                processed.add(str(sub.resolve()).casefold())
            complete = all(p.is_file() and p.stat().st_size > 0 for p in parts)
            size = sum(p.stat().st_size for p in parts if p.is_file())
            results.append({'name': base + f' ({total} shards)',
                            'path': str(first if first.is_file() else path),
                            'size': size, 'complete': complete, 'parts': total,
                            'location': str(path.parent)})
        else:
            processed.add(key)
            try:
                size = path.stat().st_size
            except OSError:
                continue
            results.append({'name': path.name, 'path': str(path), 'size': size,
                            'complete': True, 'parts': 1, 'location': str(path.parent)})
    return sorted(results, key=lambda m: m['name'].lower())
