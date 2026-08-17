"""Playback index over EvilEyeData/Streams (ported from StreamPlayerWindow logic)."""
from __future__ import annotations

import glob
import json
import os
import re
import struct
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from evileye.video_recorder.session_sidecar import (
    pick_sidecar_start_ts,
    read_session_sidecar_for_segment,
)

_data_dir_cache: tuple[str, float, str] | None = None


def _config_mtime(config_path: str | None) -> float:
    if not config_path:
        return 0.0
    try:
        return os.path.getmtime(config_path)
    except OSError:
        return 0.0


def _load_current_run_config() -> tuple[str, dict[str, Any]]:
    """Return (config_path, params) for the current run, or ("", {})."""
    try:
        from evileye.api.core.server_state import get_current_run_summary
    except Exception:
        return "", {}
    current = get_current_run_summary()
    if not isinstance(current, dict):
        return "", {}
    snapshot = current.get("runtime_snapshot")
    if isinstance(snapshot, dict):
        payload = snapshot.get("config")
        if isinstance(payload, dict):
            return str(current.get("config_path") or ""), payload
    config_path = current.get("config_path")
    if not config_path:
        return "", {}
    try:
        payload = json.loads(Path(str(config_path)).read_text(encoding="utf-8"))
    except Exception:
        return str(config_path), {}
    return str(config_path), payload if isinstance(payload, dict) else {}


def _configured_data_dir_from_params(params: dict[str, Any]) -> str | None:
    """Prefer the same roots the recorder uses (database.image_dir / record.out_dir)."""
    database = params.get("database")
    if isinstance(database, dict):
        for key in ("image_dir", "images_dir"):
            value = database.get(key)
            if value not in (None, ""):
                return str(value)

    record = params.get("record")
    if isinstance(record, dict):
        out_dir = record.get("out_dir")
        if out_dir not in (None, ""):
            return str(out_dir)

    controller = params.get("controller")
    if isinstance(controller, dict):
        value = controller.get("image_dir")
        if value not in (None, ""):
            return str(value)

    pipeline = params.get("pipeline") if isinstance(params.get("pipeline"), dict) else params
    sources = pipeline.get("sources") if isinstance(pipeline, dict) else None
    for source in sources or []:
        if not isinstance(source, dict):
            continue
        src_record = source.get("record")
        if isinstance(src_record, dict):
            out_dir = src_record.get("out_dir")
            if out_dir not in (None, ""):
                return str(out_dir)
    return None


def _resolve_configured_data_dir() -> str | None:
    global _data_dir_cache
    config_path, params = _load_current_run_config()
    mtime = _config_mtime(config_path or None)
    if _data_dir_cache and _data_dir_cache[0] == config_path and _data_dir_cache[1] == mtime:
        return _data_dir_cache[2] or None
    configured = _configured_data_dir_from_params(params) if params else None
    _data_dir_cache = (config_path, mtime, configured or "")
    return configured


def data_dir() -> Path:
    """Root for Streams/Events media.

    Preference: ``EVILEYE_DATA_DIR`` → current run ``database.image_dir`` /
    ``record.out_dir`` → local ``EvilEyeData``.
    """
    env = os.getenv("EVILEYE_DATA_DIR")
    if env not in (None, ""):
        return Path(env).resolve()
    configured = _resolve_configured_data_dir()
    return Path(configured or "EvilEyeData").resolve()


def _secure_under(base: Path, candidate: Path) -> Path:
    resolved = candidate.resolve()
    base_resolved = base.resolve()
    if not str(resolved).startswith(str(base_resolved) + os.sep) and resolved != base_resolved:
        raise PermissionError(f"Path outside data dir: {candidate}")
    return resolved


_DEFAULT_SEGMENT_LENGTH_SEC = 300.0
_DURATION_CACHE: dict[str, tuple[float, float]] = {}
_MP4_DURATION_CACHE: dict[str, tuple[float, float | None]] = {}
_SEGMENT_LENGTH_CACHE: tuple[str, float, float] | None = None


def _configured_segment_length_sec() -> float:
    """Recording segment length from current config file (fallback 300s).

    Avoids get_current_run_summary() so segment indexing stays disk-cheap.
    """
    global _SEGMENT_LENGTH_CACHE
    try:
        from evileye.api.core.server_state import get_current_config_path

        config_path = get_current_config_path() or ""
    except Exception:
        config_path = ""
    mtime = 0.0
    if config_path:
        try:
            mtime = os.path.getmtime(config_path)
        except OSError:
            mtime = 0.0
    if (
        _SEGMENT_LENGTH_CACHE
        and _SEGMENT_LENGTH_CACHE[0] == config_path
        and _SEGMENT_LENGTH_CACHE[1] == mtime
    ):
        return _SEGMENT_LENGTH_CACHE[2]

    length = _DEFAULT_SEGMENT_LENGTH_SEC
    if config_path:
        try:
            params = json.loads(Path(config_path).read_text(encoding="utf-8"))
            record = params.get("record") if isinstance(params, dict) else None
            if isinstance(record, dict) and record.get("segment_length_sec") is not None:
                sec = float(record.get("segment_length_sec"))
                if sec > 0:
                    length = sec
        except Exception:
            pass
    _SEGMENT_LENGTH_CACHE = (config_path, mtime, length)
    return length


def _parse_segment_name(path: str) -> tuple[float, int | None] | None:
    """Parse session start and optional splitmux index from filename.

    Production GStreamer names look like ``Cam1_YYYYMMDD_HHMMSS_0_%05d.mp4``:
    the datetime is the recording session start; the trailing ``_%05d`` is the
    rotation index. Older/alternate names may use a unique datetime per file.
    """
    name = Path(path).stem
    m = re.search(r"(\d{8})[_-](\d{6})", name)
    if not m:
        return None
    try:
        session_start = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S").timestamp()
    except Exception:
        return None
    idx_m = re.search(r"_(\d{5})$", name)
    index = int(idx_m.group(1)) if idx_m else None
    return session_start, index


def _session_start_with_sidecar(path: str, filename_session_start: float) -> float:
    data = read_session_sidecar_for_segment(path)
    if not data:
        return filename_session_start
    try:
        return float(data["start_ts"])
    except (KeyError, TypeError, ValueError):
        return filename_session_start


def session_anchor_ts_for_camera(
    camera: str,
    date_folder: str,
    around_ts: float | None = None,
) -> float | None:
    """Wall clock of first muxed frame from sidecar, if present."""
    date_dir = data_dir() / "Streams" / date_folder
    folder = resolve_camera_folder(date_dir, camera)
    if folder is None:
        return None
    return pick_sidecar_start_ts(folder, around_ts)


def _file_mtime(path: str) -> float | None:
    try:
        return os.path.getmtime(path)
    except OSError:
        return None


def _read_mp4_box_header(fh, file_size: int) -> tuple[int, bytes, int] | None:
    pos = fh.tell()
    if pos + 8 > file_size:
        return None
    header = fh.read(8)
    if len(header) < 8:
        return None
    size, typ = struct.unpack(">I4s", header)
    hdr_len = 8
    if size == 1:
        wide = fh.read(8)
        if len(wide) < 8:
            return None
        size = struct.unpack(">Q", wide)[0]
        hdr_len = 16
    elif size == 0:
        size = file_size - pos
    if size < hdr_len:
        return None
    return size, typ, hdr_len


def _parse_mvhd_duration(payload: bytes) -> float | None:
    if len(payload) < 20:
        return None
    version = payload[0]
    try:
        if version == 1:
            if len(payload) < 32:
                return None
            timescale = struct.unpack(">I", payload[20:24])[0]
            duration = struct.unpack(">Q", payload[24:32])[0]
        else:
            timescale = struct.unpack(">I", payload[12:16])[0]
            duration = struct.unpack(">I", payload[16:20])[0]
    except struct.error:
        return None
    if timescale <= 0 or duration <= 0:
        return None
    return duration / float(timescale)


def _mp4_duration_sec(path: str) -> float | None:
    """Read movie duration from ``mvhd`` without decoding frames.

    Closed splitmux parts have ``moov``; in-progress files often do not.
    Result is cached by mtime.
    """
    try:
        st = os.stat(path)
    except OSError:
        return None
    cached = _MP4_DURATION_CACHE.get(path)
    if cached and cached[0] == st.st_mtime:
        return cached[1]

    duration: float | None = None
    try:
        with open(path, "rb") as fh:
            file_size = st.st_size
            stack: list[int] = [file_size]
            while True:
                pos = fh.tell()
                limit = stack[-1] if stack else file_size
                if pos + 8 > limit:
                    if len(stack) <= 1:
                        break
                    fh.seek(stack.pop())
                    continue
                parsed = _read_mp4_box_header(fh, file_size)
                if parsed is None:
                    break
                size, typ, hdr_len = parsed
                payload_end = pos + size
                if payload_end > file_size or payload_end < pos:
                    break
                if typ == b"mvhd":
                    payload = fh.read(min(40, size - hdr_len))
                    duration = _parse_mvhd_duration(payload)
                    break
                if typ == b"moov":
                    stack.append(payload_end)
                    continue
                fh.seek(payload_end)
    except OSError:
        duration = None

    _MP4_DURATION_CACHE[path] = (st.st_mtime, duration)
    return duration


def _plausible_media_duration(duration: float | None, configured_length: float) -> float | None:
    if duration is None:
        return None
    if duration < 1.0:
        return None
    # Do not scale against configured_length: a stale 300s default would reject 30-min parts.
    if duration > 8 * 3600:
        return None
    return duration


def _resolve_segment_starts(
    parsed: list[tuple[str, float, int | None]],
    *,
    configured_length: float,
) -> list[tuple[str, float]]:
    """Map files to start timestamps, expanding splitmux indices when needed.

    Splitmux rotates on media time. Using ``index * segment_length_sec`` drifts
    across a long session. Using the previous file's mtime is worse for part 0:
    ``async-finalize`` stamps mtime ~10s after the last frame, and that delay
    shifts every later part so overlay boxes lead the video.

    Closed parts: accumulate ``mvhd`` duration from the session start. Fallback
    to mtime only when duration is missing and the stamp is close to the
    nominal slot (not for the first part).
    """
    if not parsed:
        return []
    by_session: dict[float, list[tuple[str, int | None]]] = {}
    for path, session_start, index in parsed:
        by_session.setdefault(session_start, []).append((path, index))

    out: list[tuple[str, float]] = []
    slack = max(60.0, configured_length * 0.5)
    for session_start, items in by_session.items():
        indices = [idx for _, idx in items if idx is not None]
        use_index = (
            len(items) > 1
            and len(indices) == len(items)
            and len(set(indices)) == len(items)
        )
        if not use_index:
            for path, _idx in items:
                out.append((path, session_start))
            continue
        ordered = sorted(items, key=lambda item: (item[1] if item[1] is not None else 0, item[0]))
        start = session_start
        for path, idx in ordered:
            nominal = session_start + float(idx or 0) * configured_length
            chosen = start
            if abs(chosen - nominal) > slack:
                chosen = nominal
            out.append((path, chosen))
            media_dur = _plausible_media_duration(_mp4_duration_sec(path), configured_length)
            if media_dur is not None:
                start = chosen + media_dur
                continue
            mtime = _file_mtime(path)
            # Skip part-0 mtime: it includes mux finalize, not media time.
            if idx not in (None, 0) and mtime is not None and abs(mtime - (chosen + configured_length)) <= slack:
                start = mtime
            else:
                start = chosen + configured_length
    return out


def _segment_start_ts(path: str) -> float | None:
    """Parse segment start from filename (Cam2_YYYYMMDD_HHMMSS_... or YYYYMMDD_HHMMSS)."""
    parsed = _parse_segment_name(path)
    if parsed is None:
        return None
    return _session_start_with_sidecar(path, parsed[0])


def _video_duration_sec(path: str) -> float | None:
    """Best-effort duration without decoding: neighbor gap / mtime / config length.

    OpenCV is intentionally avoided — opening every MP4 blocks the web API for seconds
    and fails on in-progress splitmux files (moov not written yet).
    """
    try:
        st = os.stat(path)
        cached = _DURATION_CACHE.get(path)
        if cached and cached[0] == st.st_mtime:
            return cached[1]
    except OSError:
        return None

    start = _segment_start_ts(path)
    configured = _configured_segment_length_sec()
    duration = _plausible_media_duration(_mp4_duration_sec(path), configured)
    if duration is None:
        if start is not None:
            age = max(0.1, st.st_mtime - start)
            duration = min(age, configured * 1.5)
        else:
            duration = configured

    _DURATION_CACHE[path] = (st.st_mtime, duration)
    return duration


def _assign_segment_ends(
    starts: list[tuple[str, float]],
    *,
    configured_length: float,
) -> list[tuple[str, float, float]]:
    """Fill end timestamps from next-segment start (gap) or mtime/config for the last one."""
    if not starts:
        return []
    ordered = sorted(starts, key=lambda item: (item[1], item[0]))
    max_span = configured_length * 1.25
    out: list[tuple[str, float, float]] = []
    for idx, (path, start) in enumerate(ordered):
        if idx + 1 < len(ordered):
            gap = ordered[idx + 1][1] - start
            if 0 < gap <= max_span:
                end = ordered[idx + 1][1]
            else:
                # Restart/hole between files — do not paint downtime as one segment.
                try:
                    mtime = os.path.getmtime(path)
                    end = max(start + 0.1, min(mtime, start + max_span))
                except OSError:
                    end = start + configured_length
        else:
            dur = _plausible_media_duration(_mp4_duration_sec(path), configured_length)
            if dur is not None:
                end = start + dur
            else:
                try:
                    mtime = os.path.getmtime(path)
                    end = max(start + 0.1, min(mtime, start + max_span))
                except OSError:
                    end = start + configured_length
        out.append((path, start, end))
    return out


def _parse_segment_times(path: str) -> tuple[float, float] | None:
    """Parse start/end for a single path (batch load prefers _assign_segment_ends)."""
    start = _segment_start_ts(path)
    if start is not None:
        duration = _video_duration_sec(path) or _configured_segment_length_sec()
        return start, start + duration
    try:
        mtime = os.path.getmtime(path)
        duration = _video_duration_sec(path) or _configured_segment_length_sec()
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


def _date_dirs_covering(
    base: Path,
    *,
    date: Optional[str] = None,
    from_ts: Optional[float] = None,
    to_ts: Optional[float] = None,
) -> list[Path]:
    """Collect day folders covering from/to (and optional explicit date)."""
    found: dict[str, Path] = {}

    def _add(path: Path) -> None:
        if path.is_dir():
            found[path.name] = path

    if from_ts is not None or to_ts is not None:
        start = from_ts if from_ts is not None else (to_ts or 0) - 86400
        end = to_ts if to_ts is not None else (from_ts or 0) + 86400
        if end < start:
            start, end = end, start
        day = datetime.fromtimestamp(start).date()
        end_day = datetime.fromtimestamp(end).date()
        while day <= end_day:
            _add(base / day.isoformat())
            day = day.fromordinal(day.toordinal() + 1)

    if date:
        for p in _date_dirs(base, date):
            _add(p)

    if found:
        return sorted(found.values(), key=lambda p: p.name)

    return _date_dirs(base, date)


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


def _mp4_paths_for_logical_camera(folder: Path, camera: str) -> list[str]:
    """Segment files for a logical camera in a resolved storage folder.

    Split sources share one recording: folder name is ``"-".join(source_names)``,
    files are typically prefixed with the first part. Every logical part of that
    folder must see the same shared set (crop is applied by the client).
    """
    if folder.name == camera or "-" not in folder.name:
        return glob.glob(str(folder / "*.mp4"))

    parts = [p for p in folder.name.split("-") if p]
    if camera in parts:
        primary = parts[0]
        primary_paths = glob.glob(str(folder / f"{primary}_*.mp4"))
        if primary_paths:
            return primary_paths
        return glob.glob(str(folder / "*.mp4"))

    return glob.glob(str(folder / f"{camera}_*.mp4"))


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


def _config_path_for_run(run_id: int | None) -> Optional[str]:
    if run_id is None:
        return None
    try:
        from evileye.api.core.server_state import get_run_summary

        summary = get_run_summary(int(run_id))
        if summary:
            return summary.get("config_path")
    except Exception:
        pass
    try:
        from evileye.api.core.runtime_registry import load_runtime_record

        record = load_runtime_record(int(run_id))
        if record:
            return record.get("config_path")
    except Exception:
        pass
    return None


def list_logical_cameras(run_id: int | None = None, date: Optional[str] = None) -> list[dict[str, Any]]:
    """Logical cameras from run config (source_names), mapped to on-disk storage folders."""
    from evileye.api.core.server_state import load_config_summary

    config_path = _config_path_for_run(run_id)
    summary = load_config_summary(config_path)
    if not summary.source_items:
        return discover_cameras(date)

    base = data_dir() / "Streams"
    date_dirs = _date_dirs(base, date)
    cameras: list[dict[str, Any]] = []

    for item in summary.source_items:
        logical_id = str(item.get("source_name") or "")
        if not logical_id:
            continue
        parent_folder = item.get("parent_source_name")
        storage_folder = parent_folder or logical_id
        split = bool(item.get("split"))
        src_coords = item.get("src_coords")

        folder_exists = False
        segment_count = 0
        for date_dir in date_dirs:
            folder = resolve_camera_folder(date_dir, logical_id)
            if folder is None:
                continue
            folder_exists = True
            if folder == date_dir:
                segment_count += len(glob.glob(str(date_dir / f"{logical_id}*.mp4")))
            else:
                segment_count += len(_mp4_paths_for_logical_camera(folder, logical_id))

        logical_frame_size = None
        if split and isinstance(src_coords, (list, tuple)) and len(src_coords) >= 4:
            try:
                lw, lh = int(src_coords[2]), int(src_coords[3])
                if lw > 0 and lh > 0:
                    logical_frame_size = {"w": lw, "h": lh}
            except Exception:
                logical_frame_size = None

        cameras.append(
            {
                "id": logical_id,
                "name": logical_id,
                "source_id": item.get("source_id"),
                "storage_folder": storage_folder,
                "parent_folder": parent_folder,
                "split": split,
                "src_coords": src_coords,
                "logical_frame_size": logical_frame_size,
                "folder": storage_folder,
                "segment_count": segment_count,
                "available": folder_exists or segment_count > 0,
            }
        )

    return cameras


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
    for date_dir in _date_dirs_covering(base, date=date, from_ts=from_ts, to_ts=to_ts):
        folder = resolve_camera_folder(date_dir, camera)
        if folder is None:
            continue
        if folder == date_dir:
            paths.extend(glob.glob(str(date_dir / f"{camera}*.mp4")))
        else:
            paths.extend(_mp4_paths_for_logical_camera(folder, camera))

    configured_length = _configured_segment_length_sec()
    parsed_named: list[tuple[str, float, int | None]] = []
    undated: list[str] = []
    for path in set(paths):
        parsed = _parse_segment_name(path)
        if parsed is not None:
            session_start, index = parsed
            session_start = _session_start_with_sidecar(path, session_start)
            parsed_named.append((path, session_start, index))
        else:
            undated.append(path)

    dated = _resolve_segment_starts(parsed_named, configured_length=configured_length)

    items: list[dict[str, Any]] = []
    for path, start_ts, end_ts in _assign_segment_ends(dated, configured_length=configured_length):
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

    for path in undated:
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

    items.sort(key=lambda row: (row["start_ts"], row["path"]))
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
    cameras: Optional[list[str]] = None,
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
    camera_filters = [c for c in (cameras or []) if c]
    if camera and not camera_filters:
        camera_filters = [camera]
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
                if camera_filters and not any(c in path for c in camera_filters):
                    continue
                marker_camera = next((c for c in camera_filters if c in path), None) or Path(root).name
                markers.append(
                    {
                        "ts": ts,
                        "type": Path(name).suffix.lstrip(".") or "event",
                        "camera": marker_camera,
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
