#!/usr/bin/env python3
"""HTTP timing harness for audit Stage 2 measured baseline.

Example:
  python scripts/audit_perf_probe.py \\
    --base http://127.0.0.1:8181 \\
    --cookie-jar /tmp/ee_audit_cj \\
    --date 2026-09-23 --run-id 334 --source-ids 0,1,2,3,4 \\
    --reps 21 --out /tmp/audit_perf_probe.json
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import MozillaCookieJar
from pathlib import Path
from typing import Any


def _percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return float("nan")
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_vals[int(k)]
    return sorted_vals[f] * (c - k) + sorted_vals[c] * (k - f)


def _stats(ms: list[float]) -> dict[str, float]:
    s = sorted(ms)
    return {
        "n": len(s),
        "p50_ms": round(_percentile(s, 50), 2),
        "p95_ms": round(_percentile(s, 95), 2),
        "p99_ms": round(_percentile(s, 99), 2),
        "mean_ms": round(statistics.fmean(s), 2) if s else float("nan"),
        "max_ms": round(max(s), 2) if s else float("nan"),
    }


class Client:
    def __init__(self, base: str, cookie_jar: Path | None):
        self.base = base.rstrip("/")
        handlers: list[Any] = []
        if cookie_jar and cookie_jar.exists():
            jar = MozillaCookieJar(str(cookie_jar))
            jar.load(ignore_discard=True, ignore_expires=True)
            handlers.append(urllib.request.HTTPCookieProcessor(jar))
        self.opener = urllib.request.build_opener(*handlers)

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        data: bytes | None = None,
    ) -> tuple[int, float, bytes, dict[str, str]]:
        url = self.base + path
        if params:
            url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        req = urllib.request.Request(url, data=data, method=method)
        for k, v in (headers or {}).items():
            req.add_header(k, v)
        t0 = time.perf_counter()
        try:
            with self.opener.open(req, timeout=90) as resp:
                body = resp.read()
                hdrs = {k.lower(): v for k, v in resp.headers.items()}
                code = resp.getcode() or 0
        except urllib.error.HTTPError as exc:
            body = exc.read() if exc.fp else b""
            hdrs = {k.lower(): v for k, v in (exc.headers or {}).items()}
            code = int(exc.code)
        ms = (time.perf_counter() - t0) * 1000.0
        return code, ms, body, hdrs

    def get_json(self, path: str, params: dict[str, Any] | None = None) -> Any:
        code, _, body, _ = self.request("GET", path, params=params)
        if code != 200:
            raise RuntimeError(f"GET {path} -> HTTP {code}: {body[:200]!r}")
        return json.loads(body.decode("utf-8"))


def _time_endpoint(
    client: Client,
    name: str,
    method: str,
    path: str,
    reps: int,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    warm: int = 2,
    raw_out: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    samples: list[float] = []
    codes: dict[str, int] = {}
    bytes_list: list[int] = []
    for i in range(reps + warm):
        phase = "warm" if i < warm else "measure"
        code, ms, body, _ = client.request(method, path, params=params, headers=headers)
        key = str(code)
        codes[key] = codes.get(key, 0) + 1
        if raw_out is not None:
            raw_out.append(
                {
                    "name": name,
                    "path": path,
                    "phase": phase,
                    "code": code,
                    "ms": round(ms, 3),
                    "bytes": len(body),
                    "ts": time.time(),
                }
            )
        if i >= warm:
            samples.append(ms)
            bytes_list.append(len(body))
    return {
        "name": name,
        "path": path,
        "params": params or {},
        "codes": codes,
        "bytes_p50": int(statistics.median(bytes_list)) if bytes_list else 0,
        "bytes_max": max(bytes_list) if bytes_list else 0,
        **_stats(samples),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", default="http://127.0.0.1:8181")
    ap.add_argument("--cookie-jar", type=Path, default=None)
    ap.add_argument("--date", default="2026-09-23")
    ap.add_argument("--run-id", type=int, default=None)
    ap.add_argument("--source-ids", default="")
    ap.add_argument("--camera", default="Cam1")
    ap.add_argument("--reps", type=int, default=21)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    client = Client(args.base, args.cookie_jar)
    source_ids = [int(x) for x in args.source_ids.split(",") if x.strip() != ""]
    run_id = args.run_id

    cams = client.get_json("/api/v1/state/cameras", {"scope": "current"})
    items = cams.get("items") or []
    if run_id is None and items:
        run_id = int(items[0]["run_id"])
    if not source_ids and items:
        source_ids = [int(i["source_id"]) for i in items]

    results: list[dict[str, Any]] = []
    raw_samples: list[dict[str, Any]] = []
    results.append(
        _time_endpoint(
            client,
            "state.cameras.current",
            "GET",
            "/api/v1/state/cameras",
            args.reps,
            params={"scope": "current"},
            raw_out=raw_samples,
        )
    )

    if run_id is not None and source_ids:
        for label, ids in (
            ("snapshot.1cam", source_ids[:1]),
            ("snapshot.4cam", source_ids[:4]),
            ("snapshot.all", source_ids),
        ):
            if not ids:
                continue
            samples: list[float] = []
            codes: dict[str, int] = {}
            bytes_total: list[int] = []
            warm = 1
            for rep in range(args.reps + warm):
                t0 = time.perf_counter()
                bsum = 0
                for sid in ids:
                    code, _, body, _ = client.request(
                        "GET",
                        f"/api/v1/runs/{run_id}/snapshot",
                        params={"source_id": sid},
                    )
                    codes[str(code)] = codes.get(str(code), 0) + 1
                    bsum += len(body)
                if rep >= warm:
                    samples.append((time.perf_counter() - t0) * 1000.0)
                    bytes_total.append(bsum)
            results.append(
                {
                    "name": label,
                    "n_sources": len(ids),
                    "codes": codes,
                    "bytes_p50": int(statistics.median(bytes_total)) if bytes_total else 0,
                    "bytes_max": max(bytes_total) if bytes_total else 0,
                    **_stats(samples),
                }
            )

    results.append(
        _time_endpoint(
            client,
            "playback.timeline",
            "GET",
            "/api/v1/playback/timeline",
            args.reps,
            params={"date": args.date, "cameras": args.camera},
            warm=1,
            raw_out=raw_samples,
        )
    )
    results.append(
        _time_endpoint(
            client,
            "playback.detections",
            "GET",
            "/api/v1/playback/detections",
            args.reps,
            params={
                "date": args.date,
                "cameras": args.camera,
                "ticks_only": "true",
            },
            warm=1,
            raw_out=raw_samples,
        )
    )
    results.append(
        _time_endpoint(
            client,
            "playback.events",
            "GET",
            "/api/v1/playback/events",
            args.reps,
            params={"date": args.date},
            warm=1,
            raw_out=raw_samples,
        )
    )

    try:
        tl = client.get_json("/api/v1/playback/timeline", {"date": args.date, "cameras": args.camera})
        media_path = None
        by_cam = (tl.get("by_camera") or {}) if isinstance(tl, dict) else {}
        entry = by_cam.get(args.camera) or {}
        # Timeline returns {segments, detection_ticks, events} per camera (R17).
        segs = entry.get("segments") if isinstance(entry, dict) else entry
        if isinstance(segs, list) and segs:
            media_path = (
                segs[0].get("path")
                or segs[0].get("file")
                or segs[0].get("rel_path")
                or segs[0].get("media_path")
            )
        if media_path:
            # F13: measure Range seek latency, not full-file download.
            results.append(
                _time_endpoint(
                    client,
                    "playback.media.range",
                    "GET",
                    "/api/v1/playback/media",
                    min(args.reps, 11),
                    params={"path": media_path},
                    headers={"Range": "bytes=0-65535"},
                    warm=1,
                    raw_out=raw_samples,
                )
            )
        else:
            results.append({"name": "playback.media.range", "skipped": "no segment path"})
    except Exception as exc:
        results.append({"name": "playback.media", "error": str(exc)})

    # Prefer /ready which embeds memory_cache_stats / state_thread_stats (R17).
    for path in (
        "/api/v1/ready",
        "/ready",
        "/api/v1/diagnostics/playback_cache",
        "/api/v1/system/status",
    ):
        code, ms, body, _ = client.request("GET", path)
        if code in (200, 304):
            try:
                parsed = json.loads(body.decode("utf-8"))
            except Exception:
                parsed = {"bytes": len(body)}
            results.append({"name": "aux", "path": path, "ms": round(ms, 2), "code": code, "body": parsed})
            break
        results.append({"name": "aux", "path": path, "code": code, "ms": round(ms, 2)})

    # Fail harness if required endpoints returned unexpected codes.
    # F13: every required endpoint must have at least one 200/304; state/snapshot included.
    required = {
        "playback.timeline",
        "playback.detections",
        "playback.events",
        "state.cameras.current",
    }
    bad = []
    for row in results:
        name = row.get("name")
        if name not in required:
            continue
        codes = row.get("codes") or {}
        ok = sum(int(codes.get(k, 0)) for k in ("200", "304", "206"))
        total = sum(int(v) for v in codes.values()) if codes else 0
        if total and ok == 0:
            bad.append(name)
    if bad:
        print(f"ERROR: required endpoints without 200/304/206: {bad}", file=sys.stderr)
        return 2

    import subprocess

    sha = ""
    try:
        sha = (
            subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(Path(__file__).resolve().parents[1]))
            .decode()
            .strip()
        )
    except Exception:
        sha = ""

    payload = {
        "base": args.base,
        "date": args.date,
        "run_id": run_id,
        "source_ids": source_ids,
        "camera": args.camera,
        "reps": args.reps,
        "git_sha": sha,
        "results": results,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    text = json.dumps(payload, indent=2)
    print(text)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")
        # Per-request raw samples (not aggregated report) — F13.
        samples_path = Path("reports") / f"audit_perf_samples_{time.strftime('%Y-%m-%d')}.jsonl"
        with samples_path.open("a", encoding="utf-8") as fh:
            for row in raw_samples:
                fh.write(json.dumps({"git_sha": sha, **row}, separators=(",", ":")) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
