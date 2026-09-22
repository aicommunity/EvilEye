#!/usr/bin/env python3
"""Playback WAN / cache diagnostics: API timings, cache headers, on-disk index mtime.

Usage:
  EVILEYE_E2E_BASE=https://traefik-host/ \\
  EVILEYE_E2E_USER=playback-test@local EVILEYE_E2E_PASSWORD=... \\
  E2E_PLAYBACK_DATE=2026-08-19 E2E_PLAYBACK_CAMERAS=Cam1,Cam2 \\
  python3 scripts/diagnose_playback_wan.py --scenario all --output /tmp/wan_probe.json

Scenarios:
  cold            C1: clear memory cache (debug) + timeline
  warm            C2: repeat timeline without clear
  admin_then_user C3: admin timeline then test-user timeline
  user_alone      C4: test-user only (same as cold if cache cleared)
  cold_date       C5: timeline for E2E_PLAYBACK_COLD_DATE
  all             run all applicable scenarios
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

BASE = os.environ.get("EVILEYE_E2E_BASE", "http://127.0.0.1:8181").rstrip("/")
USER = os.environ.get("EVILEYE_E2E_USER", "playback-test@example.com")
PASSWORD = os.environ.get("EVILEYE_E2E_PASSWORD", "")
ADMIN_USER = os.environ.get("EVILEYE_E2E_ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("EVILEYE_E2E_ADMIN_PASSWORD", os.environ.get("EVILEYE_E2E_PASSWORD", "admin"))
DATE = os.environ.get("E2E_PLAYBACK_DATE", time.strftime("%Y-%m-%d"))
COLD_DATE = os.environ.get("E2E_PLAYBACK_COLD_DATE", DATE)
CAMERAS = os.environ.get("E2E_PLAYBACK_CAMERAS", "Cam1")
DATA_ROOT = os.environ.get("EVILEYE_DATA_ROOT", "")


@dataclass
class RequestResult:
    route: str
    status: int
    duration_sec: float
    cache_header: str | None = None
    stale: bool | None = None
    error: str | None = None


@dataclass
class ScenarioReport:
    name: str
    requests: list[RequestResult] = field(default_factory=list)
    index_mtime: dict[str, float | None] = field(default_factory=dict)
    ready_before: dict[str, Any] = field(default_factory=dict)
    ready_after: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


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
        except urllib.error.HTTPError:
            return False
        except Exception:
            return False

    def _auth_request(self, req: urllib.request.Request) -> urllib.request.Request:
        if self._cookie:
            req.add_header("Cookie", self._cookie)
        return req

    def get(self, path: str, query: dict[str, str] | None = None) -> tuple[int, float, dict[str, str], bytes]:
        qs = urllib.parse.urlencode({k: v for k, v in (query or {}).items() if v is not None and v != ""})
        url = f"{BASE}{path}?{qs}" if qs else f"{BASE}{path}"
        req = self._auth_request(urllib.request.Request(url, method="GET"))
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                raw = resp.read()
                headers = {k.lower(): v for k, v in resp.headers.items()}
                return resp.status, time.perf_counter() - t0, headers, raw
        except urllib.error.HTTPError as exc:
            raw = exc.read() if exc.fp else b""
            headers = {k.lower(): v for k, v in exc.headers.items()}
            return exc.code, time.perf_counter() - t0, headers, raw
        except Exception as exc:  # noqa: BLE001
            return 0, time.perf_counter() - t0, {}, str(exc).encode("utf-8")

    def post(self, path: str) -> tuple[int, float, dict[str, str], bytes]:
        url = f"{BASE}{path}"
        req = self._auth_request(urllib.request.Request(url, method="POST"))
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
                headers = {k.lower(): v for k, v in resp.headers.items()}
                return resp.status, time.perf_counter() - t0, headers, raw
        except urllib.error.HTTPError as exc:
            raw = exc.read() if exc.fp else b""
            headers = {k.lower(): v for k, v in exc.headers.items()}
            return exc.code, time.perf_counter() - t0, headers, raw
        except Exception as exc:  # noqa: BLE001
            return 0, time.perf_counter() - t0, {}, str(exc).encode("utf-8")


def _day_bounds(date: str) -> tuple[str, str]:
    start = time.mktime(time.strptime(date + " 00:00:00", "%Y-%m-%d %H:%M:%S"))
    return str(start), str(start + 86400)


def _index_paths(date: str) -> dict[str, Path]:
    root = Path(DATA_ROOT) if DATA_ROOT else None
    if root is None:
        try:
            from evileye.api.core.playback_metadata_service import _load_params_for_run, _playback_data_dir

            params = _load_params_for_run(None)
            root = _playback_data_dir(params)
        except Exception:
            return {}
    det = root / "Detections" / date / "Metadata" / "detection_ticks.json"
    seg = root / "Streams" / date / "_timeline_segments.json"
    ev = root / "Events" / date / "Metadata" / "event_intervals.json"
    return {
        "detection_ticks": det,
        "segment_index": seg,
        "event_intervals": ev,
    }


def _index_mtime(date: str) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    for name, path in _index_paths(date).items():
        try:
            out[name] = path.stat().st_mtime if path.is_file() else None
        except OSError:
            out[name] = None
    return out


def _ready(session: Session) -> dict[str, Any]:
    code, _, _, raw = session.get("/ready")
    if code != 200:
        return {"status": "error", "http": code}
    try:
        return json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        return {"status": "error", "raw": raw[:200].decode("utf-8", "replace")}


def _timeline(session: Session, date: str, cameras: str) -> RequestResult:
    fr, to = _day_bounds(date)
    code, dt, headers, raw = session.get(
        "/api/v1/playback/timeline",
        {"date": date, "cameras": cameras, "from": fr, "to": to},
    )
    stale = None
    if code == 200:
        try:
            payload = json.loads(raw.decode("utf-8"))
            stale = bool(payload.get("stale"))
        except json.JSONDecodeError:
            pass
    return RequestResult(
        route="timeline",
        status=code,
        duration_sec=dt,
        cache_header=headers.get("x-playback-cache"),
        stale=stale,
        error=None if code else raw.decode("utf-8", "replace")[:200],
    )


def _cameras(session: Session, date: str) -> RequestResult:
    code, dt, headers, raw = session.get("/api/v1/playback/cameras", {"date": date})
    return RequestResult(
        route="cameras",
        status=code,
        duration_sec=dt,
        cache_header=headers.get("x-playback-cache"),
        error=None if code else raw.decode("utf-8", "replace")[:200],
    )


def _detections(session: Session, date: str, cameras: str) -> RequestResult:
    fr, to = _day_bounds(date)
    code, dt, headers, raw = session.get(
        "/api/v1/playback/detections",
        {"date": date, "cameras": cameras, "from": fr, "to": to, "ticks_only": "true"},
    )
    return RequestResult(
        route="detections",
        status=code,
        duration_sec=dt,
        cache_header=headers.get("x-playback-cache"),
        error=None if code else raw.decode("utf-8", "replace")[:200],
    )


def _clear_memory_cache(admin: Session) -> tuple[bool, str]:
    code, dt, _, raw = admin.post("/api/v1/playback/_debug/clear-memory-cache")
    if code == 200:
        return True, raw.decode("utf-8", "replace")
    return False, f"http {code}: {raw[:200].decode('utf-8', 'replace')}"


def run_scenario(name: str, date: str = DATE) -> ScenarioReport:
    report = ScenarioReport(name=name)
    report.index_mtime = _index_mtime(date)

    if name == "cold":
        admin = Session()
        if not admin.login(ADMIN_USER, ADMIN_PASSWORD):
            report.notes.append("admin login failed; skip memory cache clear")
        else:
            ok, msg = _clear_memory_cache(admin)
            report.notes.append(f"clear_memory_cache: {ok} ({msg})")
        user = Session()
        if not user.login(USER, PASSWORD):
            report.notes.append("test-user login failed")
            return report
        report.ready_before = _ready(user)
        report.requests.extend([_cameras(user, date), _timeline(user, date, CAMERAS), _detections(user, date, CAMERAS)])
        report.ready_after = _ready(user)
        return report

    if name == "warm":
        user = Session()
        if not user.login(USER, PASSWORD):
            report.notes.append("test-user login failed")
            return report
        report.ready_before = _ready(user)
        report.requests.extend([_timeline(user, date, CAMERAS), _detections(user, date, CAMERAS)])
        report.ready_after = _ready(user)
        return report

    if name == "admin_then_user":
        admin = Session()
        user = Session()
        if not admin.login(ADMIN_USER, ADMIN_PASSWORD):
            report.notes.append("admin login failed")
            return report
        if not user.login(USER, PASSWORD):
            report.notes.append("test-user login failed")
            return report
        admin_cams = os.environ.get("E2E_PLAYBACK_ADMIN_CAMERAS", CAMERAS)
        report.notes.append(f"admin warms with cameras={admin_cams}")
        report.requests.append(_timeline(admin, date, admin_cams))
        report.index_mtime = _index_mtime(date)
        report.requests.append(_timeline(user, date, CAMERAS))
        return report

    if name == "user_alone":
        user = Session()
        if not user.login(USER, PASSWORD):
            report.notes.append("test-user login failed")
            return report
        report.requests.extend([_cameras(user, date), _timeline(user, date, CAMERAS)])
        return report

    if name == "cold_date":
        user = Session()
        if not user.login(USER, PASSWORD):
            report.notes.append("test-user login failed")
            return report
        report.index_mtime = _index_mtime(COLD_DATE)
        report.notes.append(f"cold_date={COLD_DATE}")
        report.requests.extend([_timeline(user, COLD_DATE, CAMERAS), _detections(user, COLD_DATE, CAMERAS)])
        return report

    report.notes.append(f"unknown scenario: {name}")
    return report


def _summarize(reports: list[ScenarioReport]) -> dict[str, Any]:
    summary: dict[str, Any] = {"scenarios": {}}
    cold_tl = warm_tl = None
    for rep in reports:
        tl = [r for r in rep.requests if r.route == "timeline"]
        durs = [r.duration_sec for r in tl if r.status == 200]
        summary["scenarios"][rep.name] = {
            "timeline_p50": statistics.median(durs) if durs else None,
            "timeline_max": max(durs) if durs else None,
            "cache_headers": [r.cache_header for r in tl],
            "stale": [r.stale for r in tl],
            "errors503": sum(1 for r in rep.requests if r.status in (0, 503)),
            "index_mtime": rep.index_mtime,
            "notes": rep.notes,
        }
        if rep.name == "cold" and durs:
            cold_tl = durs[-1]
        if rep.name == "warm" and durs:
            warm_tl = durs[-1]
    if cold_tl and warm_tl and warm_tl > 0:
        summary["c1_c2_ratio"] = round(cold_tl / warm_tl, 2)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Playback WAN/cache diagnostics")
    parser.add_argument(
        "--scenario",
        default="all",
        choices=["cold", "warm", "admin_then_user", "user_alone", "cold_date", "all"],
    )
    parser.add_argument("--output", default="", help="Write JSON report to path")
    args = parser.parse_args()

    scenarios = (
        ["cold", "warm", "admin_then_user", "user_alone", "cold_date"]
        if args.scenario == "all"
        else [args.scenario]
    )

    print(f"BASE={BASE} DATE={DATE} CAMERAS={CAMERAS} USER={USER}")
    reports = [run_scenario(s) for s in scenarios]
    payload = {
        "base": BASE,
        "date": DATE,
        "cameras": CAMERAS,
        "timestamp": time.time(),
        "reports": [{**asdict(r)} for r in reports],
        "summary": _summarize(reports),
    }

    text = json.dumps(payload, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"Wrote {args.output}")
    else:
        print(text)

    errors = sum(
        1
        for r in reports
        for req in r.requests
        if req.status not in (200, 401) and req.status != 0
    )
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
