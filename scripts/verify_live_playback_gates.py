#!/usr/bin/env python3
"""Verify live overlay + playback residual gates (L1u/L1/P1/P2/P3).

Reuse patterns from ensure_playback_test_user.py / diagnose_playback_wan.py.

Env:
  EVILEYE_E2E_BASE (default http://127.0.0.1:8181)
  EVILEYE_E2E_USER / EVILEYE_E2E_PASSWORD
  E2E_PLAYBACK_DATE / E2E_PLAYBACK_CAMERAS (default Cam1)
  EVILEYE_SKIP_VITEST=1 to skip L1u (not recommended)
  EVILEYE_SKIP_LIVE=1 to skip L1 soft API poll

Exit 0 only when required gates L1u + P0t + P1 + P2 pass.
"""
from __future__ import annotations

import json
import math
import os
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BASE = os.environ.get("EVILEYE_E2E_BASE", "http://127.0.0.1:8181").rstrip("/")
USER = os.environ.get("EVILEYE_E2E_USER", "playback-test@example.com")
PASSWORD = os.environ.get("EVILEYE_E2E_PASSWORD", "")
DATE = os.environ.get("E2E_PLAYBACK_DATE", time.strftime("%Y-%m-%d"))
CAMERAS = [c.strip() for c in os.environ.get("E2E_PLAYBACK_CAMERAS", "Cam1").split(",") if c.strip()]
PRIMARY_CAM = CAMERAS[0] if CAMERAS else "Cam1"
SKIP_VITEST = os.environ.get("EVILEYE_SKIP_VITEST", "").strip().lower() in ("1", "true", "yes")
SKIP_LIVE = os.environ.get("EVILEYE_SKIP_LIVE", "").strip().lower() in ("1", "true", "yes")
OUTPUT = os.environ.get("EVILEYE_VERIFY_OUTPUT", "")
CLIENT_DIAG = ROOT / "logs" / f"client_diag_{time.strftime('%Y%m%d')}.log"
EMPTY_RATE_BASELINE = 0.16


@dataclass
class GateResult:
    name: str
    required: bool
    passed: bool
    detail: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class Session:
    def __init__(self) -> None:
        self._cookie = ""

    def login(self, username: str, password: str) -> bool:
        url = f"{BASE}/api/v1/auth/login"
        body = json.dumps({"username": username, "password": password}).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                set_cookie = resp.headers.get("Set-Cookie", "")
                self._cookie = set_cookie.split(";")[0] if set_cookie else ""
                return 200 <= resp.status < 300 and bool(self._cookie)
        except Exception:
            return False

    def get(
        self,
        path: str,
        query: dict[str, str] | None = None,
        *,
        headers: dict[str, str] | None = None,
        timeout: float = 60.0,
        read_body: bool = True,
    ) -> tuple[int, float, dict[str, str], bytes]:
        qs = urllib.parse.urlencode({k: v for k, v in (query or {}).items() if v is not None and v != ""})
        url = f"{BASE}{path}?{qs}" if qs else f"{BASE}{path}"
        req = urllib.request.Request(url, method="GET")
        if self._cookie:
            req.add_header("Cookie", self._cookie)
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read() if read_body else b""
                if not read_body:
                    # Still drain a little for Range probes that only need timing/status.
                    try:
                        raw = resp.read(65536)
                    except Exception:
                        raw = b""
                hdrs = {k.lower(): v for k, v in resp.headers.items()}
                return resp.status, time.perf_counter() - t0, hdrs, raw
        except urllib.error.HTTPError as exc:
            raw = exc.read() if exc.fp else b""
            hdrs = {k.lower(): v for k, v in exc.headers.items()}
            return exc.code, time.perf_counter() - t0, hdrs, raw
        except Exception as exc:  # noqa: BLE001
            return 0, time.perf_counter() - t0, {}, str(exc).encode("utf-8")


def _p95(samples: list[float]) -> float:
    if not samples:
        return float("inf")
    if len(samples) == 1:
        return samples[0]
    ordered = sorted(samples)
    idx = max(0, min(len(ordered) - 1, math.ceil(0.95 * len(ordered)) - 1))
    return ordered[idx]


def gate_l1u() -> GateResult:
    if SKIP_VITEST:
        return GateResult("L1u", True, False, error="EVILEYE_SKIP_VITEST set")
    frontend = ROOT / "evileye" / "api" / "frontend"
    cmd = ["npm", "test", "--", "src/features/live/useRunMetadataWs.test.ts"]
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(frontend),
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except Exception as exc:  # noqa: BLE001
        return GateResult("L1u", True, False, error=str(exc))
    ok = proc.returncode == 0
    return GateResult(
        "L1u",
        True,
        ok,
        detail={"returncode": proc.returncode, "stdout_tail": (proc.stdout or "")[-800:]},
        error=None if ok else (proc.stderr or proc.stdout or "vitest failed")[-500:],
    )


def _active_run_id(session: Session) -> int | None:
    code, _, _, raw = session.get("/api/v1/state/runs")
    if code == 200:
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            payload = {}
        current = payload.get("current_run") if isinstance(payload, dict) else None
        if isinstance(current, dict) and current.get("id") is not None:
            state = str(current.get("state") or "").lower()
            if state in ("running", "active", "started", "processing", "") or current.get("alive"):
                return int(current["id"])
        items = payload.get("runs") or payload.get("items") or []
        if isinstance(items, dict):
            items = list(items.values())
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict) or item.get("id") is None:
                continue
            state = str(item.get("state") or item.get("status") or "").lower()
            if state in ("running", "active", "started", "processing") or item.get("alive"):
                return int(item["id"])
    # Legacy fallback
    code, _, _, raw = session.get("/api/v1/runs")
    if code != 200:
        return None
    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        return None
    items = payload if isinstance(payload, list) else payload.get("items") or payload.get("runs") or []
    for item in items:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or item.get("state") or "").lower()
        rid = item.get("id") or item.get("run_id")
        if rid is None:
            continue
        if status in ("running", "active", "started", "processing") or item.get("active"):
            return int(rid)
    return None


def gate_l1(session: Session) -> GateResult:
    if SKIP_LIVE:
        return GateResult("L1", False, True, detail={"skipped": True})
    rid = _active_run_id(session)
    if rid is None:
        return GateResult("L1", False, True, detail={"skipped": True, "reason": "no_active_run"})
    samples = 0
    empties = 0
    flicker = 0
    prev_n: int | None = None
    prev_fid: Any = None
    deadline = time.time() + 20.0
    while time.time() < deadline:
        code, _, _, raw = session.get(f"/api/v1/runs/{rid}/metadata", {"source_id": "0"}, timeout=5)
        if code == 200:
            try:
                payload = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                payload = {}
            n = len(payload.get("objects") or [])
            fid = payload.get("frame_id")
            samples += 1
            if n == 0:
                empties += 1
            if prev_n is not None and prev_n > 0 and n == 0 and fid != prev_fid:
                flicker += 1
            prev_n = n
            prev_fid = fid
        time.sleep(0.25)
    empty_rate = (empties / samples) if samples else 1.0
    flicker_rate = (flicker / max(1, samples - 1)) if samples > 1 else 0.0
    non_empty = samples - empties
    detail = {
        "run_id": rid,
        "samples": samples,
        "non_empty": non_empty,
        "empty_rate": round(empty_rate, 4),
        "flicker_rate": round(flicker_rate, 4),
        "baseline_cap": round(EMPTY_RATE_BASELINE * 1.1, 4),
    }
    # Quiet scene: cannot judge API empty flicker vs baseline.
    if non_empty < 5:
        return GateResult(
            "L1",
            False,
            True,
            detail={**detail, "skipped": True, "reason": "insufficient_dense_samples"},
        )
    ok = empty_rate <= EMPTY_RATE_BASELINE * 1.1 and flicker_rate <= 0.05
    return GateResult(
        "L1",
        False,
        ok,
        detail=detail,
        error=None if ok else f"empty_rate={empty_rate:.3f} flicker_rate={flicker_rate:.3f}",
    )


def _mid_segment(session: Session) -> tuple[float | None, str | None, dict[str, Any]]:
    fr = str(time.mktime(time.strptime(DATE + " 00:00:00", "%Y-%m-%d %H:%M:%S")))
    to = str(float(fr) + 86400)
    code, _, _, raw = session.get(
        "/api/v1/playback/timeline",
        {"date": DATE, "cameras": ",".join(CAMERAS), "from": fr, "to": to, "segments_only": "true"},
        timeout=90,
    )
    info: dict[str, Any] = {"timeline_status": code}
    if code != 200:
        return None, None, info
    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        return None, None, {**info, "error": "bad_json"}
    by_cam = payload.get("by_camera") or payload.get("segments_by_camera") or {}
    cam_payload = by_cam.get(PRIMARY_CAM) if isinstance(by_cam, dict) else None
    segs = None
    if isinstance(cam_payload, list):
        segs = cam_payload
    elif isinstance(cam_payload, dict):
        segs = cam_payload.get("segments") or cam_payload.get("items") or []
    if not segs:
        segs = payload.get("segments") or []
        if isinstance(segs, dict):
            inner = segs.get(PRIMARY_CAM) or []
            segs = inner.get("segments") if isinstance(inner, dict) else inner
    if not isinstance(segs, list) or not segs:
        return None, None, {**info, "error": "no_segments", "keys": list(payload.keys())[:12]}
    # Prefer playable mid segment
    playable = [s for s in segs if isinstance(s, dict) and s.get("playable", True)]
    pool = playable or [s for s in segs if isinstance(s, dict)]
    if not pool:
        return None, None, {**info, "error": "no_dict_segments"}
    seg = pool[len(pool) // 2] if len(pool) > 1 else pool[0]
    start = float(seg.get("start_ts") or seg.get("start") or 0)
    end = float(seg.get("end_ts") or seg.get("end") or start)
    mid = start + max(0.5, (end - start) * 0.5)
    path = seg.get("path") or seg.get("rel_path") or seg.get("media_path")
    info.update({"start": start, "end": end, "mid": mid, "path": path, "n_segments": len(segs)})
    return mid, path, info


def gate_p1(session: Session, mid_ts: float | None, *, date: str | None = None) -> GateResult:
    if mid_ts is None:
        return GateResult("P1", True, False, error="no mid-segment ts")
    date_q = date or DATE
    # Warm sticky/happy cache once so p95 reflects steady-state (cold miss measured separately).
    session.get(
        "/api/v1/playback/metadata",
        {"camera": PRIMARY_CAM, "ts": f"{mid_ts:.3f}", "date": date_q},
        timeout=30,
    )
    durations: list[float] = []
    statuses: list[int] = []
    caches: list[str | None] = []
    for _ in range(10):
        code, dt, headers, _raw = session.get(
            "/api/v1/playback/metadata",
            {
                "camera": PRIMARY_CAM,
                "ts": f"{mid_ts:.3f}",
                "date": date_q,
            },
            timeout=30,
        )
        statuses.append(code)
        durations.append(dt * 1000.0)
        caches.append(headers.get("x-playback-cache"))
        time.sleep(0.05)
    n503 = sum(1 for s in statuses if s == 503)
    p95 = _p95(durations)
    ok = n503 == 0 and all(s == 200 for s in statuses) and p95 < 5000.0
    return GateResult(
        "P1",
        True,
        ok,
        detail={
            "n503": n503,
            "statuses": statuses,
            "caches": caches,
            "p95_ms": round(p95, 1),
            "mean_ms": round(statistics.mean(durations), 1) if durations else None,
            "mid_ts": mid_ts,
            "date": date_q,
        },
        error=None if ok else f"n503={n503} p95_ms={p95:.1f}",
    )


def gate_p2(session: Session, media_path: str | None) -> GateResult:
    if not media_path:
        return GateResult("P2", True, False, error="no media path from timeline")
    durations: list[float] = []
    statuses: list[int] = []
    for _ in range(8):
        code, dt, _, _raw = session.get(
            "/api/v1/playback/media",
            {"path": media_path},
            headers={"Range": "bytes=0-65535"},
            timeout=30,
            read_body=True,
        )
        statuses.append(code)
        durations.append(dt * 1000.0)
        time.sleep(0.05)
    p95 = _p95(durations)
    ok_status = all(s in (200, 206) for s in statuses)
    ok = ok_status and p95 < 300.0
    return GateResult(
        "P2",
        True,
        ok,
        detail={
            "statuses": statuses,
            "p95_ms": round(p95, 1),
            "mean_ms": round(statistics.mean(durations), 1) if durations else None,
            "path": media_path,
        },
        error=None if ok else f"status_ok={ok_status} p95_ms={p95:.1f}",
    )


def gate_p0t(session: Session) -> GateResult:
    """Timeline cold/warm: must not 503; p95 after warmup < 5s."""
    cams = ",".join(CAMERAS)
    fr = str(time.mktime(time.strptime(DATE + " 00:00:00", "%Y-%m-%d %H:%M:%S")))
    to = str(float(fr) + 86400)
    q = {"date": DATE, "cameras": cams, "from": fr, "to": to}
    # warmup (may be cold rebuild)
    session.get("/api/v1/playback/timeline", q, timeout=90)
    durations: list[float] = []
    statuses: list[int] = []
    caches: list[str | None] = []
    for _ in range(10):
        code, dt, headers, _raw = session.get("/api/v1/playback/timeline", q, timeout=30)
        statuses.append(code)
        durations.append(dt * 1000.0)
        caches.append(headers.get("x-playback-cache"))
        time.sleep(0.05)
    n503 = sum(1 for s in statuses if s == 503)
    p95 = _p95(durations)
    ok = n503 == 0 and all(s == 200 for s in statuses) and p95 < 5000.0
    return GateResult(
        "P0t",
        True,
        ok,
        detail={
            "n503": n503,
            "statuses": statuses,
            "caches": caches,
            "p95_ms": round(p95, 1),
            "mean_ms": round(statistics.mean(durations), 1) if durations else None,
            "cameras": cams,
        },
        error=None if ok else f"n503={n503} p95_ms={p95:.1f}",
    )


def gate_p2m(session: Session, media_paths: list[str]) -> GateResult:
    """Parallel Range waves across cameras; 503 busy ok ≤20%, no hangs."""
    paths = [p for p in media_paths if p][:5]
    if not paths:
        return GateResult("P2m", False, True, detail={"skipped": True, "reason": "no_paths"})
    statuses: list[int] = []
    durations: list[float] = []
    for _wave in range(4):
        # sequential burst approximates browser parallel without threads
        for path in paths:
            code, dt, _, _raw = session.get(
                "/api/v1/playback/media",
                {"path": path},
                headers={"Range": "bytes=0-65535"},
                timeout=15,
            )
            statuses.append(code)
            durations.append(dt * 1000.0)
    n503 = sum(1 for s in statuses if s == 503)
    n_ok = sum(1 for s in statuses if s in (200, 206))
    n_other = len(statuses) - n503 - n_ok
    frac503 = n503 / max(1, len(statuses))
    hung = any(d > 10000 for d in durations)
    ok = n_other == 0 and not hung and frac503 <= 0.20 and n_ok > 0
    return GateResult(
        "P2m",
        False,
        ok,
        detail={
            "n": len(statuses),
            "n503": n503,
            "frac503": round(frac503, 3),
            "p95_ms": round(_p95(durations), 1),
            "paths": len(paths),
        },
        error=None if ok else f"frac503={frac503:.2f} other={n_other} hung={hung}",
    )


def _paths_by_camera(session: Session) -> list[str]:
    """Collect one media path per camera from timeline."""
    fr = str(time.mktime(time.strptime(DATE + " 00:00:00", "%Y-%m-%d %H:%M:%S")))
    to = str(float(fr) + 86400)
    code, _, _, raw = session.get(
        "/api/v1/playback/timeline",
        {"date": DATE, "cameras": ",".join(CAMERAS), "from": fr, "to": to, "segments_only": "true"},
        timeout=90,
    )
    if code != 200:
        return []
    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        return []
    by_cam = payload.get("by_camera") or {}
    paths: list[str] = []
    for cam in CAMERAS:
        cam_payload = by_cam.get(cam) if isinstance(by_cam, dict) else None
        segs = []
        if isinstance(cam_payload, dict):
            segs = cam_payload.get("segments") or []
        elif isinstance(cam_payload, list):
            segs = cam_payload
        playable = [s for s in segs if isinstance(s, dict) and s.get("playable", True) and s.get("path")]
        if playable:
            paths.append(str(playable[len(playable) // 2]["path"]))
    return paths


def gate_p3() -> GateResult:
    if not CLIENT_DIAG.is_file():
        return GateResult("P3", False, False, detail={"skipped": False}, error="client_diag missing")
    try:
        lines = CLIENT_DIAG.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return GateResult("P3", False, False, error=str(exc))
    # Look at last ~400 lines for recent play window.
    window = lines[-400:]
    slot = 0
    rs0 = 0
    for line in window:
        if "slot_state" not in line and "video_error" not in line:
            continue
        try:
            # client diag may be JSON or key=value; try JSON first
            if line.strip().startswith("{"):
                obj = json.loads(line)
            else:
                # best-effort: look for readyState
                if "readyState" not in line:
                    continue
                obj = {"kind": "slot_state", "readyState": 0 if "readyState=0" in line or '"readyState":0' in line else 1}
            kind = str(obj.get("kind") or obj.get("event") or "")
            if kind not in ("slot_state", "video_error") and "slot_state" not in line:
                continue
            slot += 1
            rs = obj.get("readyState")
            if rs == 0 or rs == "0":
                rs0 += 1
        except Exception:
            if "readyState=0" in line or '"readyState": 0' in line or '"readyState":0' in line:
                slot += 1
                rs0 += 1
    frac = (rs0 / slot) if slot else 0.0
    ok = slot == 0 or frac < 0.15
    return GateResult(
        "P3",
        False,
        ok,
        detail={"samples": slot, "readyState0": rs0, "fraction": round(frac, 4), "log": str(CLIENT_DIAG)},
        error=None if ok else f"readyState0_fraction={frac:.3f}",
    )


def main() -> int:
    print(f"BASE={BASE} USER={USER} DATE={DATE} CAMERAS={CAMERAS}")
    gates: list[GateResult] = []

    gates.append(gate_l1u())
    print(f"L1u: {'PASS' if gates[-1].passed else 'FAIL'} {gates[-1].error or gates[-1].detail}")

    if not PASSWORD:
        print("ERROR: set EVILEYE_E2E_PASSWORD", file=sys.stderr)
        summary = {"gates": [asdict(g) for g in gates], "ok": False}
        if OUTPUT:
            Path(OUTPUT).write_text(json.dumps(summary, indent=2), encoding="utf-8")
        return 2

    session = Session()
    if not session.login(USER, PASSWORD):
        print(f"ERROR: login failed for {USER}", file=sys.stderr)
        gates.append(GateResult("auth", True, False, error="login failed"))
        summary = {"gates": [asdict(g) for g in gates], "ok": False}
        if OUTPUT:
            Path(OUTPUT).write_text(json.dumps(summary, indent=2), encoding="utf-8")
        return 2

    gates.append(gate_l1(session))
    print(f"L1: {'PASS' if gates[-1].passed else 'FAIL'} {gates[-1].error or gates[-1].detail}")

    gates.append(gate_p0t(session))
    print(f"P0t: {'PASS' if gates[-1].passed else 'FAIL'} {gates[-1].error or gates[-1].detail}")

    mid_ts, media_path, seg_info = _mid_segment(session)
    print(f"segment: {seg_info}")
    seg_date = DATE
    if media_path:
        # Prefer date folder embedded in Streams/<date>/...
        parts = Path(media_path).parts
        if "Streams" in parts:
            i = parts.index("Streams")
            if i + 1 < len(parts):
                seg_date = parts[i + 1]

    gates.append(gate_p1(session, mid_ts, date=seg_date))
    print(f"P1: {'PASS' if gates[-1].passed else 'FAIL'} {gates[-1].error or gates[-1].detail}")

    gates.append(gate_p2(session, media_path))
    print(f"P2: {'PASS' if gates[-1].passed else 'FAIL'} {gates[-1].error or gates[-1].detail}")

    multi_paths = _paths_by_camera(session)
    if media_path and media_path not in multi_paths:
        multi_paths = [media_path] + multi_paths
    gates.append(gate_p2m(session, multi_paths))
    print(f"P2m: {'PASS' if gates[-1].passed else 'FAIL'} {gates[-1].error or gates[-1].detail}")

    gates.append(gate_p3())
    print(f"P3: {'PASS' if gates[-1].passed else 'FAIL'} {gates[-1].error or gates[-1].detail}")

    required_ok = all(g.passed for g in gates if g.required)
    summary = {
        "ok": required_ok,
        "required_ok": required_ok,
        "gates": [asdict(g) for g in gates],
        "segment": seg_info,
        "base": BASE,
        "date": DATE,
        "cameras": CAMERAS,
    }
    print(json.dumps({"ok": required_ok, "gates": {g.name: g.passed for g in gates}}, indent=2))
    if OUTPUT:
        Path(OUTPUT).write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"wrote {OUTPUT}")
    return 0 if required_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
