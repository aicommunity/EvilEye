#!/usr/bin/env bash
# Morning report after nightly 01:00 restart — run after 01:15 local time.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

REPORT_DATE="${1:-$(date +%F)}"

"$SCRIPT_DIR/daily_report.sh" "$REPORT_DATE"

REPORT_FILE="$MONITOR_DIR/reports/${REPORT_DATE}.md"
MAIN_LOG="$(latest_main_log)"

python3 - "$REPORT_DATE" "$REPORT_FILE" "$MAIN_LOG" <<'PY'
import sys
from pathlib import Path

report_date, report_file, main_log = sys.argv[1:4]
path = Path(report_file)
text = path.read_text(encoding="utf-8") if path.exists() else ""

extra = [
    "",
    "## Morning checklist (post 01:00)",
    "- Verify `[scheduler] terminating process` and iteration N+1 launch",
    "- Check CUDA OOM within 5 min after restart (det-mp workers ready)",
    "- Confirm scheduler did NOT log `stopping scheduler loop` after planned restart",
    "- Confirm `evileye run` parent process still alive after child restart",
]

if main_log and Path(main_log).exists():
    log = Path(main_log).read_text(encoding="utf-8", errors="replace")
    ymd_compact = report_date.replace("-", "")
    ymd_dash = report_date
    hits = [ln for ln in log.splitlines() if ymd_dash in ln or ymd_compact in ln]
    restart_hits = [ln for ln in hits if "scheduled restart" in ln]
    oom_hits = [ln for ln in hits if "CUDA out of memory" in ln or "CudaOutOfMemoryError" in ln]
    sched_stop = [ln for ln in hits if "stopping scheduler loop" in ln]
    extra.append(f"- Log lines for {report_date}: {len(hits)}")
    extra.append(f"- Scheduled restart events: {len(restart_hits)}")
    extra.append(f"- CUDA OOM events: {len(oom_hits)}")
    extra.append(f"- Scheduler stop events: {len(sched_stop)}")
    if restart_hits:
        extra.append("- Latest restart line:")
        extra.append(f"  - `{restart_hits[-1].strip()}`")
    if oom_hits and not any("ready" in ln for ln in hits):
        extra.append("- **WARNING:** OOM detected; verify worker recovery")
    if sched_stop:
        extra.append("- **WARNING:** Scheduler stop detected on restart day")

path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(text.rstrip() + "\n" + "\n".join(extra) + "\n", encoding="utf-8")
print(path)
PY
