from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, List, Tuple


def get_disk_free_percent(path: str | os.PathLike) -> float:
    p = Path(path)
    try:
        st = os.statvfs(str(p.resolve()))
    except Exception:
        # Fallback to parent directory
        st = os.statvfs(str(p.parent.resolve()))
    total = float(st.f_blocks) * float(st.f_frsize)
    free = float(st.f_bavail) * float(st.f_frsize)
    if total <= 0:
        return 0.0
    return (free / total) * 100.0


def iter_segments(dir_path: str | os.PathLike, exts: Iterable[str]) -> List[Tuple[Path, float]]:
    """List segments (path, mtime) for given extensions in directory."""
    base = Path(dir_path)
    if not base.exists():
        return []
    exts_lower = {e.lower().lstrip('.') for e in exts}
    items: List[Tuple[Path, float]] = []
    for p in base.glob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower().lstrip('.') in exts_lower:
            try:
                items.append((p, p.stat().st_mtime))
            except Exception:
                continue
    items.sort(key=lambda x: x[1])
    return items


def delete_files(paths: List[Path]) -> int:
    removed = 0
    for p in paths:
        try:
            p.unlink(missing_ok=True)
            removed += 1
        except Exception:
            pass
    return removed


