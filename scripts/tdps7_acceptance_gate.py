#!/usr/bin/env python3
"""Acceptance gate for TD-PS-D6/D7: end-to-end frame-delivery budget.

Runs the CURRENT checkout on a reference clip (same harness as
``scripts/runtime_compare.py``) and fails unless the share of frames that
reach the tracker output meets the budget. This turns the open acceptance
criterion ("target FPS/p95/loss budget") into a single hard-gated command for
the GPU host:

    python scripts/tdps7_acceptance_gate.py --video <clip.mp4> \
        --min-tracker-ratio 0.92 --runs 3 --seconds 60

Linux only (same constraint as runtime_compare.py: control socket polling).
Exit code 0 = budget met, 1 = budget missed, 2 = measurement error.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from runtime_compare import (  # noqa: E402
    build_config,
    make_clip,
    run_once,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--video", required=True, help="reference clip (2688x1520 recommended)")
    parser.add_argument("--min-tracker-ratio", type=float, default=0.92,
                        help="budget: TrackersOut/DetectorsIn median across runs (default 0.92 = parity with main)")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--seconds", type=int, default=60)
    parser.add_argument("--model", default="models/yolo11m.pt")
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--report", help="append a markdown row to this file")
    args = parser.parse_args(argv)

    tree = Path(__file__).resolve().parents[1]
    ratios = []
    # A file inside configs/ makes the pipeline chdir to the repo root, so
    # relative model paths resolve to <repo>/models. See run_config_helper.
    config_path = tree / "configs" / "_tdps7_acceptance.json"
    clip_dir = tree / "logs" / "tdps7_gate"
    for run in range(1, args.runs + 1):
        try:
            clip = make_clip(args.video, args.seconds, clip_dir)
            config_path.write_text(
                json.dumps(build_config(tree, clip, args.model, tracker=True)),
                encoding="utf-8",
            )
            result = run_once(tree, config_path, args.timeout)
        except Exception as exc:
            print(f"run {run}: measurement error: {exc}")
            return 2
        finally:
            config_path.unlink(missing_ok=True)
        if result.get("timed_out"):
            print(f"run {run}: timed out after {args.timeout}s")
            return 2
        into_detector = int(result.get("detector_in") or 0)
        tracker_out = int(result.get("tracker_out") or 0)
        if into_detector <= 0:
            print(f"run {run}: detector saw no frames (DetectorsIn=0); aborting")
            return 2
        ratio = tracker_out / into_detector
        ratios.append(ratio)
        print(f"run {run}: DetectorsIn={into_detector} TrackersOut={tracker_out} ratio={ratio:.3f}")

    median = statistics.median(ratios)
    verdict = "PASS" if median >= args.min_tracker_ratio else "FAIL"
    print(f"median tracker-delivery ratio: {median:.3f} (budget >= {args.min_tracker_ratio:.3f}) -> {verdict}")

    if args.report:
        import time

        report = Path(args.report)
        line = (
            f"| {time.strftime('%Y-%m-%d %H:%M')} | {tree} | "
            f"{median:.3f} | {', '.join(f'{r:.3f}' for r in ratios)} | "
            f">= {args.min_tracker_ratio:.3f} | {verdict} |\n"
        )
        header = "| when | tree | median | runs | budget | verdict |\n|---|---|---|---|---|---|\n"
        if not report.exists():
            report.write_text(header, encoding="utf-8")
        with report.open("a", encoding="utf-8") as fh:
            fh.write(line)

    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
