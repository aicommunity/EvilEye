#!/usr/bin/env python3
"""Headless output snapshot for poly-videos configs (pipeline + controller path)."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("EVILEYE_PIPELINE_TIMELINE", "0")

from poly_mode_compare_lib import COMPARE_CONFIGS, DEFAULT_OUT_DIR, REPO_ROOT, write_bench_config


def _tracks_len(item) -> int:
    if not isinstance(item, (list, tuple)) or len(item) < 2:
        return 0
    data = item[0]
    tracks = getattr(data, "tracks", None)
    return len(tracks or [])


def _count_stage(results: dict, stage: str) -> Counter:
    c: Counter = Counter()
    for item in results.get(stage) or []:
        sid = None
        frame = item
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            frame = item[1]
            data = item[0]
            sid = getattr(data, "source_id", None) or getattr(frame, "source_id", None)
        else:
            sid = getattr(item, "source_id", None)
        if sid is not None:
            try:
                c[int(sid)] += 1
            except (TypeError, ValueError):
                pass
    return c


def collect_for_config(
    config_path: Path,
    *,
    ticks: int,
    warmup_sec: float,
    tick_sleep: float,
    config_label: str | None = None,
) -> dict[str, Any]:
    from evileye.core.logging_config import setup_evileye_logging
    from evileye.core.mp_context import ensure_spawn_start_method
    from evileye.controller.controller_processing_mixin import ControllerProcessingMixin
    from evileye.pipelines.pipeline_surveillance import PipelineSurveillance

    ensure_spawn_start_method()
    setup_evileye_logging(log_level="WARNING")

    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    pipeline = PipelineSurveillance()
    pipeline.set_params(**cfg["pipeline"])
    pipeline.init()
    pipeline.start()

    class _CtrlStub(ControllerProcessingMixin):
        def __init__(self) -> None:
            self.params = cfg
            self.skip_objects_handler = True
            self.source_id_name_table = {}
            self.source_video_duration = {}

        def _get_preview_event_entries(self, _sid):
            return []

        def _get_preview_event_cfg(self):
            return {}

        def _get_preview_visualizer_cfg(self):
            return {}

    ctrl = _CtrlStub()
    mc = None
    for proc in pipeline.processors:
        if getattr(proc, "processor_name", None) == "mc_trackers" and proc.processors:
            mc = proc.processors[0]
            break

    src_c: Counter = Counter()
    det_c: Counter = Counter()
    trk_c: Counter = Counter()
    mc_ticks_nonempty = 0
    mc_batch_sizes: Counter = Counter()
    sticky_tracks_samples: list[int] = []
    vis_counts: list[int] = []

    time.sleep(warmup_sec)
    try:
        for _ in range(ticks):
            res = pipeline.process()
            for k, cnt in (("sources", src_c), ("detectors", det_c), ("trackers", trk_c)):
                for sid, n in _count_stage(res, k).items():
                    cnt[sid] += n
            mc_out = res.get("mc_trackers") or []
            if mc_out:
                mc_ticks_nonempty += 1
                mc_batch_sizes[len(mc_out)] += 1

            sticky = pipeline.get_latest_objects_results()
            vis = pipeline.get_latest_visualization_frames()
            sticky_tracks_samples.append(sum(_tracks_len(x) for x in sticky))
            vis_counts.append(len(vis))
            time.sleep(tick_sleep)

        last_sticky = pipeline.get_latest_objects_results()
        last_vis = pipeline.get_latest_visualization_frames()
        converted = ctrl._convert_results_for_visualization(last_sticky)
        active_per_source = {str(sid): len(ol.objects) for sid, ol in converted.items()}

        payload_ok = 0
        for item in last_sticky:
            if isinstance(item, (list, tuple)) and len(item) >= 2 and ctrl._has_non_empty_payload(item[0]):
                payload_ok += 1

        result: dict[str, Any] = {
            "config": config_label or str(config_path),
            "ticks": ticks,
            "warmup_sec": warmup_sec,
            "tick_sleep": tick_sleep,
            "sources_per_source": dict(src_c),
            "detectors_per_source": dict(det_c),
            "trackers_per_source": dict(trk_c),
            "mc_ticks_nonempty": mc_ticks_nonempty,
            "mc_emit_rate": round(mc_ticks_nonempty / max(1, ticks), 4),
            "mc_batch_sizes": dict(mc_batch_sizes),
            "sticky_tracks_last": sticky_tracks_samples[-1] if sticky_tracks_samples else 0,
            "sticky_tracks_mean": round(
                sum(sticky_tracks_samples) / max(1, len(sticky_tracks_samples)), 2
            ),
            "vis_frames_last": vis_counts[-1] if vis_counts else 0,
            "objects_results_items": len(last_sticky),
            "objects_with_payload": payload_ok,
            "active_objects_per_source": active_per_source,
            "tracks_total": sticky_tracks_samples[-1] if sticky_tracks_samples else 0,
            "tracker_frames_total": sum(trk_c.values()),
            "has_data": (
                (sum(trk_c.values()) > 0 or (sticky_tracks_samples[-1] if sticky_tracks_samples else 0) > 0)
                and (mc_ticks_nonempty / max(1, ticks)) >= 0.05
            ),
        }
        if mc is not None:
            result["mc_diag"] = {
                "tick_batch_skip": getattr(mc, "_diag_tick_batch_skip", 0),
                "tick_batch_stale_evict": getattr(mc, "_diag_tick_batch_stale_evict", 0),
                "accumulator_size": len(getattr(mc, "_accumulated_tick_batch", {}) or {}),
                "source_ids": list(getattr(mc, "source_ids", []) or []),
            }
        return result
    finally:
        try:
            pipeline.stop()
        except Exception:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect poly-videos output snapshots.")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR.relative_to(REPO_ROOT)))
    parser.add_argument("--ticks", type=int, default=60)
    parser.add_argument("--warmup-sec", type=float, default=25.0)
    parser.add_argument("--tick-sleep", type=float, default=0.12)
    parser.add_argument("--configs", nargs="*", help="slug filter")
    args = parser.parse_args()

    out_dir = (REPO_ROOT / args.out_dir).resolve()
    artifacts = out_dir / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)

    specs = COMPARE_CONFIGS
    if args.configs:
        wanted = set(args.configs)
        specs = [s for s in specs if s["slug"] in wanted or s["config"] in wanted]

    for spec in specs:
        print(f"Snapshot: {spec['slug']}")
        base = REPO_ROOT / spec["config"]
        overlay = write_bench_config(base)
        warmup = args.warmup_sec
        ticks = args.ticks
        if spec.get("capture") == "gst":
            warmup = max(warmup, 45.0)
            ticks = max(ticks, 120)
        try:
            data = collect_for_config(
                overlay,
                ticks=ticks,
                warmup_sec=warmup,
                tick_sleep=args.tick_sleep,
                config_label=spec["config"],
            )
        finally:
            try:
                overlay.unlink(missing_ok=True)
            except OSError:
                pass
        data["slug"] = spec["slug"]
        data["capture"] = spec["capture"]
        data["mode"] = spec["mode"]
        out_path = artifacts / f"{spec['slug']}_output.json"
        out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"  -> {out_path.relative_to(REPO_ROOT)} has_data={data['has_data']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
