#!/usr/bin/env python
"""Mypy ratchet gate (audit 2026-11, TD-AUD-008).

Runs mypy on an explicit module list with ``--follow-imports=silent`` (only the
listed files are checked) and compares per-file error counts with
``scripts/mypy_baseline.json``. New errors fail the run; the baseline shrinks
as files get annotated. Add modules to MODULES once they are (near) clean.

Usage:
    python scripts/check_mypy_ratchet.py           # gate (CI)
    python scripts/check_mypy_ratchet.py --update  # regenerate baseline
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

BASELINE_PATH = Path(__file__).resolve().parent / "mypy_baseline.json"

# Files opted into the ratchet. Grow this list as modules get typed;
# counts may only go down.
MODULES: tuple[str, ...] = (
    "evileye/core/frame_transport.py",
    "evileye/core/gpu_errors.py",
    "evileye/database_controller/pg_spool.py",
    "evileye/api/core/web_auth_bootstrap.py",
    "evileye/events_detectors/event_cameras.py",
    "evileye/events_detectors/event_schedule_alarm.py",
)

ERROR_RE = re.compile(r"^(?P<file>[^:]+):(?P<line>\d+): error: ")


def run_mypy() -> dict[str, int]:
    cmd = [
        sys.executable, "-m", "mypy",
        "--ignore-missing-imports",
        "--no-error-summary",
        "--follow-imports=silent",
        *MODULES,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    counts: dict[str, int] = defaultdict(int)
    for line in (proc.stdout or "").splitlines():
        match = ERROR_RE.match(line.strip())
        if match:
            counts[match.group("file").replace("\\", "/")] += 1
    return dict(counts)


def main() -> int:
    current = run_mypy()
    if "--update" in sys.argv:
        BASELINE_PATH.write_text(
            json.dumps(dict(sorted(current.items())), indent=2) + "\n", encoding="utf-8"
        )
        print(f"mypy baseline updated: {sum(current.values())} errors across {len(current)} files")
        return 0

    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8")) if BASELINE_PATH.exists() else {}
    failures: list[str] = []
    for module in MODULES:
        base = int(baseline.get(module, 0))
        now = int(current.get(module, 0))
        if now > base:
            failures.append(f"{module}: {base} -> {now} errors (new mypy errors)")
    if failures:
        print("mypy ratchet FAILED (fix the new errors or update the baseline deliberately):")
        for failure in failures:
            print("  " + failure)
        return 1
    total = sum(current.values())
    print(f"mypy ratchet OK: {total} known errors (baseline preserved or improved)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
