#!/usr/bin/env python3
"""Headless compare: per-source frame counts and MC/tracker yield (poly-videos-gst MP)."""
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("EVILEYE_PIPELINE_TIMELINE", "0")

from evileye.core.logging_config import setup_evileye_logging
from evileye.core.mp_context import ensure_spawn_start_method
from evileye.core.frame import Frame
from evileye.pipelines.pipeline_surveillance import PipelineSurveillance

# Baseline from run before capture drain + mp_wait removal (40 ticks sources).
BASELINE_SOURCES = {0: 40, 1: 34, 2: 6, 3: 32, 4: 8}
BASELINE_SMOKE = {"loops": 25, "mc_nonempty": 3, "mc_empty": 22, "tracker_nonempty": 25}


def _sid_from_item(item) -> int | None:
    if isinstance(item, Frame):
        return getattr(item, "source_id", None)
    if isinstance(item, (list, tuple)) and len(item) >= 2:
        frame = item[1]
        sid = getattr(frame, "source_id", None)
        if sid is None and item[0] is not None:
            sid = getattr(item[0], "source_id", None)
        return sid
    return getattr(item, "source_id", None)


def _count_stage(results: dict, stage: str) -> Counter:
    c: Counter = Counter()
    for item in results.get(stage) or []:
        sid = _sid_from_item(item)
        if sid is not None:
            try:
                c[int(sid)] += 1
            except (TypeError, ValueError):
                pass
    return c


def main() -> int:
    ensure_spawn_start_method()
    setup_evileye_logging(log_level="WARNING")
    cfg = json.load(open(ROOT / "configs/poly-videos-gst.json", encoding="utf-8"))
    pipeline = PipelineSurveillance()
    pipeline.set_params(**cfg["pipeline"])
    pipeline.init()
    pipeline.start()

    roi_sizes: dict[int, int] = {}
    for det in pipeline.detectors:
        sid = int(det.source_ids[0]) if det.source_ids else -1
        roi_sizes[sid] = len(det.roi[0]) if det.roi and det.roi[0] else 1

    ticks = 50
    tick_sleep = 0.12
    print(f"warmup 20s, then {ticks} ticks @ {tick_sleep}s (controller-like)...", flush=True)
    time.sleep(20)

    src_c: Counter = Counter()
    det_c: Counter = Counter()
    tr_c: Counter = Counter()
    mc_ticks_nonempty = 0
    mc_objects_total = 0
    tr_ticks_nonempty = 0
    both_12 = only_1 = only_2 = neither_12 = 0

    try:
        for _ in range(ticks):
            res = pipeline.process()
            stage_src = _count_stage(res, "sources")
            for k, cnt in (
                ("sources", src_c),
                ("detectors", det_c),
                ("trackers", tr_c),
            ):
                for sid, n in _count_stage(res, k).items():
                    cnt[sid] += n
            sids = set(stage_src.keys())
            if 1 in sids and 2 in sids:
                both_12 += 1
            elif 1 in sids:
                only_1 += 1
            elif 2 in sids:
                only_2 += 1
            else:
                neither_12 += 1

            mc = res.get("mc_trackers") or []
            if mc:
                mc_ticks_nonempty += 1
                mc_objects_total += len(mc)
            if res.get("trackers"):
                tr_ticks_nonempty += 1
            time.sleep(tick_sleep)
    finally:
        try:
            pipeline.stop()
        except Exception:
            pass

    all_sids = sorted(set(roi_sizes) | set(src_c) | set(det_c) | set(tr_c))

    print(f"\n=== Per-source counts over {ticks} pipeline ticks ===")
    print(f"{'sid':>4} {'roi':>4} {'src':>5} {'det':>5} {'trk':>5} {'src%':>6}  baseline_src")
    for sid in all_sids:
        b = BASELINE_SOURCES.get(sid, 0)
        sc = src_c[sid]
        print(
            f"{sid:4d} {roi_sizes.get(sid, 0):4d} {sc:5d} {det_c[sid]:5d} {tr_c[sid]:5d} "
            f"{sc / ticks * 100:5.0f}%  {b:5d} ({b / ticks * 100:.0f}%)"
        )

    print(
        f"\n=== MC / trackers (ticks={ticks}) ===\n"
        f"  mc_ticks_nonempty={mc_ticks_nonempty} ({mc_ticks_nonempty / ticks * 100:.0f}%)\n"
        f"  mc_objects_total={mc_objects_total}\n"
        f"  tracker_ticks_nonempty={tr_ticks_nonempty} ({tr_ticks_nonempty / ticks * 100:.0f}%)\n"
        f"  baseline smoke: mc_nonempty~{BASELINE_SMOKE['mc_nonempty']}/{BASELINE_SMOKE['loops']} "
        f"tracker_nonempty={BASELINE_SMOKE['tracker_nonempty']}"
    )

    print(
        f"\n=== Split capture-1_2 same-tick presence ({ticks} ticks) ===\n"
        f"  both sid 1+2: {both_12}\n"
        f"  only sid 1:   {only_1}\n"
        f"  only sid 2:   {only_2}\n"
        f"  neither:      {neither_12}"
    )

    ok_capture = src_c.get(2, 0) > BASELINE_SOURCES.get(2, 0) * 2
    ok_mc = mc_ticks_nonempty >= max(5, BASELINE_SMOKE["mc_nonempty"])
    print(
        f"\n=== Verdict ===\n"
        f"  cam2 sources improved vs baseline: {ok_capture} ({src_c.get(2, 0)} vs {BASELINE_SOURCES.get(2, 6)})\n"
        f"  mc emits improved vs baseline:     {ok_mc} ({mc_ticks_nonempty} vs ~{BASELINE_SMOKE['mc_nonempty']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
