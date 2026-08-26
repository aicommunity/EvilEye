#!/usr/bin/env python3
"""Concurrent playback API fan-out to stress timeline/cameras/metadata under seek-like windows.

Usage:
  EVILEYE_E2E_BASE=http://127.0.0.1:8181 \\
  EVILEYE_COOKIE='session=...' \\
  EVILEYE_PID=$(pgrep -f 'evileye server' | head -1) \\
  python3 scripts/load_playback_seek_fanout.py

Env:
  EVILEYE_E2E_BASE, EVILEYE_COOKIE (optional), EVILEYE_PID (optional)
  LOAD_DATE (YYYY-MM-DD), LOAD_CAMERAS (comma ids), LOAD_WORKERS (8), LOAD_ITERS (20)
"""
from __future__ import annotations

import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

BASE = os.environ.get("EVILEYE_E2E_BASE", "http://127.0.0.1:8181").rstrip("/")
COOKIE = os.environ.get("EVILEYE_COOKIE", "")
DATE = os.environ.get("LOAD_DATE", time.strftime("%Y-%m-%d"))
CAMERAS = os.environ.get("LOAD_CAMERAS", "")
WORKERS = int(os.environ.get("LOAD_WORKERS", "8"))
ITERS = int(os.environ.get("LOAD_ITERS", "20"))
PID = os.environ.get("EVILEYE_PID", "")


def _proc_stat(pid: str) -> dict[str, str]:
    if not pid:
        return {}
    try:
        status = Path(f"/proc/{pid}/status").read_text(encoding="utf-8")
    except OSError:
        return {}
    out: dict[str, str] = {}
    for line in status.splitlines():
        if line.startswith("Threads:") or line.startswith("VmRSS:"):
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    try:
        out["fds"] = str(len(list(Path(f"/proc/{pid}/fd").iterdir())))
    except OSError:
        pass
    return out


def _request(path: str, query: dict[str, str]) -> tuple[int, float, str]:
    qs = urllib.parse.urlencode({k: v for k, v in query.items() if v is not None and v != ""})
    url = f"{BASE}{path}?{qs}" if qs else f"{BASE}{path}"
    req = urllib.request.Request(url, method="GET")
    if COOKIE:
        req.add_header("Cookie", COOKIE)
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read(256)
            return resp.status, time.perf_counter() - t0, body[:80].decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, time.perf_counter() - t0, str(exc.reason)
    except Exception as exc:  # noqa: BLE001
        return 0, time.perf_counter() - t0, str(exc)


def _day_bounds(date: str) -> tuple[float, float]:
    # Local midnight approx via time.strptime in local TZ.
    start = time.mktime(time.strptime(date + " 00:00:00", "%Y-%m-%d %H:%M:%S"))
    return start, start + 86400


def worker(i: int, cameras: str) -> list[tuple[str, int, float]]:
    start, end = _day_bounds(DATE)
    span = 3600.0
    results: list[tuple[str, int, float]] = []
    for j in range(ITERS):
        mid = start + ((i * 97 + j * 131) % int(end - start - span))
        fr, to = mid, mid + span
        code, dt, _ = _request(
            "/api/v1/playback/timeline",
            {"date": DATE, "cameras": cameras, "from": str(fr), "to": str(to)},
        )
        results.append(("timeline", code, dt))
        if j % 3 == 0:
            code, dt, _ = _request("/api/v1/playback/cameras", {"date": DATE})
            results.append(("cameras", code, dt))
        if j % 4 == 0 and cameras:
            cam0 = cameras.split(",")[0]
            code, dt, _ = _request(
                "/api/v1/playback/metadata",
                {"camera": cam0, "date": DATE, "ts": str(mid + 10), "static_only": "true"},
            )
            results.append(("metadata", code, dt))
    return results


def main() -> int:
    before = _proc_stat(PID)
    cameras = CAMERAS
    if not cameras:
        # Best-effort discovery (may 401 without cookie).
        code, _, body = _request("/api/v1/playback/cameras", {"date": DATE})
        if code == 200:
            try:
                payload = json.loads(body) if body.startswith("{") else {}
            except json.JSONDecodeError:
                payload = {}
            # Response may be truncated; fall back to env requirement.
            items = payload.get("items") or payload.get("cameras") or []
            if isinstance(items, list) and items:
                names = []
                for it in items[:4]:
                    if isinstance(it, dict) and it.get("id"):
                        names.append(str(it["id"]))
                    elif isinstance(it, dict) and it.get("name"):
                        names.append(str(it["name"]))
                cameras = ",".join(names)
        if not cameras:
            print(
                "WARN: LOAD_CAMERAS not set and cameras discovery failed "
                f"(http {code}). Pass LOAD_CAMERAS=Cam1,Cam2",
                file=sys.stderr,
            )
            cameras = "Cam1"

    print(f"BASE={BASE} DATE={DATE} CAMERAS={cameras} WORKERS={WORKERS} ITERS={ITERS}")
    print(f"proc_before={before}")

    all_rows: list[tuple[str, int, float]] = []
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futs = [pool.submit(worker, i, cameras) for i in range(WORKERS)]
        for fut in as_completed(futs):
            all_rows.extend(fut.result())

    after = _proc_stat(PID)
    by_route: dict[str, list[tuple[int, float]]] = {}
    for route, code, dt in all_rows:
        by_route.setdefault(route, []).append((code, dt))

    print(f"proc_after={after}")
    for route, rows in sorted(by_route.items()):
        lat = [dt for _, dt in rows]
        codes: dict[int, int] = {}
        for code, _ in rows:
            codes[code] = codes.get(code, 0) + 1
        lat_sorted = sorted(lat)
        p50 = lat_sorted[len(lat_sorted) // 2]
        p95 = lat_sorted[min(len(lat_sorted) - 1, int(len(lat_sorted) * 0.95))]
        timeouts = sum(1 for c, _ in rows if c in (0, 503))
        print(
            f"{route}: n={len(rows)} codes={codes} "
            f"p50={p50:.3f}s p95={p95:.3f}s mean={statistics.mean(lat):.3f}s "
            f"timeout_or_503={timeouts}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
