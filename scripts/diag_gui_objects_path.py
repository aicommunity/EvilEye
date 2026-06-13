#!/usr/bin/env python3
"""Trace data path: pipeline stages -> sticky mc -> GUI-like object counts."""
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("EVILEYE_PIPELINE_TIMELINE", "1")
os.environ["EVILEYE_PIPELINE_TIMELINE"] = "1"

from evileye.core.logging_config import setup_evileye_logging
from evileye.core.mp_context import ensure_spawn_start_method
from evileye.core.frame import Frame
from evileye.pipelines.pipeline_surveillance import PipelineSurveillance
from evileye.controller.controller_processing_mixin import ControllerProcessingMixin


class _CtrlStub(ControllerProcessingMixin):
    def __init__(self):
        self.params = {}
        self.skip_objects_handler = False


def _tracks_len(item) -> int:
    if not isinstance(item, (list, tuple)) or len(item) < 2:
        return 0
    data = item[0]
    if hasattr(data, "tracks"):
        return len(data.tracks or [])
    return 0


def main() -> int:
    ensure_spawn_start_method()
    setup_evileye_logging(log_level="INFO")
    cfg = json.load(open(ROOT / "configs/poly-videos-gst.json", encoding="utf-8"))
    pipeline = PipelineSurveillance()
    pipeline.set_params(**cfg["pipeline"])
    pipeline.init()
    pipeline.start()
    ctrl = _CtrlStub()

    mc = None
    for proc in pipeline.processors:
        if getattr(proc, "processor_name", None) == "mc_trackers" and proc.processors:
            mc = proc.processors[0]
            break

    print("warmup 25s...", flush=True)
    time.sleep(25)

    ticks = 60
    tick_sleep = 0.12
    stage_trk = Counter()
    mc_emitted_ticks = 0
    mc_batch_in_hist = Counter()

    try:
        for t in range(ticks):
            res = pipeline.process()
            for item in res.get("trackers") or []:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    sid = getattr(item[1], "source_id", None)
                    if sid is not None:
                        stage_trk[int(sid)] += 1
            mc_out = res.get("mc_trackers") or []
            if mc_out:
                mc_emitted_ticks += 1
                mc_batch_in_hist[len(mc_out)] += 1

            if mc is not None and t % 15 == 0:
                acc = len(mc._accumulated_tick_batch)
                print(
                    f"  tick {t}: acc={acc}/{len(mc.source_ids)} "
                    f"skip={mc._diag_tick_batch_skip} stale={mc._diag_tick_batch_stale_evict} "
                    f"trk_out={len(res.get('trackers') or [])} mc_out={len(mc_out)}",
                    flush=True,
                )
            time.sleep(tick_sleep)

        sticky = pipeline.get_latest_objects_results()
        vis = pipeline.get_latest_visualization_frames()
        latest_peek = pipeline.peek_latest_result() or {}

        print("\n=== Last tick pipeline sections ===")
        for stage in ("sources", "detectors", "trackers", "mc_trackers"):
            items = latest_peek.get(stage) or []
            print(f"  {stage}: len={len(items)}")

        print("\n=== Sticky objects (get_latest_objects_results) ===")
        print(f"  items={len(sticky)} total_tracks={sum(_tracks_len(x) for x in sticky)}")
        by_sid = Counter()
        for item in sticky:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                by_sid[getattr(item[1], "source_id", None)] += 1
                print(
                    f"    sid={item[1].source_id} fid={item[1].frame_id} "
                    f"tracks={_tracks_len(item)} has_payload={ctrl._has_non_empty_payload(item[0])}"
                )

        converted = ctrl._convert_results_for_visualization(sticky)
        print("\n=== After _convert_results_for_visualization ===")
        for sid, ol in sorted(converted.items(), key=lambda x: x[0] if x[0] is not None else -1):
            print(f"  sid={sid}: objects={len(ol.objects)}")

        print("\n=== Vis frames chain ===")
        print(f"  vis_frames={len(vis)}")
        if vis and isinstance(vis[0], (list, tuple)):
            print(f"  first vis sid={getattr(vis[0][1], 'source_id', None)} fid={getattr(vis[0][1], 'frame_id', None)}")

        print(f"\n=== Over {ticks} ticks: mc_emitted_ticks={mc_emitted_ticks} ({100*mc_emitted_ticks/ticks:.0f}%)")
        print(f"  trackers per sid: {dict(stage_trk)}")
        if mc:
            print(
                f"  MC final: skip={mc._diag_tick_batch_skip} stale_evict={mc._diag_tick_batch_stale_evict} "
                f"acc={len(mc._accumulated_tick_batch)}/{len(mc.source_ids)}"
            )
            acc_fids = {
                sid: mc._frame_id_for_pair(ti, fr)
                for sid, (ti, fr) in mc._accumulated_tick_batch.items()
            }
            print(f"  acc_fids={acc_fids}")
    finally:
        try:
            pipeline.stop()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
