#!/usr/bin/env python3
"""Compare baseline vs post-fix poly-videos benchmark CSV/E2E JSON."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from poly_mode_compare_lib import DEFAULT_OUT_DIR, REPO_ROOT


def _load_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8-sig", newline="") as inp:
        return list(csv.DictReader(inp, delimiter=";"))


def _mean(rows: list[dict], col: str, *, mode: str, capture: str = "opencv") -> float | None:
    vals = []
    for r in rows:
        if r.get("mode") != mode or r.get("capture") != capture:
            continue
        try:
            vals.append(float(str(r.get(col, "")).replace(",", ".")))
        except (TypeError, ValueError):
            pass
    if not vals:
        return None
    return sum(vals) / len(vals)


def _delta_pct(baseline: float | None, current: float | None) -> str:
    if baseline is None or current is None or baseline == 0:
        return "-"
    return f"{((current - baseline) / baseline) * 100:+.1f}%"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-dir", default="reports/poly_videos_mode_compare/baseline_pre_fix")
    parser.add_argument("--current-dir", default="reports/poly_videos_mode_compare")
    parser.add_argument("--out", default="docs/mp_fps_post_fix_summary.md")
    args = parser.parse_args()

    baseline_csv = (REPO_ROOT / args.baseline_dir / "results.csv").resolve()
    current_csv = (REPO_ROOT / args.current_dir / "results.csv").resolve()
    base_rows = _load_csv(baseline_csv)
    cur_rows = _load_csv(current_csv)

    e2e_proc = REPO_ROOT / args.current_dir / "e2e_opencv_process.json"
    e2e_thr = REPO_ROOT / args.current_dir / "e2e_opencv_thread.json"
    e2e_ratio = None
    if e2e_proc.is_file() and e2e_thr.is_file():
        p = json.loads(e2e_proc.read_text(encoding="utf-8"))
        t = json.loads(e2e_thr.read_text(encoding="utf-8"))
        pf = p.get("e2e_tracker_fps")
        tf = t.get("e2e_tracker_fps")
        if pf and tf:
            e2e_ratio = pf / tf

    metrics = [
        ("pipeline_hz_est", "opencv", "process"),
        ("pipeline_hz_est", "opencv", "thread"),
        ("p95_pipeline_ms", "opencv", "process"),
    ]
    lines = [
        "# MP FPS post-fix comparison",
        "",
        "| Metric | Baseline | Current | Δ% |",
        "| --- | ---: | ---: | ---: |",
    ]
    for col, cap, mode in metrics:
        b = _mean(base_rows, col, mode=mode, capture=cap)
        c = _mean(cur_rows, col, mode=mode, capture=cap)
        lines.append(
            f"| {col} ({cap}/{mode}) | {b or '-'} | {c or '-'} | {_delta_pct(b, c)} |"
        )
    lines.extend(["", f"**E2E process/thread ratio:** {e2e_ratio or 'n/a'} (target ≥ 0.70)", ""])
    out_path = (REPO_ROOT / args.out).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
