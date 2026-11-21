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

if __package__:
    from .poly_mode_compare_lib import REPO_ROOT, write_bench_config
else:
    from poly_mode_compare_lib import REPO_ROOT, write_bench_config

STALENESS_REF = 6.2
STALENESS_MIN = 5.9
STALENESS_MAX = 6.5


def staleness_in_band(mean_staleness: float | None) -> bool:
    if mean_staleness is None:
        return False
    return STALENESS_MIN <= mean_staleness <= STALENESS_MAX


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


def _percentile_int(values: list[int], pct: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = int(round((pct / 100.0) * (len(ordered) - 1)))
    return ordered[max(0, min(idx, len(ordered) - 1))]



class RuntimeStatsSampler:
    """Summarize module queue and health counters over one active measurement."""

    _COUNTERS = ("input_queue_dropped", "input_queue_rejected")

    def __init__(self, baseline: dict[str, Any]):
        self._baseline: dict[str, dict[str, int]] = {}
        self._latest: dict[str, dict[str, Any]] = {}
        self._modules: dict[str, dict[str, Any]] = {}
        self._pipeline_degraded_seen = False
        self._samples = 0
        self.observe(baseline, establish_baseline=True)

    @staticmethod
    def _integer(value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def observe(
        self, snapshot: dict[str, Any], *, establish_baseline: bool = False
    ) -> None:
        self._samples += 1
        self._pipeline_degraded_seen |= bool(snapshot.get("degraded"))
        modules = snapshot.get("modules")
        if not isinstance(modules, dict):
            return

        for module_id, raw_stats in modules.items():
            if not isinstance(raw_stats, dict):
                continue
            stats = dict(raw_stats)
            if establish_baseline or module_id not in self._baseline:
                self._baseline[module_id] = {
                    name: self._integer(stats.get(name)) for name in self._COUNTERS
                }

            row = self._modules.setdefault(
                str(module_id),
                {
                    "execution_mode": stats.get("execution_mode"),
                    "input_queue_depth_max": None,
                    "output_queue_depth_max": None,
                    "in_flight_max": None,
                    "degraded_seen": False,
                },
            )
            row["execution_mode"] = stats.get(
                "execution_mode", row.get("execution_mode")
            )
            row["degraded_seen"] |= bool(stats.get("degraded"))
            for name, output_name in (
                ("input_queue_size", "input_queue_depth_max"),
                ("output_queue_size", "output_queue_depth_max"),
                ("in_flight", "in_flight_max"),
            ):
                depth = stats.get(name)
                if depth is None:
                    continue
                depth_value = self._integer(depth)
                previous = row.get(output_name)
                row[output_name] = (
                    depth_value if previous is None else max(previous, depth_value)
                )
            self._latest[str(module_id)] = stats

    def finish(self, final_snapshot: dict[str, Any]) -> dict[str, Any]:
        self.observe(final_snapshot)
        result = {}
        for module_id, row in self._modules.items():
            latest = self._latest.get(module_id, {})
            baseline = self._baseline.get(module_id, {})
            result[module_id] = {
                **row,
                "input_queue_dropped": max(
                    0,
                    self._integer(latest.get("input_queue_dropped"))
                    - baseline.get("input_queue_dropped", 0),
                ),
                "input_queue_rejected": max(
                    0,
                    self._integer(latest.get("input_queue_rejected"))
                    - baseline.get("input_queue_rejected", 0),
                ),
                "degraded_at_end": bool(latest.get("degraded")),
                "worker_running_at_end": bool(latest.get("worker_running")),
            }
        return {
            "samples": self._samples,
            "pipeline_degraded_seen": self._pipeline_degraded_seen,
            "pipeline_degraded_at_end": bool(final_snapshot.get("degraded")),
            "modules": result,
        }

def measure(
    config_path: Path,
    *,
    warmup_sec: float,
    active_sec: float,
    env_note: str = "",
    poll_interval_sec: float = 0.001,
) -> dict[str, Any]:
    from evileye.core.logging_config import setup_evileye_logging
    from evileye.core.mp_context import ensure_spawn_start_method
    from evileye.pipelines.pipeline_surveillance import PipelineSurveillance

    if poll_interval_sec < 0:
        raise ValueError("poll_interval_sec must be non-negative")

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
        runtime_sampler = RuntimeStatsSampler(pipeline.get_runtime_stats())
        runtime_sample_interval_sec = 0.25
        next_runtime_sample = time.monotonic() + runtime_sample_interval_sec

        pending: dict[tuple[int, int], float] = {}
        latencies_ms: list[float] = []
        tracker_keys: set[tuple[int, int]] = set()
        source_keys: set[tuple[int, int]] = set()
        last_source_fid: dict[int, int] = {}
        staleness_samples: list[int] = []
        staleness_matched: list[int] = []
        matched_tracker_keys: set[tuple[int, int]] = set()

        time.sleep(warmup_sec)
        t_start = time.monotonic()
        ticks = 0
        runtime_snapshot_at_measurement_end = None
        try:
            while time.monotonic() - t_start < active_sec:
                t_tick = time.monotonic()
                res = pipeline.process()
                ticks += 1
                now = time.monotonic()
                if now >= next_runtime_sample:
                    runtime_sampler.observe(pipeline.get_runtime_stats())
                    next_runtime_sample = now + runtime_sample_interval_sec
                for item in res.get("sources") or []:
                    key = _frame_key(item)
                    if key:
                        sid, fid = key
                        last_source_fid[sid] = max(last_source_fid.get(sid, 0), fid)
                        if key not in pending:
                            source_keys.add(key)
                        pending[key] = t_tick
                for item in res.get("trackers") or []:
                    key = _frame_key(item)
                    if key:
                        sid, fid = key
                        latest = last_source_fid.get(sid, fid)
                        staleness = latest - fid
                        if staleness >= 0:
                            staleness_samples.append(staleness)
                    if key and key in pending:
                        latencies_ms.append((time.monotonic() - pending.pop(key)) * 1000.0)
                        tracker_keys.add(key)
                        matched_tracker_keys.add(key)
                        sid, fid = key
                        latest = last_source_fid.get(sid, fid)
                        s = latest - fid
                        if s >= 0:
                            staleness_matched.append(s)
                if poll_interval_sec:
                    time.sleep(poll_interval_sec)
        finally:
            try:
                runtime_snapshot_at_measurement_end = pipeline.get_runtime_stats()
            except Exception:
                runtime_snapshot_at_measurement_end = None
            try:
                pipeline.stop()
            except Exception:
                pass

        if runtime_snapshot_at_measurement_end is None:
            runtime_snapshot_at_measurement_end = pipeline.get_runtime_stats()
        module_runtime = runtime_sampler.finish(runtime_snapshot_at_measurement_end)
        active_elapsed = max(0.001, time.monotonic() - t_start)
        sorted_lat = sorted(latencies_ms)
        p50 = sorted_lat[len(sorted_lat) // 2] if sorted_lat else None
        p95_idx = int(round(0.95 * (len(sorted_lat) - 1))) if sorted_lat else 0
        p95 = sorted_lat[p95_idx] if sorted_lat else None
        unmatched = len(pending)
        mean_staleness = (
            round(sum(staleness_samples) / len(staleness_samples), 4)
            if staleness_samples
            else None
        )
        mean_staleness_matched = (
            round(sum(staleness_matched) / len(staleness_matched), 4)
            if staleness_matched
            else None
        )
        in_band = staleness_in_band(mean_staleness)
        return {
            "config": str(config_path.relative_to(REPO_ROOT)),
            "warmup_sec": warmup_sec,
            "active_sec": active_sec,
            "poll_interval_sec": poll_interval_sec,
            "ticks": ticks,
            "source_frames": len(source_keys),
            "tracker_matches": len(tracker_keys),
            "e2e_tracker_fps": round(len(tracker_keys) / active_elapsed, 4),
            "e2e_p50_ms": round(p50, 2) if p50 is not None else None,
            "e2e_p95_ms": round(p95, 2) if p95 is not None else None,
            "mean_staleness_frames": mean_staleness,
            "mean_staleness_matched_only": mean_staleness_matched,
            "staleness_in_band": in_band,
            "staleness_ref": STALENESS_REF,
            "staleness_min": STALENESS_MIN,
            "staleness_max": STALENESS_MAX,
            "e2e_tracker_fps_matched": round(
                len(matched_tracker_keys) / active_elapsed, 4
            ),
            "p95_staleness_frames": _percentile_int(staleness_samples, 95.0),
            "max_staleness_frames": max(staleness_samples) if staleness_samples else None,
            "staleness_samples": len(staleness_samples),
            "pending_unmatched": unmatched,
            "pending_unmatched_pct": round(
                100.0 * unmatched / max(1, len(source_keys)), 2
            ),
            "module_runtime": module_runtime,
            "env_note": env_note,
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
        "--poll-interval-sec",
        type=float,
        default=0.001,
        help="Yield briefly between pipeline polls to avoid saturating the host CPU",
    )
    parser.add_argument(
        "--out",
        default="reports/poly_videos_mode_compare/e2e_measure.json",
    )
    parser.add_argument("--env-note", default="", help="Experiment label stored in JSON")
    args = parser.parse_args()

    config_path = (REPO_ROOT / args.config).resolve()
    result = measure(
        config_path,
        warmup_sec=args.warmup_sec,
        active_sec=args.active_sec,
        env_note=args.env_note,
        poll_interval_sec=args.poll_interval_sec,
    )
    out_path = (REPO_ROOT / args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
