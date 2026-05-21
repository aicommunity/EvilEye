#!/usr/bin/env python3
"""Run N pipeline ticks with EVILEYE_PIPELINE_TIMELINE and print summary."""
import concurrent.futures
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["EVILEYE_PIPELINE_TIMELINE"] = "1"
os.environ.setdefault("EVILEYE_PERF_DIAG", "1")
os.environ["EVILEYE_PERF_DIAG_EVERY"] = "1"

from evileye.core.logging_config import setup_evileye_logging
from evileye.core.mp_context import ensure_spawn_start_method
from evileye.pipelines.pipeline_surveillance import PipelineSurveillance

TL_RE = re.compile(
    r"PipelineTimeline\((?P<stage>[^)]+)\):.*?"
    r"(?:in=(?P<in>\d+) put=(?P<put>\d+) out=(?P<out>\d+) )?"
    r"put_ms=(?P<put_ms>[\d.]+) drain_imm_ms=(?P<drain_ms>[\d.]+)\(out_imm=(?P<out_imm>\d+)\) "
    r"total_ms=(?P<total>[\d.]+)"
)

MC_RE = re.compile(
    r"PipelineTimeline\(mc_trackers\): batch_in=(?P<bin>\d+) emitted=(?P<em>\d+) acc=(?P<acc>[^ ]+) "
)


def main() -> int:
    ensure_spawn_start_method()
    setup_evileye_logging(log_level="INFO")
    cfg = json.load(open(ROOT / "configs/poly-videos-gst.json", encoding="utf-8"))
    pipeline = PipelineSurveillance()
    pipeline.set_params(**cfg["pipeline"])
    pipeline.init()
    pipeline.start()
    print("warmup 18s...", flush=True)
    time.sleep(18)
    loops = 12
    rows = []
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            for i in range(loops):
                t0 = time.monotonic()
                fut = pool.submit(pipeline.process)
                try:
                    res = fut.result(timeout=15.0)
                except concurrent.futures.TimeoutError:
                    print(f"tick {i}: TIMEOUT", flush=True)
                    continue
                mc = res.get("mc_trackers") or []
                rows.append(
                    {
                        "tick": i,
                        "wall_ms": (time.monotonic() - t0) * 1000,
                        "mc_len": len(mc),
                    }
                )
                time.sleep(0.05)
    finally:
        try:
            pipeline.stop()
        except Exception:
            pass

    print("\n=== Tick summary ===")
    for r in rows:
        print(f"  tick {r['tick']}: wall={r['wall_ms']:.0f}ms mc_out={r['mc_len']}")

    log_hint = "grep PipelineTimeline /tmp/timeline_run.log"
    print(f"\nParse full timeline from log: {log_hint}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
