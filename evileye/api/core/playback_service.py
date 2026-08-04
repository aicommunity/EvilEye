"""Playback index over EvilEyeData/Streams (ported from StreamPlayerWindow logic)."""
from __future__ import annotations

import glob
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


def data_dir() -> Path:
    return Path(os.getenv("EVILEYE_DATA_DIR", "EvilEyeData")).resolve()


def _secure_under(base: Path, candidate: Path) -> Path:
    resolved = candidate.resolve()
    base_resolved = base.resolve()
    if not str(resolved).startswith(str(base_resolved) + os.sep) and resolved != base_resolved:
        raise PermissionError(f"Path outside data dir: {candidate}")
    return resolved


def _parse_segment_times(path: str) -> tuple[float, float] | None:
    name = Path(path).stem
    # Common patterns: YYYYMMDD_HHMMSS or unix-ish; fall back to mtime
    m = re.search(r"(\d{8})[_-](\d{6})", name)
    if m:
        try:
            start = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S").timestamp()
            # Assume ~60s segments if unknown
            return start, start + 60.0
        except Exception:
            pass
    try:
        mtime = os.path.getmtime(path)
        return mtime - 60.0, mtime
    except Exception:
        return None


def discover_cameras(date: Optional[str] = None) -> list[dict[str, str]]:
    base = data_dir() / "Streams"
    if not base.exists():
        return []
    date_dirs: list[Path]
    if date:
        date_dirs = [base / date]
    else:
        date_dirs = sorted([p for p in base.iterdir() if p.is_dir()], reverse=True)[:7]
    cameras: dict[str, dict[str, str]] = {}
    for d in date_dirs:
        if not d.exists():
            continue
        for item in d.iterdir():
            if item.is_dir():
                cam_id = item.name
                cameras[cam_id] = {"id": cam_id, "name": cam_id, "folder": str(item)}
            elif item.suffix.lower() == ".mp4":
                cam_id = item.stem
                cameras.setdefault(cam_id, {"id": cam_id, "name": cam_id, "folder": str(d)})
    return sorted(cameras.values(), key=lambda x: x["id"])


def load_segments(camera: str, from_ts: Optional[float] = None, to_ts: Optional[float] = None) -> list[dict[str, Any]]:
    base = data_dir() / "Streams"
    if not base.exists():
        return []
    paths: list[str] = []
    for date_dir in sorted(base.iterdir()):
        if not date_dir.is_dir():
            continue
        cam_dir = date_dir / camera
        if cam_dir.is_dir():
            paths.extend(glob.glob(str(cam_dir / "*.mp4")))
        else:
            paths.extend(glob.glob(str(date_dir / f"{camera}*.mp4")))
    items: list[dict[str, Any]] = []
    for path in sorted(paths):
        times = _parse_segment_times(path)
        if not times:
            continue
        start_ts, end_ts = times
        if from_ts is not None and end_ts < from_ts:
            continue
        if to_ts is not None and start_ts > to_ts:
            continue
        items.append(
            {
                "path": path,
                "start_ts": start_ts,
                "end_ts": end_ts,
                "duration_ms": int(max(0.0, end_ts - start_ts) * 1000),
            }
        )
    return items


def load_event_markers(
    from_ts: Optional[float] = None,
    to_ts: Optional[float] = None,
    camera: Optional[str] = None,
) -> list[dict[str, Any]]:
    base = data_dir() / "Events"
    if not base.exists():
        return []
    markers: list[dict[str, Any]] = []
    for date_dir in sorted(base.iterdir()):
        if not date_dir.is_dir():
            continue
        for root, _dirs, files in os.walk(date_dir):
            for name in files:
                if not name.lower().endswith((".json", ".jpg", ".jpeg", ".png", ".mp4")):
                    continue
                path = os.path.join(root, name)
                try:
                    ts = os.path.getmtime(path)
                except Exception:
                    continue
                if from_ts is not None and ts < from_ts:
                    continue
                if to_ts is not None and ts > to_ts:
                    continue
                cam = camera
                if cam and cam not in path:
                    continue
                markers.append(
                    {
                        "ts": ts,
                        "type": Path(name).suffix.lstrip(".") or "event",
                        "camera": cam or Path(root).name,
                        "row_key": path,
                    }
                )
    markers.sort(key=lambda m: m["ts"])
    return markers[:2000]


def resolve_media_path(path: str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = data_dir() / path
    return _secure_under(data_dir(), candidate)
