#!/usr/bin/env python3
"""Measure how often each source_id appears at sources stage (1 tick = 1 frame per capture proc)."""
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("EVILEYE_PIPELINE_TIMELINE", "1")

from evileye.core.logging_config import setup_evileye_logging
from evileye.core.mp_context import ensure_spawn_start_method
from evileye.core.frame import Frame
from evileye.pipelines.pipeline_surveillance import PipelineSurveillance


def main() -> int:
    ensure_spawn_start_method()
    setup_evileye_logging(log_level="WARNING")
    cfg = json.load(open(ROOT / "configs/poly-videos-gst.json", encoding="utf-8"))
    pipeline = PipelineSurveillance()
    pipeline.set_params(**cfg["pipeline"])
    pipeline.init()
    pipeline.start()
    print("warmup 15s...", flush=True)
    time.sleep(15)
    counts: Counter = Counter()
    roi_sizes: dict[int, list] = {}
    for det in pipeline.detectors:
        sid = det.source_ids[0] if det.source_ids else -1
        n_roi = len(det.roi[0]) if det.roi and det.roi[0] else 1
        roi_sizes[sid] = n_roi

    ticks = 40
    try:
        for _ in range(ticks):
            res = pipeline.process()
            for fr in res.get("sources") or []:
                if isinstance(fr, Frame):
                    counts[fr.source_id] += 1
                elif isinstance(fr, (list, tuple)) and len(fr) >= 2:
                    counts[getattr(fr[1], "source_id", None)] += 1
            time.sleep(0.05)
    finally:
        try:
            pipeline.stop()
        except Exception:
            pass

    print(f"\n=== Frames at sources stage over {ticks} pipeline ticks ===")
    for sid in sorted(roi_sizes):
        print(
            f"  source_id={sid}: count={counts[sid]:4d}  "
            f"detector_roi_regions={roi_sizes[sid]}  "
            f"(~{counts[sid]/ticks*100:.0f}% ticks)"
        )
    print("\nNote: split capture-1_2 should yield both source_id 1 and 2 per tick when queued.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
