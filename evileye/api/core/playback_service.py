"""Playback index over EvilEyeData/Streams (ported from StreamPlayerWindow logic)."""
from __future__ import annotations

import glob
import os
import re
from datetime import datetime, timezone
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


_DURATION_CACHE: dict[str, tuple[float, float]] = {}


def _video_duration_sec(path: str) -> float | None:
    """Best-effort duration; prefer cache, OpenCV last resort."""
    try:
        st = os.stat(path)
        cached = _DURATION_CACHE.get(path)
        if cached and cached[0] == st.st_mtime:
            return cached[1]
    except OSError:
        st = None

    duration: float | None = None
    try:
        import cv2  # type: ignore

        cap = cv2.VideoCapture(path)
        if cap.isOpened():
            fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
            frames = float(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0)
            cap.release()
            if fps > 0 and frames > 0:
                duration = max(0.1, frames / fps)
    except Exception:
        duration = None

    if duration is not None and st is not None:
        _DURATION_CACHE[path] = (st.st_mtime, duration)
    return duration


def _parse_segment_times(path: str) -> tuple[float, float] | None:
    """Parse start/end from filename; Qt-like Cam2_YYYYMMDD_HHMMSS_... or YYYYMMDD_HHMMSS."""
    name = Path(path).stem
    m = re.search(r"(\d{8})[_-](\d{6})", name)
    if m:
        try:
            start = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S").timestamp()
            duration = _video_duration_sec(path) or 60.0
            return start, start + duration
        except Exception:
            pass
    try:
        mtime = os.path.getmtime(path)
        duration = _video_duration_sec(path) or 60.0
        return mtime - duration, mtime
    except Exception:
        return None


def _date_dirs(base: Path, date: Optional[str]) -> list[Path]:
    if date:
        # Accept YYYY-MM-DD or YYYYMMDD
        candidates = [base / date]
        if re.fullmatch(r"\d{8}", date):
            candidates.append(base / f"{date[:4]}-{date[4:6]}-{date[6:8]}")
        return [p for p in candidates if p.exists()]
    if not base.exists():
        return []
    return sorted([p for p in base.iterdir() if p.is_dir()], reverse=True)[:14]


def _date_str_from_ts(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone().strftime("%Y-%m-%d")


def resolve_camera_folder(date_dir: Path, camera: str) -> Optional[Path]:
    """Resolve camera folder including composite split names (Cam2-Cam3)."""
    direct = date_dir / camera
    if direct.is_dir() and glob.glob(str(direct / "*.mp4")):
        return direct
    # Composite parent: camera is one part of "A-B-C"
    try:
        for item in date_dir.iterdir():
            if not item.is_dir():
                continue
            parts = item.name.split("-")
            if camera in parts and glob.glob(str(item / "*.mp4")):
                return item
    except OSError:
        pass
    # Loose files with camera prefix
    loose = list(date_dir.glob(f"{camera}*.mp4"))
    if loose:
        return date_dir
    return None


def discover_cameras(date: Optional[str] = None) -> list[dict[str, Any]]:
    base = data_dir() / "Streams"
    if not base.exists():
        return []
    cameras: dict[str, dict[str, Any]] = {}
    for d in _date_dirs(base, date):
        if not d.exists():
            continue
        for item in d.iterdir():
            if item.is_dir():
                # Expose composite parts as selectable logical cameras too
                name = item.name
                cameras[name] = {"id": name, "name": name, "folder": str(item)}
                if "-" in name:
                    for part in name.split("-"):
                        if part and part not in cameras:
                            cameras[part] = {
                                "id": part,
                                "name": part,
                                "folder": str(item),
                                "parent_folder": name,
                            }
            elif item.suffix.lower() == ".mp4":
                cam_id = item.stem
                cameras.setdefault(cam_id, {"id": cam_id, "name": cam_id, "folder": str(d)})
    return sorted(cameras.values(), key=lambda x: x["id"])


def load_segments(
    camera: str,
    from_ts: Optional[float] = None,
    to_ts: Optional[float] = None,
    date: Optional[str] = None,
) -> list[dict[str, Any]]:
    base = data_dir() / "Streams"
    if not base.exists():
        return []
    paths: list[str] = []
    for date_dir in _date_dirs(base, date):
        folder = resolve_camera_folder(date_dir, camera)
        if folder is None:
            continue
        if folder == date_dir:
            paths.extend(glob.glob(str(date_dir / f"{camera}*.mp4")))
        else:
            paths.extend(glob.glob(str(folder / "*.mp4")))
    items: list[dict[str, Any]] = []
    for path in sorted(set(paths)):
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
                "camera": camera,
            }
        )
    return items


def load_segments_batch(
    cameras: list[str],
    from_ts: Optional[float] = None,
    to_ts: Optional[float] = None,
    date: Optional[str] = None,
) -> dict[str, list[dict[str, Any]]]:
    return {
        cam: load_segments(cam, from_ts, to_ts, date=date)
        for cam in cameras
        if cam
    }


def load_event_markers(
    from_ts: Optional[float] = None,
    to_ts: Optional[float] = None,
    camera: Optional[str] = None,
    *,
    date: Optional[str] = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    base = data_dir() / "Events"
    if not base.exists():
        return []

    date_dirs: list[Path] = []
    if date:
        date_dirs = _date_dirs(base, date)
    elif from_ts is not None or to_ts is not None:
        start = from_ts if from_ts is not None else (to_ts or 0) - 86400
        end = to_ts if to_ts is not None else (from_ts or 0) + 86400
        if end < start:
            start, end = end, start
        # Walk day folders covering the range (inclusive)
        day = datetime.fromtimestamp(start).date()
        end_day = datetime.fromtimestamp(end).date()
        while day <= end_day:
            d = base / day.isoformat()
            if d.is_dir():
                date_dirs.append(d)
            day = day.fromordinal(day.toordinal() + 1)
    else:
        # Without scope: only most recent day folders
        date_dirs = _date_dirs(base, None)[:3]

    markers: list[dict[str, Any]] = []
    cap = max(1, min(int(limit or 500), 2000))
    for date_dir in date_dirs:
        if not date_dir.is_dir():
            continue
        for root, _dirs, files in os.walk(date_dir):
            # Prefer JSON metadata; fall back to images if no json in folder
            json_files = [n for n in files if n.lower().endswith(".json")]
            candidates = json_files or [
                n for n in files if n.lower().endswith((".jpg", ".jpeg", ".png"))
            ]
            for name in candidates:
                path = os.path.join(root, name)
                try:
                    ts = os.path.getmtime(path)
                except Exception:
                    continue
                if from_ts is not None and ts < from_ts:
                    continue
                if to_ts is not None and ts > to_ts:
                    continue
                if camera and camera not in path:
                    continue
                markers.append(
                    {
                        "ts": ts,
                        "type": Path(name).suffix.lstrip(".") or "event",
                        "camera": camera or Path(root).name,
                        "row_key": path,
                    }
                )
                if len(markers) >= cap:
                    markers.sort(key=lambda m: m["ts"])
                    return markers[:cap]
    markers.sort(key=lambda m: m["ts"])
    return markers[:cap]


def resolve_media_path(path: str) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = data_dir() / path
    return _secure_under(data_dir(), candidate)
