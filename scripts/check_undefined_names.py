#!/usr/bin/env python3
"""Fail when ruff finds undefined names or syntax errors that are not in the baseline.

The repository still has known F821 findings (mostly optional Qt imports). They are
recorded in ``scripts/ruff_baseline.json`` so CI blocks only *new* findings.
Line numbers are ignored, so unrelated edits do not invalidate the baseline.

    python scripts/check_undefined_names.py            # check
    python scripts/check_undefined_names.py --update   # rewrite the baseline
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "scripts" / "ruff_baseline.json"
TARGETS = ["evileye", "tests", "scripts", "examples"]
RULES = "F821,E9"


def collect() -> Counter:
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--select", RULES, "--no-cache",
         "--output-format", "json", *TARGETS],
        cwd=ROOT, capture_output=True, text=True,
    )
    if result.returncode not in (0, 1):
        sys.stderr.write(result.stdout + result.stderr)
        raise SystemExit(f"ruff failed with exit code {result.returncode}")
    findings = Counter()
    for item in json.loads(result.stdout or "[]"):
        path = Path(item["filename"]).resolve().relative_to(ROOT).as_posix()
        findings[f"{path}|{item['code']}|{item['message']}"] += 1
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--update", action="store_true", help="rewrite the baseline")
    args = parser.parse_args()
    current = collect()
    if args.update:
        BASELINE.write_text(json.dumps(dict(sorted(current.items())), indent=2) + "\n", encoding="utf-8")
        print(f"baseline updated: {sum(current.values())} findings")
        return 0
    baseline = Counter(json.loads(BASELINE.read_text(encoding="utf-8")))
    new = current - baseline
    fixed = baseline - current
    if fixed:
        print(f"{sum(fixed.values())} baseline finding(s) are fixed; "
              "run with --update to shrink the baseline.")
    if new:
        print("New undefined names / syntax errors:")
        for key, count in sorted(new.items()):
            print(f"  {key}" + (f"  (x{count})" if count > 1 else ""))
        return 1
    print(f"OK: no new findings ({sum(current.values())} known)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
