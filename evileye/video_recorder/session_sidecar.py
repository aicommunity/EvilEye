"""Sidecar for splitmux session wall-clock of the first muxed frame."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


_SPLITMUX_INDEX = re.compile(r"_\d{5}$")


def sidecar_path_for_segment(video_path: str | Path) -> Path:
    """``Cam4_..._0_00018.mp4`` → ``Cam4_..._0.session.json``."""
    path = Path(video_path)
    stem = path.stem
    stripped = _SPLITMUX_INDEX.sub("", stem)
    return path.with_name(stripped + ".session.json")


def sidecar_path_from_splitmux_location(location: str) -> Path:
    """``.../Cam4_..._0_%05d.mp4`` → ``.../Cam4_..._0.session.json``."""
    if "_%05d." in location:
        base = location.replace("_%05d.", ".", 1)
        return Path(base).with_suffix(".session.json")
    return Path(location).with_suffix(".session.json")


_SIDECAR_STARTS_CACHE: dict[str, list[float]] = {}


def write_session_sidecar(path: Path, start_ts: float, first_pts_ns: int | None = None) -> None:
    payload: dict[str, Any] = {"start_ts": float(start_ts)}
    if first_pts_ns is not None:
        payload["first_pts_ns"] = int(first_pts_ns)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    tmp.replace(path)
    _SIDECAR_STARTS_CACHE.pop(str(path.parent.resolve()), None)


def read_session_sidecar(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def read_session_sidecar_for_segment(video_path: str | Path) -> dict[str, Any] | None:
    return read_session_sidecar(sidecar_path_for_segment(video_path))


def _sidecar_starts_for_folder(folder: Path) -> list[float]:
    key = str(folder.resolve())
    cached = _SIDECAR_STARTS_CACHE.get(key)
    if cached is not None:
        return cached

    starts: list[float] = []
    try:
        paths = list(folder.glob("*.session.json"))
    except OSError:
        paths = []
    for sidecar in paths:
        data = read_session_sidecar(sidecar)
        if not data:
            continue
        try:
            starts.append(float(data["start_ts"]))
        except (KeyError, TypeError, ValueError):
            continue
    _SIDECAR_STARTS_CACHE[key] = starts
    return starts


def pick_sidecar_start_ts(folder: Path, around_ts: float | None = None) -> float | None:
    starts = _sidecar_starts_for_folder(folder)
    if not starts:
        return None
    if around_ts is None:
        return min(starts)
    earlier = [value for value in starts if value <= float(around_ts) + 1.0]
    if earlier:
        return max(earlier)
    return min(starts, key=lambda value: abs(value - float(around_ts)))
