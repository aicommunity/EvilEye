#!/usr/bin/env python3
"""Probe detection journal freshness without waiting for evening stall.

Modes:
  (default) live now — Streams fresh ⇒ objects_found OR .journal_writer_alive fresh
  --historical YYYY-MM-DD — reconstruct stall window from file mtimes (no wait)
  --simulate-stale-check — run monitor check_detection_journal_stale via bash

Env:
  EVILEYE_DATA_ROOT (default /media/user/Data8/EvilEyeData)
  DETECTION_STALE_SEC (default 600)
  EVILEYE_DEPLOY (default /home/user/EvilEyeDeploy) for simulate
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

DATA_ROOT = Path(os.environ.get("EVILEYE_DATA_ROOT", "/media/user/Data8/EvilEyeData"))
AGE_LIMIT = int(os.environ.get("DETECTION_STALE_SEC", "600"))
DEPLOY = Path(os.environ.get("EVILEYE_DEPLOY", "/home/user/EvilEyeDeploy"))
LOGS = DEPLOY / "logs"


def _newest_mp4_mtime(day: str) -> float:
    root = DATA_ROOT / "Streams" / day
    newest = 0.0
    if not root.is_dir():
        return 0.0
    for p in root.rglob("*.mp4"):
        try:
            newest = max(newest, p.stat().st_mtime)
        except OSError:
            continue
    return newest


def _found_mtime(day: str) -> float:
    p = DATA_ROOT / "Detections" / day / "Metadata" / "objects_found.json"
    try:
        return p.stat().st_mtime if p.is_file() else 0.0
    except OSError:
        return 0.0


def _alive_mtime(day: str) -> float:
    p = DATA_ROOT / "Detections" / day / "Metadata" / ".journal_writer_alive"
    try:
        return p.stat().st_mtime if p.is_file() else 0.0
    except OSError:
        return 0.0


def _days_around(day: str | None = None) -> list[str]:
    if day:
        d = datetime.strptime(day, "%Y-%m-%d").date()
        return [d.strftime("%Y-%m-%d"), (d - timedelta(days=1)).strftime("%Y-%m-%d")]
    today = datetime.now().date()
    return [today.strftime("%Y-%m-%d"), (today - timedelta(days=1)).strftime("%Y-%m-%d")]


def _last_journal_heartbeat() -> dict[str, Any] | None:
    # Prefer newest main log chunks
    candidates = sorted(LOGS.glob("*_evileye_main.log*"), key=lambda p: p.stat().st_mtime, reverse=True)[:6]
    for fp in candidates:
        try:
            # read last 200KB
            data = fp.read_bytes()[-200_000:]
            text = data.decode("utf-8", "replace")
        except OSError:
            continue
        for line in reversed(text.splitlines()):
            if "journal_heartbeat" in line and "objects_found_mtime_age_sec=" in line:
                return {"file": fp.name, "line": line.strip()[-400:]}
    return None


def probe_live() -> dict[str, Any]:
    now = time.time()
    days = _days_around()
    streams = max(_newest_mp4_mtime(d) for d in days)
    found = max(_found_mtime(d) for d in days)
    alive = max(_alive_mtime(d) for d in days)
    streams_age = (now - streams) if streams else None
    found_age = (now - found) if found else None
    alive_age = (now - alive) if alive else None
    hb = _last_journal_heartbeat()

    streams_fresh = streams_age is not None and streams_age < AGE_LIMIT
    found_fresh = found_age is not None and found_age < AGE_LIMIT
    alive_fresh = alive_age is not None and alive_age < AGE_LIMIT

    if not streams_fresh:
        ok = True
        reason = "streams_not_fresh"
    elif found_fresh or alive_fresh:
        ok = True
        reason = "found_fresh" if found_fresh else "writer_alive_fresh"
    else:
        ok = False
        reason = "detection_stale_while_streams_fresh"

    return {
        "ok": ok,
        "reason": reason,
        "age_limit_sec": AGE_LIMIT,
        "days": days,
        "streams_age_sec": None if streams_age is None else round(streams_age, 1),
        "found_age_sec": None if found_age is None else round(found_age, 1),
        "alive_age_sec": None if alive_age is None else round(alive_age, 1),
        "heartbeat": hb,
        "data_root": str(DATA_ROOT),
    }


def probe_historical(day: str) -> dict[str, Any]:
    """Detect evening stall pattern: found stops ~20:00 while streams continue to midnight."""
    found = _found_mtime(day)
    streams = _newest_mp4_mtime(day)
    # Also check next calendar morning stream spill
    next_day = (datetime.strptime(day, "%Y-%m-%d").date() + timedelta(days=1)).strftime("%Y-%m-%d")
    streams_spill = _newest_mp4_mtime(next_day)
    streams_end = max(streams, streams_spill)
    if not found or not streams_end:
        return {"ok": False, "reason": "missing_files", "day": day, "found": found, "streams_end": streams_end}

    found_local = datetime.fromtimestamp(found)
    streams_local = datetime.fromtimestamp(streams_end)
    gap_sec = streams_end - found
    # Historical FAIL (stall pattern) if found stopped before ~21:00 and streams continued >1h
    stall_like = found_local.hour >= 19 and gap_sec > 3600
    return {
        "ok": True,  # script success; pattern flagged separately
        "day": day,
        "stall_pattern_detected": stall_like,
        "found_mtime": found_local.isoformat(sep=" ", timespec="seconds"),
        "streams_end_mtime": streams_local.isoformat(sep=" ", timespec="seconds"),
        "gap_sec": round(gap_sec, 1),
        "note": "stall_pattern_detected=true means evening journal stop while Streams continued",
    }


def simulate_stale_check() -> dict[str, Any]:
    common = DEPLOY / "monitor" / "scripts" / "common.sh"
    if not common.is_file():
        return {"ok": False, "error": f"missing {common}"}
    script = f'source "{common}"; check_detection_journal_stale; echo EXIT:$?'
    proc = subprocess.run(
        ["bash", "-lc", script],
        capture_output=True,
        text=True,
        env={**os.environ, "DETECTION_STALE_SEC": str(AGE_LIMIT)},
        timeout=60,
        check=False,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    exit_line = [ln for ln in out.splitlines() if ln.startswith("EXIT:")]
    code = int(exit_line[-1].split(":", 1)[1]) if exit_line else proc.returncode
    # monitor: exit 0 = incident should fire; exit 1 = healthy
    return {
        "ok": True,
        "monitor_incident": code == 0,
        "monitor_exit": code,
        "output": out.strip()[-500:],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--historical", metavar="YYYY-MM-DD")
    ap.add_argument("--simulate-stale-check", action="store_true")
    ap.add_argument("--json-out", default="")
    args = ap.parse_args()

    if args.historical:
        result = probe_historical(args.historical)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        if args.json_out:
            Path(args.json_out).write_text(json.dumps(result, indent=2), encoding="utf-8")
        return 0 if result.get("ok") else 1

    if args.simulate_stale_check:
        result = simulate_stale_check()
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result.get("ok") else 1

    result = probe_live()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
