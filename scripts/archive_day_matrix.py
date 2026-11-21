#!/usr/bin/env python3
"""Read-only archive matrix: Streams/Detections/Events × Cam1–5 for recent days."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path("/media/user/Data8/EvilEyeData")
DAYS = ["2026-09-05", "2026-09-06", "2026-09-07", "2026-09-08", "2026-09-09"]
CAMS = ["Cam1", "Cam2", "Cam3", "Cam4", "Cam5"]


def _count_mp4(folder: Path, prefix: str | None = None) -> int:
    if not folder.is_dir():
        return 0
    n = 0
    for p in folder.glob("*.mp4"):
        if prefix and not p.name.startswith(prefix):
            continue
        n += 1
    return n


def _ticks_for_cam(ticks_path: Path, cam: str) -> int:
    if not ticks_path.is_file():
        return 0
    try:
        data = json.loads(ticks_path.read_text(encoding="utf-8"))
    except Exception:
        return 0
    by = data.get("by_camera") if isinstance(data, dict) else None
    if not isinstance(by, dict):
        return 0
    items = by.get(cam) or []
    return len(items) if isinstance(items, list) else 0


def _tl_for_cam(tl_path: Path, cam: str) -> int:
    if not tl_path.is_file():
        return 0
    try:
        data = json.loads(tl_path.read_text(encoding="utf-8"))
    except Exception:
        return 0
    by = data.get("by_camera") if isinstance(data, dict) else None
    if not isinstance(by, dict):
        return 0
    items = by.get(cam) or []
    return len(items) if isinstance(items, list) else 0


def main() -> int:
    if not ROOT.is_dir():
        print(f"missing data root {ROOT}", file=sys.stderr)
        return 1
    print(f"root={ROOT}")
    print(f"{'day':12} {'cam':6} {'mp4':>5} {'tl':>5} {'ticks':>6} {'ev_mp4':>6}")
    for day in DAYS:
        streams = ROOT / "Streams" / day
        ticks = ROOT / "Detections" / day / "Metadata" / "detection_ticks.json"
        tl = streams / "_timeline_segments.json"
        ev = ROOT / "Events" / day / "Videos"
        for cam in CAMS:
            if cam == "Cam1":
                mp4 = _count_mp4(streams / "Cam1")
            elif cam in ("Cam2", "Cam3"):
                folder = streams / "Cam2-Cam3"
                # Shared files use Cam2_ prefix for both logical cams
                mp4 = _count_mp4(folder, "Cam2_")
                if cam == "Cam3":
                    # Physical Cam3-prefixed files (usually 0)
                    own = _count_mp4(folder, "Cam3_")
                    mp4 = own  # report own; shared noted separately
            else:
                folder = streams / "Cam4-Cam5"
                mp4 = _count_mp4(folder, "Cam4_" if cam == "Cam4" else "Cam5_")
            ev_n = 0
            if ev.is_dir():
                for p in ev.rglob("*.mp4"):
                    if cam in p.name or (cam == "Cam3" and "Cam2" in p.name):
                        ev_n += 1
            print(
                f"{day:12} {cam:6} {mp4:5d} {_tl_for_cam(tl, cam):5d} {_ticks_for_cam(ticks, cam):6d} {ev_n:6d}"
            )
        # folder existence
        print(
            f"  streams_dir={'yes' if streams.is_dir() else 'no'} "
            f"ticks_bytes={ticks.stat().st_size if ticks.is_file() else 0} "
            f"tl_bytes={tl.stat().st_size if tl.is_file() else 0}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
