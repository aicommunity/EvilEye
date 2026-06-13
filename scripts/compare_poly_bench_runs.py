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
    e2e_p = {}
    e2e_t = {}
    if e2e_proc.is_file() and e2e_thr.is_file():
        e2e_p = json.loads(e2e_proc.read_text(encoding="utf-8"))
        e2e_t = json.loads(e2e_thr.read_text(encoding="utf-8"))
        pf = e2e_p.get("e2e_tracker_fps")
        tf = e2e_t.get("e2e_tracker_fps")
        if pf and tf:
            e2e_ratio = pf / tf

    out_path = (REPO_ROOT / args.out).resolve()
    barrier_csv = (REPO_ROOT / args.current_dir / "barrier_metrics.csv").resolve()
    barrier_rows = _load_csv(barrier_csv)
    mp_pending_max = _mean(barrier_rows, "mp_pending_max", mode="process", capture="opencv")
    lag_ratio = _mean(barrier_rows, "lag_ratio", mode="process", capture="opencv")

    metrics = [
        ("pipeline_hz_est", "opencv", "process"),
        ("pipeline_hz_est", "opencv", "thread"),
        ("p95_pipeline_ms", "opencv", "process"),
    ]
    is_phase3 = "phase3" in out_path.name
    is_phase2 = "phase2" in out_path.name
    if is_phase3:
        title = "# MP FPS phase 3 summary"
    elif is_phase2:
        title = "# MP FPS phase 2 summary"
    else:
        title = "# MP FPS post-fix comparison"
    lines = [
        title,
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
    if is_phase3:
        ms = e2e_p.get("mean_staleness_frames")
        in_band = e2e_p.get("staleness_in_band")
        e2e_p_fps = e2e_p.get("e2e_tracker_fps")
        lines.extend(
            [
                "",
                "## E2E KPI (phase 3 — primary)",
                "",
                "| ID | Metric | Current | Target |",
                "| --- | --- | ---: | ---: |",
                f"| K1 | e2e_tracker_fps (process) | {e2e_p_fps or '-'} | ≥ 31 |",
                f"| K2 | e2e_ratio process/thread | {e2e_ratio or 'n/a'} | ≥ 3.0 |",
                f"| K3 | mean_staleness_frames | {ms or '-'} | [5.9, 6.5] |",
                f"| K4 | staleness_in_band | {in_band} | true |",
                f"| K5 | mp_pending_max | {mp_pending_max or '-'} | ≤ 45 |",
                f"| K6 | drop_events (barrier) | {sum(int(r.get('drop_events') or 0) for r in barrier_rows)} | 0 |",
                "",
                f"**E2E env:** {e2e_p.get('env_note', '')}",
                "",
                "См. матрицу F*: `experiments/e2e_fps_matrix/matrix_results.md`.",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "## Backlog / freshness (phase 2)",
                "",
                "| Metric | Baseline | Current | Target |",
                "| --- | ---: | ---: | ---: |",
                f"| mp_pending_max (process) | — | {mp_pending_max or '-'} | ≤ 25 |",
                f"| lag_ratio mean (process) | {_mean(_load_csv(baseline_csv), 'lag_ratio', mode='process') or '-'} | {lag_ratio or '-'} | < 1.5 |",
                f"| mean_staleness_frames (process) | — | {e2e_p.get('mean_staleness_frames', '-')} | ≤ 2 |",
                f"| E2E process/thread ratio | — | {e2e_ratio or 'n/a'} | ≥ 0.70 |",
                "",
                f"**E2E env:** {e2e_p.get('env_note', '')}",
            ]
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
