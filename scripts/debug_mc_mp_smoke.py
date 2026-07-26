#!/usr/bin/env python3
"""Headless pipeline smoke: log mc_trackers emit rate under MP (no GUI)."""
import concurrent.futures
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("EVILEYE_PERF_DIAG", "1")
os.environ.setdefault("EVILEYE_PERF_DIAG_EVERY", "20")

from evileye.core.logging_config import setup_evileye_logging
from evileye.core.mp_context import ensure_spawn_start_method
from evileye.pipelines.pipeline_surveillance import PipelineSurveillance


def main() -> int:
    ensure_spawn_start_method()
    setup_evileye_logging(log_level="INFO")
    cfg_path = ROOT / "configs" / "poly-videos-gst.json"
    with open(cfg_path, encoding="utf-8") as f:
        cfg = json.load(f)
    pipeline = PipelineSurveillance()
    pipeline.set_params(**cfg.get("pipeline", cfg))
    pipeline.init()
    pipeline.start()
    mc_empty = 0
    mc_nonempty = 0
    tracker_nonempty = 0
    loops = 25
    process_timeout_sec = 10.0
    print("init done, warming up 15s...", flush=True)
    time.sleep(15)
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            for i in range(loops):
                fut = pool.submit(pipeline.process)
                try:
                    results = fut.result(timeout=process_timeout_sec)
                except concurrent.futures.TimeoutError:
                    print(f"loop {i}: pipeline.process timeout", flush=True)
                    continue
                mc = results.get("mc_trackers") or []
                tr = results.get("trackers") or []
                if mc:
                    mc_nonempty += 1
                    if mc_nonempty == 1:
                        print(f"loop {i}: first mc emit len={len(mc)}", flush=True)
                else:
                    mc_empty += 1
                if tr:
                    tracker_nonempty += 1
                time.sleep(0.12)
    finally:
        pipeline.stop()
    print(
        f"loops={loops} mc_nonempty={mc_nonempty} mc_empty={mc_empty} "
        f"tracker_nonempty={tracker_nonempty}",
        flush=True,
    )
    return 0 if mc_nonempty > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
