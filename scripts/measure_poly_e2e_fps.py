#!/usr/bin/env python3
"""Measure end-to-end tracker latency/FPS (source frame -> trackers output)."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("EVILEYE_PIPELINE_TIMELINE", "0")

from poly_mode_compare_lib import REPO_ROOT, write_bench_config


def _frame_key(item) -> tuple[int, int] | None:
    frame = item
    if isinstance(item, (list, tuple)) and len(item) >= 2:
        frame = item[1]
        data = item[0]
        sid = getattr(data, "source_id", None) or getattr(frame, "source_id", None)
    else:
        sid = getattr(item, "source_id", None)
    fid = getattr(frame, "frame_id", None)
    if sid is None or fid is None:
        return None
    try:
        return int(sid), int(fid)
    except (TypeError, ValueError):
        return None


def measure(
    config_path: Path,
    *,
    warmup_sec: float,
    active_sec: float,
) -> dict[str, Any]:
    from evileye.core.logging_config import setup_evileye_logging
    from evileye.core.mp_context import ensure_spawn_start_method
    from evileye.pipelines.pipeline_surveillance import PipelineSurveillance

    ensure_spawn_start_method()
    setup_evileye_logging(log_level="WARNING")

    overlay = write_bench_config(config_path)
    try:
        import json as _json

        cfg = _json.loads(overlay.read_text(encoding="utf-8"))
        pipeline = PipelineSurveillance()
        pipeline.set_params(**cfg["pipeline"])
        pipeline.init()
        pipeline.start()

        pending: dict[tuple[int, int], float] = {}
        latencies_ms: list[float] = []
        tracker_keys: set[tuple[int, int]] = set()
        source_keys: set[tuple[int, int]] = set()

        time.sleep(warmup_sec)
        t_start = time.monotonic()
        ticks = 0
        try:
            while time.monotonic() - t_start < active_sec:
                t_tick = time.monotonic()
                res = pipeline.process()
                ticks += 1
                for item in res.get("sources") or []:
                    key = _frame_key(item)
                    if key:
                        pending[key] = t_tick
                        source_keys.add(key)
                for item in res.get("trackers") or []:
                    key = _frame_key(item)
                    if key and key in pending:
                        latencies_ms.append((time.monotonic() - pending.pop(key)) * 1000.0)
                        tracker_keys.add(key)
        finally:
            try:
                pipeline.stop()
            except Exception:
                pass

        active_elapsed = max(0.001, time.monotonic() - t_start)
        sorted_lat = sorted(latencies_ms)
        p50 = sorted_lat[len(sorted_lat) // 2] if sorted_lat else None
        p95_idx = int(round(0.95 * (len(sorted_lat) - 1))) if sorted_lat else 0
        p95 = sorted_lat[p95_idx] if sorted_lat else None
        unmatched = len(pending)
        return {
            "config": str(config_path.relative_to(REPO_ROOT)),
            "warmup_sec": warmup_sec,
            "active_sec": active_sec,
            "ticks": ticks,
            "source_frames": len(source_keys),
            "tracker_matches": len(tracker_keys),
            "e2e_tracker_fps": round(len(tracker_keys) / active_elapsed, 4),
            "e2e_p50_ms": round(p50, 2) if p50 is not None else None,
            "e2e_p95_ms": round(p95, 2) if p95 is not None else None,
            "pending_unmatched": unmatched,
            "pending_unmatched_pct": round(
                100.0 * unmatched / max(1, len(source_keys)), 2
            ),
        }
    finally:
        try:
            overlay.unlink(missing_ok=True)
        except OSError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description="E2E tracker FPS for poly-videos config.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--warmup-sec", type=float, default=30.0)
    parser.add_argument("--active-sec", type=float, default=120.0)
    parser.add_argument(
        "--out",
        default="reports/poly_videos_mode_compare/e2e_measure.json",
    )
    args = parser.parse_args()

    config_path = (REPO_ROOT / args.config).resolve()
    result = measure(
        config_path,
        warmup_sec=args.warmup_sec,
        active_sec=args.active_sec,
    )
    out_path = (REPO_ROOT / args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
