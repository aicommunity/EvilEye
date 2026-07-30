#!/usr/bin/env bash
# Append one memory snapshot for EvilEye tree to monitor/memory_journal.jsonl.
# Called from health_check (every 5 min) or manually.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

MEMORY_JOURNAL="${MEMORY_JOURNAL:-$MONITOR_DIR/memory_journal.jsonl}"
mkdir -p "$MONITOR_DIR"

export DEPLOY_DIR MONITOR_DIR
python3 - "$MEMORY_JOURNAL" "$CLI_PATTERN" "$CHILD_PATTERN" "$DEPLOY_DIR" <<'PY'
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

journal_path, cli_pattern, child_pattern, deploy_dir = sys.argv[1:5]


def pgrep(pattern: str) -> list[int]:
    try:
        out = subprocess.check_output(["pgrep", "-f", pattern], text=True)
    except subprocess.CalledProcessError:
        return []
    return [int(x) for x in out.split() if x.strip().isdigit()]


def children(pid: int) -> list[int]:
    try:
        out = subprocess.check_output(["pgrep", "-P", str(pid)], text=True)
    except subprocess.CalledProcessError:
        return []
    return [int(x) for x in out.split() if x.strip().isdigit()]


def rss_pss_swap_kb(pid: int) -> tuple[int, int, int]:
    rss = pss = swap = 0
    try:
        with open(f"/proc/{pid}/status", encoding="utf-8") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    rss = int(line.split()[1])
                    break
    except OSError:
        return 0, 0, 0
    try:
        with open(f"/proc/{pid}/smaps_rollup", encoding="utf-8") as f:
            for line in f:
                if line.startswith("Pss:"):
                    pss = int(line.split()[1])
                elif line.startswith("Swap:"):
                    swap = int(line.split()[1])
    except OSError:
        pss = rss
    return rss, pss, swap


def cmdline(pid: int) -> str:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ")
        return raw.decode(errors="replace")[:160]
    except OSError:
        return ""


def swap_used_kb() -> int:
    try:
        text = Path("/proc/swaps").read_text(encoding="utf-8")
    except OSError:
        return 0
    total = 0
    for line in text.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 4:
            try:
                total += int(parts[3])
            except ValueError:
                pass
    return total


def meminfo_kb() -> dict:
    out = {}
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            key, _, rest = line.partition(":")
            out[key] = int(rest.split()[0])
    except OSError:
        pass
    return out


cli_pids = pgrep(cli_pattern)
child_pids = pgrep(child_pattern)
cli_pid = cli_pids[0] if cli_pids else None
child_pid = child_pids[0] if child_pids else None

roles = {
    "process_main": {"rss_kb": 0, "pss_kb": 0, "swap_kb": 0, "count": 0},
    "det_mp": {"rss_kb": 0, "pss_kb": 0, "swap_kb": 0, "count": 0},
    "tracker": {"rss_kb": 0, "pss_kb": 0, "swap_kb": 0, "count": 0},
    "web": {"rss_kb": 0, "pss_kb": 0, "swap_kb": 0, "count": 0},
    "other": {"rss_kb": 0, "pss_kb": 0, "swap_kb": 0, "count": 0},
    "cli": {"rss_kb": 0, "pss_kb": 0, "swap_kb": 0, "count": 0},
}

tree_pids: set[int] = set()
if cli_pid:
    tree_pids.add(cli_pid)
if child_pid:
    tree_pids.add(child_pid)
    for c in children(child_pid):
        tree_pids.add(c)

# Best-effort role from latest main log worker starts
pid_role: dict[int, str] = {}
try:
    logs = sorted(Path(deploy_dir).glob("logs/*_evileye_main.log"), key=lambda p: p.stat().st_mtime)
    if logs:
        text = logs[-1].read_text(encoding="utf-8", errors="replace")[-400_000:]
        for m in re.finditer(r"evileye\.(det-mp-\d+) - INFO - start:\d+ - Started worker process pid=(\d+)", text):
            pid_role[int(m.group(2))] = "det_mp"
        for m in re.finditer(r"evileye\.(tracker-\d+) - INFO - start:\d+ - Started worker process pid=(\d+)", text):
            pid_role[int(m.group(2))] = "tracker"
        for m in re.finditer(r"Web server process started, pid=(\d+)", text):
            pid_role[int(m.group(1))] = "web"
except Exception:
    pass

if child_pid:
    pid_role[child_pid] = "process_main"
if cli_pid:
    pid_role[cli_pid] = "cli"

total_rss = total_pss = total_swap = 0
for pid in sorted(tree_pids):
    rss, pss, swap = rss_pss_swap_kb(pid)
    if rss <= 0 and pss <= 0:
        continue
    role = pid_role.get(pid)
    if role is None:
        cmd = cmdline(pid).lower()
        if "spawn_main" in cmd:
            role = "other"
        else:
            role = "other"
    bucket = roles.setdefault(role, {"rss_kb": 0, "pss_kb": 0, "swap_kb": 0, "count": 0})
    bucket["rss_kb"] += rss
    bucket["pss_kb"] += pss
    bucket["swap_kb"] += swap
    bucket["count"] += 1
    total_rss += rss
    total_pss += pss
    total_swap += swap

mi = meminfo_kb()
entry = {
    "timestamp": datetime.now(timezone.utc).astimezone().isoformat(),
    "cli_pid": cli_pid,
    "child_pid": child_pid,
    "tree": {
        "proc_count": len(tree_pids),
        "rss_kb": total_rss,
        "pss_kb": total_pss,
        "swap_kb": total_swap,
        "rss_gb": round(total_rss / 1024 / 1024, 3),
        "pss_gb": round(total_pss / 1024 / 1024, 3),
    },
    "roles": roles,
    "host": {
        "mem_total_kb": mi.get("MemTotal"),
        "mem_available_kb": mi.get("MemAvailable"),
        "swap_total_kb": mi.get("SwapTotal"),
        "swap_free_kb": mi.get("SwapFree"),
        "swap_used_kb": swap_used_kb(),
    },
}

path = Path(journal_path)
with path.open("a", encoding="utf-8") as f:
    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
print(
    f"memory_journal: tree_rss_gb={entry['tree']['rss_gb']} "
    f"pss_gb={entry['tree']['pss_gb']} swap_used_gb="
    f"{round((entry['host']['swap_used_kb'] or 0)/1024/1024, 2)} "
    f"det={roles['det_mp']['count']} tracker={roles['tracker']['count']}"
)
PY
