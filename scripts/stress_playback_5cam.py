#!/usr/bin/env python3
"""Stress 5-cam playback like onmatsko session (~2 min wall).

Parallel-ish timeline + detections + media Range waves.
Pass: 0 timeline 503; media not hung forever.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

BASE = os.environ.get("EVILEYE_E2E_BASE", "http://127.0.0.1:8181").rstrip("/")
USER = os.environ.get("EVILEYE_E2E_USER", "playback-test@example.com")
PASSWORD = os.environ.get("EVILEYE_E2E_PASSWORD", "")
DATE = os.environ.get("E2E_PLAYBACK_DATE", time.strftime("%Y-%m-%d"))
CAMERAS = [c.strip() for c in os.environ.get("E2E_PLAYBACK_CAMERAS", "Cam1,Cam2,Cam3,Cam4,Cam5").split(",") if c.strip()]
DURATION_SEC = float(os.environ.get("EVILEYE_STRESS_SEC", "90"))


class Session:
    def __init__(self) -> None:
        self._cookie = ""

    def login(self) -> bool:
        body = json.dumps({"username": USER, "password": PASSWORD}).encode()
        req = urllib.request.Request(f"{BASE}/api/v1/auth/login", data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                self._cookie = (resp.headers.get("Set-Cookie") or "").split(";")[0]
                return bool(self._cookie)
        except Exception:
            return False

    def get(self, path: str, query: dict | None = None, headers: dict | None = None, timeout: float = 30.0):
        qs = urllib.parse.urlencode({k: v for k, v in (query or {}).items() if v not in (None, "")})
        url = f"{BASE}{path}?{qs}" if qs else f"{BASE}{path}"
        req = urllib.request.Request(url, method="GET")
        if self._cookie:
            req.add_header("Cookie", self._cookie)
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read(65536)
                return resp.status, (time.perf_counter() - t0) * 1000.0, dict(resp.headers)
        except urllib.error.HTTPError as exc:
            try:
                exc.read(4096)
            except Exception:
                pass
            return exc.code, (time.perf_counter() - t0) * 1000.0, {}
        except Exception:
            return 0, (time.perf_counter() - t0) * 1000.0, {}


def _collect_paths(session: Session) -> list[str]:
    fr = str(time.mktime(time.strptime(DATE + " 00:00:00", "%Y-%m-%d %H:%M:%S")))
    to = str(float(fr) + 86400)
    qs = urllib.parse.urlencode(
        {"date": DATE, "cameras": ",".join(CAMERAS), "from": fr, "to": to, "segments_only": "true"}
    )
    req = urllib.request.Request(f"{BASE}/api/v1/playback/timeline?{qs}")
    req.add_header("Cookie", session._cookie)
    with urllib.request.urlopen(req, timeout=90) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    by_cam = payload.get("by_camera") or {}
    paths: list[str] = []
    for cam in CAMERAS:
        block = by_cam.get(cam) or {}
        segs = block.get("segments") if isinstance(block, dict) else block
        if not isinstance(segs, list):
            continue
        playable = [s for s in segs if isinstance(s, dict) and s.get("path") and s.get("playable", True)]
        if playable:
            paths.append(playable[len(playable) // 2]["path"])
    return paths


def main() -> int:
    if not PASSWORD:
        print("ERROR: set EVILEYE_E2E_PASSWORD", file=sys.stderr)
        return 2
    session = Session()
    if not session.login():
        print("ERROR: login failed", file=sys.stderr)
        return 2

    paths = _collect_paths(session)
    print(f"paths={len(paths)} cameras={CAMERAS} duration={DURATION_SEC}s")
    if not paths:
        print("ERROR: no media paths", file=sys.stderr)
        return 1

    fr = str(time.mktime(time.strptime(DATE + " 00:00:00", "%Y-%m-%d %H:%M:%S")))
    to = str(float(fr) + 86400)
    tl_q = {"date": DATE, "cameras": ",".join(CAMERAS), "from": fr, "to": to}
    det_q = {**tl_q, "ticks_only": "true"}

    stats = {"timeline": [], "detections": [], "media": []}
    deadline = time.time() + DURATION_SEC

    def one_wave():
        out = []
        out.append(("timeline", *session.get("/api/v1/playback/timeline", tl_q, timeout=20)[:2]))
        out.append(("detections", *session.get("/api/v1/playback/detections", det_q, timeout=45)[:2]))
        for path in paths:
            code, ms, _ = session.get(
                "/api/v1/playback/media",
                {"path": path},
                headers={"Range": "bytes=0-65535"},
                timeout=15,
            )
            out.append(("media", code, ms))
        return out

    waves = 0
    while time.time() < deadline:
        with ThreadPoolExecutor(max_workers=3) as pool:
            futs = [pool.submit(one_wave) for _ in range(2)]
            for fut in as_completed(futs):
                for kind, code, ms in fut.result():
                    stats[kind].append((code, ms))
        waves += 1
        time.sleep(0.2)

    def summarize(name: str):
        rows = stats[name]
        n503 = sum(1 for c, _ in rows if c == 503)
        n0 = sum(1 for c, _ in rows if c == 0)
        ok = sum(1 for c, _ in rows if c in (200, 206))
        p95 = sorted(ms for _, ms in rows)[max(0, int(0.95 * len(rows)) - 1)] if rows else 0
        return {"n": len(rows), "ok": ok, "n503": n503, "n0": n0, "p95_ms": round(p95, 1)}

    summary = {k: summarize(k) for k in stats}
    summary["waves"] = waves
    timeline_fail = summary["timeline"]["n503"] > 0 or summary["timeline"]["n0"] > 0
    media_hang = summary["media"]["p95_ms"] > 10000
    ok = not timeline_fail and not media_hang and summary["timeline"]["ok"] > 0
    print(json.dumps({"ok": ok, **summary}, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
