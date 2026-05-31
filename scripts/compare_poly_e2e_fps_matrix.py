#!/usr/bin/env python3
"""Aggregate E2E FPS matrix experiments; maximize e2e with staleness band guard."""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from pathlib import Path
from typing import Any

from measure_poly_e2e_fps import STALENESS_MAX, STALENESS_MIN, staleness_in_band
from poly_mode_compare_lib import DEFAULT_OUT_DIR, REPO_ROOT

MATRIX_ROOT = DEFAULT_OUT_DIR / "experiments" / "e2e_fps_matrix"
E2E_RATIO_MIN = 3.0
PENDING_MAX_LIMIT = 45


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


def _disqualify(
    *,
    mean_staleness: float | None,
    in_band: bool,
    drops: int,
    e2e_ratio: float | None,
    pending_max: float | None,
) -> list[str]:
    reasons: list[str] = []
    if mean_staleness is None or not in_band:
        reasons.append("staleness_out_of_band")
    if mean_staleness is not None and mean_staleness < STALENESS_MIN:
        reasons.append("staleness_too_fresh")
    if mean_staleness is not None and mean_staleness > STALENESS_MAX:
        reasons.append("staleness_too_stale")
    if drops > 0:
        reasons.append("drop_events")
    if e2e_ratio is not None and e2e_ratio < E2E_RATIO_MIN:
        reasons.append("e2e_ratio_low")
    if pending_max is not None and pending_max > PENDING_MAX_LIMIT:
        reasons.append("pending_too_high")
    return reasons


def collect_experiment(exp_id: str, exp_dir: Path) -> dict[str, Any]:
    barrier = _load_barrier_rows(exp_dir)
    e2e_p = _load_e2e(exp_dir / "e2e_opencv_process.json")
    e2e_t = _load_e2e(exp_dir / "e2e_opencv_thread.json")

    e2e_proc = e2e_p.get("e2e_tracker_fps")
    e2e_thr = e2e_t.get("e2e_tracker_fps")
    e2e_ratio = None
    if e2e_proc and e2e_thr:
        try:
            e2e_ratio = float(e2e_proc) / float(e2e_thr)
        except (TypeError, ValueError, ZeroDivisionError):
            pass

    mean_staleness = e2e_p.get("mean_staleness_frames")
    if mean_staleness is not None:
        try:
            mean_staleness = float(mean_staleness)
        except (TypeError, ValueError):
            mean_staleness = None
    in_band = bool(e2e_p.get("staleness_in_band"))
    if mean_staleness is not None:
        in_band = staleness_in_band(mean_staleness)

    drop_sum = sum(int(r.get("drop_events") or 0) for r in barrier)
    pending_max = _mean_process(barrier, "mp_pending_max")

    disqualified = _disqualify(
        mean_staleness=mean_staleness,
        in_band=in_band,
        drops=drop_sum,
        e2e_ratio=e2e_ratio,
        pending_max=pending_max,
    )

    base_score = None
    if e2e_proc is not None and not disqualified:
        base_score = float(e2e_proc) + 0.5 * float(e2e_ratio or 0.0)

    return {
        "exp": exp_id,
        "e2e_tracker_fps": e2e_proc,
        "e2e_ratio": e2e_ratio,
        "mean_staleness": mean_staleness,
        "staleness_in_band": in_band,
        "mp_pending_max": pending_max,
        "drops": drop_sum,
        "base_score": base_score,
        "disqualified": disqualified,
    }


def render_matrix(rows: list[dict[str, Any]]) -> str:
    lines = [
        "# E2E FPS matrix results",
        "",
        "| exp | e2e_fps | e2e_ratio | staleness | in_band | pending_max | score | notes |",
        "| --- | ---: | ---: | ---: | --- | ---: | ---: | --- |",
    ]
    for r in sorted(
        rows,
        key=lambda x: (
            x.get("base_score") is None,
            -(x.get("base_score") or -1),
        ),
    ):
        notes = ", ".join(r.get("disqualified") or []) or "-"
        lines.append(
            f"| {r['exp']} | {r.get('e2e_tracker_fps', '-')} | {r.get('e2e_ratio', '-')} | "
            f"{r.get('mean_staleness', '-')} | {r.get('staleness_in_band', '-')} | "
            f"{r.get('mp_pending_max', '-')} | {r.get('base_score', '-')} | {notes} |"
        )

    eligible = [r for r in rows if not r.get("disqualified") and r.get("base_score") is not None]
    if eligible:
        winner = max(eligible, key=lambda x: x["base_score"])
        lines.extend(
            [
                "",
                f"**Suggested winner:** `{winner['exp']}` (score={winner['base_score']:.2f})",
                "",
                "Score = e2e_tracker_fps + 0.5×e2e_ratio (maximize). "
                f"Disqualified if staleness not in [{STALENESS_MIN}, {STALENESS_MAX}], "
                f"staleness<{STALENESS_MIN} (too fresh), drops>0, e2e_ratio<{E2E_RATIO_MIN}, "
                f"pending_max>{PENDING_MAX_LIMIT}.",
            ]
        )
    else:
        candidates = [
            r
            for r in rows
            if r.get("e2e_tracker_fps") is not None
            and r.get("exp") not in ("F0",)
            and not str(r.get("exp", "")).endswith("_smoke")
        ]
        if candidates:
            fallback = max(candidates, key=lambda x: float(x["e2e_tracker_fps"]))
            lines.extend(
                [
                    "",
                    f"**WARN: no in-band winner.** Best e2e (non-F0): `{fallback['exp']}`",
                ]
            )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare E2E FPS matrix experiments.")
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
        p.name for p in matrix_dir.iterdir() if p.is_dir() and p.name.startswith("F")
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
        eligible = [r for r in rows if not r.get("disqualified") and r.get("base_score") is not None]
        winner = None
        note = "eligible"
        if eligible:
            winner = max(eligible, key=lambda x: x["base_score"])
        else:
            candidates = [
                r for r in rows
                if r.get("e2e_tracker_fps") is not None
                and r.get("exp") not in ("F0",)
                and not str(r.get("exp", "")).endswith("_smoke")
            ]
            if candidates:
                winner = max(candidates, key=lambda x: float(x["e2e_tracker_fps"]))
                note = "fallback_best_e2e_no_in_band"
        if winner:
            (matrix_dir / "WINNER.txt").write_text(winner["exp"] + "\n", encoding="utf-8")
            (matrix_dir / "WINNER_meta.txt").write_text(
                json.dumps(
                    {
                        "exp": winner["exp"],
                        "note": note,
                        "base_score": winner.get("base_score"),
                        "disqualified": winner.get("disqualified"),
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            print(f"Wrote WINNER.txt -> {winner['exp']} ({note})")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
