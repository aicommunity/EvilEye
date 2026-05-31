#!/usr/bin/env python3
"""Re-run failed benchmark slots and refresh output snapshots."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from poly_mode_compare_lib import COMPARE_CONFIGS, DEFAULT_OUT_DIR, REPO_ROOT


def _failed_runs(summary_path: Path) -> list[dict]:
    if not summary_path.is_file():
        return []
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    return [r for r in summary.get("runs", []) if r.get("kind") == "run" and not r.get("success")]


def _empty_output_slugs(out_dir: Path) -> list[str]:
    bad: list[str] = []
    for path in sorted((out_dir / "artifacts").glob("*_output.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if not data.get("has_data"):
            slug = data.get("slug") or path.stem.replace("_output", "")
            bad.append(slug)
    return bad


def main() -> int:
    parser = argparse.ArgumentParser(description="Remediate failed poly-videos benchmark runs.")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR.relative_to(REPO_ROOT)))
    parser.add_argument("--timeout-sec", type=int, default=180)
    parser.add_argument("--check-output", action="store_true")
    args = parser.parse_args()

    out_dir = (REPO_ROOT / args.out_dir).resolve()
    summary_path = out_dir / "run_summary.json"
    failed = _failed_runs(summary_path)
    slugs = sorted({str(r.get("slug")) for r in failed if r.get("slug")})

    if args.check_output:
        for slug in _empty_output_slugs(out_dir):
            if slug not in slugs:
                slugs.append(slug)

    if not slugs:
        print("No failed runs or empty outputs to remediate.")
        return 0

    fixes_log = out_dir / "remediation_log.md"
    lines = [
        "# Исправления в ходе эксперимента",
        "",
        "## Автоматическая ремедиация",
        f"- Перезапуск конфигов: {', '.join(slugs)}",
        "- Bench overlay: абсолютные пути к `models/yolov8n.pt` (исключить гонку загрузки в MP)",
        "",
    ]
    fixes_log.write_text("\n".join(lines), encoding="utf-8")

    cmd = [
        sys.executable,
        str(REPO_ROOT / "scripts" / "run_poly_videos_mode_compare.py"),
        "--out-dir",
        str(args.out_dir),
        "--timeout-sec",
        str(args.timeout_sec),
        "--only-failed",
        "--rerun-from-summary",
        "--configs",
        *slugs,
        "--skip-warmup",
    ]
    print("Running:", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=str(REPO_ROOT), check=False)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
