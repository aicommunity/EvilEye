#!/usr/bin/env bash
# Generate daily monitoring report (including nightly 01:00 restart analysis).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

REPORT_DATE="${1:-$(date +%F)}"
REPORT_FILE="$MONITOR_DIR/reports/${REPORT_DATE}.md"
MAIN_LOG="$(latest_main_log)"
mkdir -p "$MONITOR_DIR/reports"

python3 - "$REPORT_DATE" "$REPORT_FILE" "$MONITOR_DIR" "$MAIN_LOG" <<'PY'
import json
import re
import sys
from datetime import datetime
from pathlib import Path

report_date, report_file, monitor_dir, main_log = sys.argv[1:5]
monitor = Path(monitor_dir)
journal = monitor / "journal.jsonl"
incidents_dir = monitor / "incidents"
state_file = monitor / "state.json"

state = {}
if state_file.exists():
    state = json.loads(state_file.read_text(encoding="utf-8"))

journal_entries = []
if journal.exists():
    for line in journal.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                journal_entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass

day_entries = [e for e in journal_entries if e.get("timestamp", "").startswith(report_date)]
incidents = sorted([p for p in incidents_dir.iterdir() if p.is_dir() and not p.name.startswith(".")])
day_incidents = [p for p in incidents if p.name.startswith(report_date.replace("-", "")) or report_date in (p / "summary.txt").read_text(encoding="utf-8", errors="replace") if (p / "summary.txt").exists()]

restart_lines = []
oom_lines = []
scheduler_stop = []
if main_log and Path(main_log).exists():
  text = Path(main_log).read_text(encoding="utf-8", errors="replace")
  for line in text.splitlines():
    if report_date.replace("-", "-") in line or report_date[:4] + report_date[5:7] + report_date[8:10] in line:
      if "terminating process pid=" in line and "scheduled restart" in line:
        restart_lines.append(line)
      if "CUDA out of memory" in line or "CudaOutOfMemoryError" in line:
        oom_lines.append(line)
      if "stopping scheduler loop" in line:
        scheduler_stop.append(line)

status_counts = {}
for e in day_entries:
    status_counts[e.get("status", "unknown")] = status_counts.get(e.get("status", "unknown"), 0) + 1

lines = [
    f"# EvilEye monitoring report — {report_date}",
    "",
    f"Generated: {datetime.now().isoformat(timespec='seconds')}",
    "",
    "## Process state",
    f"- CLI PID: {state.get('cli_pid')}",
    f"- Child PID: {state.get('child_pid')}",
    f"- Log file: {state.get('log_file')}",
    f"- Next scheduled restart: {state.get('next_scheduled_restart', 'unknown')}",
    "",
    "## Health checks today",
    f"- Total journal entries: {len(day_entries)}",
]
for k, v in sorted(status_counts.items()):
    lines.append(f"- {k}: {v}")

lines += ["", "## Incidents today", f"- Count: {len(day_incidents)}"]
for inc in day_incidents:
    summary = (inc / "summary.txt").read_text(encoding="utf-8", errors="replace") if (inc / "summary.txt").exists() else ""
    reason = ""
    for sline in summary.splitlines():
        if sline.startswith("reason="):
            reason = sline.split("=", 1)[1]
    lines.append(f"- `{inc.name}`: {reason or 'see bundle'}")

lines += ["", "## Nightly restart (01:00)"]
if restart_lines:
    lines.append(f"- Scheduled restarts detected: {len(restart_lines)}")
    for rl in restart_lines[-5:]:
        lines.append(f"  - `{rl.strip()}`")
else:
    lines.append("- No scheduled restart lines found for this date in current main log.")

lines += ["", "## CUDA OOM events"]
if oom_lines:
    lines.append(f"- OOM events: {len(oom_lines)}")
    for ol in oom_lines[:5]:
        lines.append(f"  - `{ol.strip()[:200]}`")
    if len(oom_lines) > 5:
        lines.append(f"  - ... and {len(oom_lines) - 5} more")
else:
    lines.append("- No CUDA OOM in log for this date.")

lines += ["", "## Scheduler stop events"]
if scheduler_stop:
    for sl in scheduler_stop:
        lines.append(f"- `{sl.strip()}`")
else:
    lines.append("- None.")

Path(report_file).write_text("\n".join(lines) + "\n", encoding="utf-8")
print(report_file)
PY

log_msg "Daily report written: $REPORT_FILE"
