#!/usr/bin/env python3
"""Warn on configs that mix legacy detector types with execution_mode."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def validate(data: dict) -> list[str]:
    warnings: list[str] = []
    detectors = data.get("detectors") or []
    for i, det in enumerate(detectors):
        if not isinstance(det, dict):
            continue
        dtype = det.get("type", "")
        if dtype == "ObjectDetectorYoloMp":
            warnings.append(
                f"detectors[{i}]: ObjectDetectorYoloMp is legacy; "
                "use ObjectDetectorYolo with execution_mode=process"
            )

    mc = data.get("mc_trackers") or []
    for i, block in enumerate(mc):
        if not isinstance(block, dict):
            continue
        if block.get("execution_mode") == "process":
            warnings.append(
                f"mc_trackers[{i}]: execution_mode=process is ignored; "
                "mc_trackers is sync_batch in parent only (see thread_vs_mp_contracts §7)"
            )
        if block.get("stage_kind") == "sync_batch":
            continue
        if block.get("enable", True) is False:
            continue
    return warnings


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Usage: validate_config.py <config.json>", file=sys.stderr)
        return 2
    path = Path(argv[1])
    data = json.loads(path.read_text(encoding="utf-8"))
    warnings = validate(data)
    for w in warnings:
        print(f"WARN: {w}")
    return 1 if warnings else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
