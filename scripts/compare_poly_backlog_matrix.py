#!/usr/bin/env python3
"""Aggregate backlog matrix experiment dirs into matrix_results.md."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from pathlib import Path
from typing import Any

from poly_mode_compare_lib import DEFAULT_OUT_DIR, REPO_ROOT

MATRIX_ROOT = DEFAULT_OUT_DIR / "experiments" / "backlog_matrix"
ENV_KEYS = (
    "EVILEYE_MP_QUEUE_SCALE",
    "EVILEYE_MP_DRAIN_POLL_SEC",
    "EVILEYE_CONTROLLER_BACKPRESSURE",
    "EVILEYE_PIPELINE_SYNC_MP",
    "EVILEYE_MP_PENDING_CAP",
    "EVILEYE_MP_PENDING_CAP_TRACKER",
)


def _load_barrier_rows(exp_dir: Path) -> list[dict[str, str]]:
    csv_path = exp_dir / "barrier_metrics.csv"
    if not csv_path.is_file():
        return []
    with csv_path.open(encoding="utf-8-sig", newline="") as inp:
        return list(csv.DictReader(inp, delimiter=";"))


def _mean_process(rows: list[dict], col: str, *, capture: str = "opencv") -> float | None:
    vals: list[float] = []
    for r in rows:
        if r.get("mode") != "process" or r.get("capture") != capture:
            continue
        raw = r.get(col)
        if raw in (None, ""):
            continue
        try:
            vals.append(float(str(raw).replace(",", ".")))
        except (TypeError, ValueError):
            pass
    return statistics.mean(vals) if vals else None


def _load_e2e(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _score_row(
    *,
    mean_staleness: float | None,
    pending_max: float | None,
    lag_ratio: float | None,
) -> float | None:
    if mean_staleness is None and pending_max is None and lag_ratio is None:
        return None
    ms = mean_staleness if mean_staleness is not None else 999.0
    pm = pending_max if pending_max is not None else 999.0
    lr = lag_ratio if lag_ratio is not None else 999.0
    return 3.0 * ms + 2.0 * pm + max(0.0, lr - 1.0)


def _pipeline_hz_mean(exp_dir: Path) -> float | None:
    results = exp_dir / "results.csv"
    if not results.is_file():
        return None
    with results.open(encoding="utf-8-sig", newline="") as inp:
        rows = list(csv.DictReader(inp, delimiter=";"))
    vals: list[float] = []
    for r in rows:
        if r.get("mode") != "process" or r.get("capture") != "opencv":
            continue
        try:
            vals.append(float(str(r.get("pipeline_hz_est", "")).replace(",", ".")))
        except (TypeError, ValueError):
            pass
    return statistics.mean(vals) if vals else None


def collect_experiment(exp_id: str, exp_dir: Path) -> dict[str, Any]:
    barrier = _load_barrier_rows(exp_dir)
    e2e_p = _load_e2e(exp_dir / "e2e_opencv_process.json")
    e2e_t = _load_e2e(exp_dir / "e2e_opencv_thread.json")
    env: dict[str, str] = {}
    env_path = exp_dir / "env.json"
    if env_path.is_file():
        env = json.loads(env_path.read_text(encoding="utf-8"))

    mean_staleness = e2e_p.get("mean_staleness_frames")
    e2e_proc = e2e_p.get("e2e_tracker_fps")
    e2e_thr = e2e_t.get("e2e_tracker_fps")
    e2e_ratio = None
    if e2e_proc and e2e_thr:
        try:
            e2e_ratio = float(e2e_proc) / float(e2e_thr)
        except (TypeError, ValueError, ZeroDivisionError):
            pass

    drop_sum = sum(int(r.get("drop_events") or 0) for r in barrier)
    pending_max = _mean_process(barrier, "mp_pending_max")
    lag_ratio = _mean_process(barrier, "lag_ratio")

    disqualified = []
    if drop_sum > 0:
        disqualified.append("drop_events>0")
    if mean_staleness is not None and float(mean_staleness) > 5:
        disqualified.append("mean_staleness>5")
    if e2e_ratio is not None and e2e_ratio < 0.5:
        disqualified.append("e2e_ratio<0.5")

    return {
        "exp": exp_id,
        "env": env,
        "mp_pending_max": pending_max,
        "lag_ratio": lag_ratio,
        "mean_staleness": mean_staleness,
        "e2e_ratio": e2e_ratio,
        "pipeline_hz_p": _pipeline_hz_mean(exp_dir),
        "drops": drop_sum,
        "score": _score_row(
            mean_staleness=float(mean_staleness) if mean_staleness is not None else None,
            pending_max=pending_max,
            lag_ratio=lag_ratio,
        ),
        "disqualified": disqualified,
    }


def render_matrix(rows: list[dict[str, Any]]) -> str:
    lines = [
        "# Backlog matrix results",
        "",
        "| exp | pending_max | lag_ratio | mean_staleness | e2e_ratio | pipeline_hz_p | drops | score | notes |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for r in sorted(rows, key=lambda x: (x.get("score") is None, x.get("score") or 9999)):
        notes = ", ".join(r.get("disqualified") or []) or "-"
        lines.append(
            f"| {r['exp']} | {r.get('mp_pending_max', '-')} | {r.get('lag_ratio', '-')} | "
            f"{r.get('mean_staleness', '-')} | {r.get('e2e_ratio', '-')} | "
            f"{r.get('pipeline_hz_p', '-')} | {r.get('drops', 0)} | "
            f"{r.get('score', '-')} | {notes} |"
        )

    eligible = [
        r for r in rows if not r.get("disqualified") and r.get("score") is not None
    ]
    if eligible:
        winner = min(eligible, key=lambda x: x["score"])
        lines.extend(
            [
                "",
                f"**Suggested winner:** `{winner['exp']}` (score={winner['score']:.2f})",
                "",
                "Score = 3×mean_staleness + 2×mp_pending_max + max(0, lag_ratio−1). Lower is better.",
            ]
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare backlog matrix experiments.")
    parser.add_argument(
        "--matrix-dir",
        default=str(MATRIX_ROOT.relative_to(REPO_ROOT)),
    )
    parser.add_argument("--experiments", nargs="*", default=None)
    parser.add_argument("--write-winner", action="store_true")
    args = parser.parse_args()

    matrix_dir = (REPO_ROOT / args.matrix_dir).resolve()
    if not matrix_dir.is_dir():
        print(f"Matrix dir missing: {matrix_dir}", file=__import__("sys").stderr)
        return 1

    exp_ids = args.experiments or sorted(
        p.name for p in matrix_dir.iterdir() if p.is_dir() and p.name.startswith("B")
    )
    rows = []
    for exp_id in exp_ids:
        exp_dir = matrix_dir / exp_id
        if exp_dir.is_dir():
            rows.append(collect_experiment(exp_id, exp_dir))

    if not rows:
        print("No experiment rows.", file=__import__("sys").stderr)
        return 1

    md = render_matrix(rows)
    out_path = matrix_dir / "matrix_results.md"
    out_path.write_text(md, encoding="utf-8")
    print(md)

    if args.write_winner:
        eligible = [
            r for r in rows if not r.get("disqualified") and r.get("score") is not None
        ]
        pool = eligible if eligible else [
            r for r in rows if r.get("score") is not None and not str(r.get("exp", "")).endswith("_smoke")
        ]
        if pool:
            winner = min(pool, key=lambda x: x["score"])
            note = "eligible" if eligible else "best_score_all_disqualified"
            (matrix_dir / "WINNER.txt").write_text(
                f"{winner['exp']}\n",
                encoding="utf-8",
            )
            (matrix_dir / "WINNER_meta.txt").write_text(
                f"exp={winner['exp']}\nnote={note}\nscore={winner.get('score')}\n",
                encoding="utf-8",
            )
            print(f"Wrote WINNER.txt -> {winner['exp']} ({note})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
