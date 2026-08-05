#!/usr/bin/env python3
"""Regression bench for web UI hot-path service functions.

Usage (from repo root, with EVILEYE_DATA_DIR / cwd as in deploy if needed):

  python scripts/bench_web_ui_hotpaths.py

Prints wall times for cameras/current summary, journal meta/stats/grouped, playback segments.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _ms(fn, *args, **kwargs) -> tuple[float, object]:
    t0 = time.perf_counter()
    result = fn(*args, **kwargs)
    return (time.perf_counter() - t0) * 1000.0, result


def main() -> int:
    deploy = Path(os.environ.get("EVILEYE_DEPLOY_DIR", "/home/user/EvilEyeDeploy"))
    if deploy.is_dir():
        os.chdir(deploy)
    if "EVILEYE_DATA_DIR" not in os.environ:
        data = Path("/media/user/Data8/EvilEyeData")
        if data.is_dir():
            os.environ["EVILEYE_DATA_DIR"] = str(data)

    from evileye.api.core import server_state as ss
    from evileye.api.core import journal_service as js
    from evileye.api.core import playback_service as ps
    from evileye.api.core import runtime_registry as rr

    rows: list[dict] = []

    stubs = rr.list_runtime_record_stubs(discover=False)
    rows.append({"op": "registry_stubs_count", "ms": 0.0, "extra": {"n": len(stubs)}})

    ms, current = _ms(ss.get_current_run_summary)
    rows.append({"op": "get_current_run_summary", "ms": round(ms, 2), "extra": {"rid": (current or {}).get("id")}})

    ms, cams = _ms(ss.list_camera_summaries, scope="current")
    rows.append({"op": "list_camera_summaries(current)", "ms": round(ms, 2), "extra": {"n": len(cams)}})

    ms, _ = _ms(ss.list_run_summaries)
    rows.append({"op": "list_run_summaries", "ms": round(ms, 2)})

    ms, meta = _ms(js.load_filters_meta)
    dates = meta.get("dates") if isinstance(meta, dict) else None
    rows.append(
        {
            "op": "load_filters_meta",
            "ms": round(ms, 2),
            "extra": {"dates": len(dates) if isinstance(dates, list) else None},
        }
    )

    ms, _ = _ms(js.load_journal_stats)
    rows.append({"op": "load_journal_stats", "ms": round(ms, 2)})

    from datetime import date, timedelta

    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    ms, page = _ms(
        js.load_events_grouped_page,
        page=0,
        size=30,
        filters={},
        date_from=yesterday,
        date_to=today,
    )
    items = page.get("items") if isinstance(page, dict) else None
    rows.append(
        {
            "op": "load_events_grouped_page",
            "ms": round(ms, 2),
            "extra": {"items": len(items) if isinstance(items, list) else None},
        }
    )

    # Warm second call for TTL
    ms, _ = _ms(js.load_filters_meta)
    rows.append({"op": "load_filters_meta(warm)", "ms": round(ms, 2)})
    ms, _ = _ms(js.load_journal_stats)
    rows.append({"op": "load_journal_stats(warm)", "ms": round(ms, 2)})

    cam_names: list[str] = []
    try:
        ms_cams, pb_cams = _ms(ps.discover_cameras, today)
        cam_names = [str(c.get("id") or c.get("name") or "") for c in (pb_cams or []) if isinstance(c, dict)][:3]
        cam_names = [c for c in cam_names if c]
        rows.append({"op": "discover_cameras", "ms": round(ms_cams, 2), "extra": {"n": len(pb_cams or [])}})
    except Exception as exc:
        rows.append({"op": "discover_cameras", "ms": -1, "extra": {"error": str(exc)}})

    if cam_names:
        ms, batch = _ms(ps.load_segments_batch, cam_names, None, None, today)
        n = sum(len(v) for v in (batch or {}).values()) if isinstance(batch, dict) else 0
        rows.append({"op": "load_segments_batch", "ms": round(ms, 2), "extra": {"cams": cam_names, "segments": n}})

    print(json.dumps({"cwd": os.getcwd(), "results": rows}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
