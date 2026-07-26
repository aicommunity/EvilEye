#!/usr/bin/env bash
# Shared helpers for EvilEye watchdog scripts.
#
# Paths (override via env):
#   DEPLOY_DIR   — site working dir (configs/, logs/); default: parent of MONITOR_DIR
#   MONITOR_DIR  — runtime state (journal, incidents); default: directory containing scripts/..
#   CONFIG_NAME  — config file name passed to `evileye run`

set -euo pipefail

_COMMON_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MONITOR_DIR="${MONITOR_DIR:-$(cd "$_COMMON_DIR/.." && pwd)}"
DEPLOY_DIR="${DEPLOY_DIR:-$(cd "$MONITOR_DIR/.." && pwd)}"
CONFIG_NAME="${CONFIG_NAME:-poly-cameras-gst.json}"
CONFIG_STEM="${CONFIG_NAME%.json}"
LOG_STALE_SEC="${LOG_STALE_SEC:-600}"
MANUAL_STOP_COOLDOWN_SEC="${MANUAL_STOP_COOLDOWN_SEC:-3600}"
SCHEDULED_RESTART_HOUR="${SCHEDULED_RESTART_HOUR:-01}"
SCHEDULED_RESTART_MINUTE="${SCHEDULED_RESTART_MINUTE:-00}"
RESTART_WINDOW_SEC="${RESTART_WINDOW_SEC:-900}"

INCIDENTS_DIR="$MONITOR_DIR/incidents"
JOURNAL_FILE="$MONITOR_DIR/journal.jsonl"
STATE_FILE="$MONITOR_DIR/state.json"
PENDING_NOTIFY="$INCIDENTS_DIR/.pending_notify"
MANUAL_STOP_FILE="$MONITOR_DIR/.manual_stop_until"
WATCHDOG_RESTARTING_FILE="$MONITOR_DIR/.watchdog_restarting"
RESTART_LOCK="$MONITOR_DIR/.restart_lock"
RESTART_BACKOFF_FILE="$MONITOR_DIR/.restart_backoff"
RESTART_GRACE_FILE="$MONITOR_DIR/.restart_grace_until"
WATCHDOG_LOG="$MONITOR_DIR/watchdog.log"
RESTART_GRACE_SEC="${RESTART_GRACE_SEC:-900}"
RESTART_BACKOFF_BASE_SEC="${RESTART_BACKOFF_BASE_SEC:-300}"
RESTART_BACKOFF_MAX_SEC="${RESTART_BACKOFF_MAX_SEC:-3600}"

# Match `evileye run <config>` / process.py --config ...<stem>...
CLI_PATTERN="evileye run.*${CONFIG_STEM}"
CHILD_PATTERN="process\\.py.*${CONFIG_STEM}"

watchdog_restarting_recent() {
    if [[ ! -f "$WATCHDOG_RESTARTING_FILE" ]]; then
        return 1
    fi
    local ts now
    ts=$(stat -c %Y "$WATCHDOG_RESTARTING_FILE" 2>/dev/null || echo 0)
    now=$(date +%s)
    (( now - ts < 600 ))
}

mark_watchdog_restarting() {
    touch "$WATCHDOG_RESTARTING_FILE"
}

cleanup_orphan_mp_workers() {
    local killed=0
    local pid ppid
    while read -r pid; do
        [[ -n "$pid" ]] || continue
        ppid=$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d ' ' || true)
        if [[ -z "$ppid" ]]; then
            continue
        fi
        # Orphaned workers are reparented to systemd --user after SIGKILL on process.py.
        if ! ps -p "$ppid" -o cmd= 2>/dev/null | grep -qE 'process\.py|evileye run'; then
            kill -TERM "$pid" 2>/dev/null || true
            killed=$((killed + 1))
        fi
    done < <(pgrep -f 'multiprocessing.spawn import spawn_main' 2>/dev/null || true)
    if (( killed > 0 )); then
        sleep 2
        while read -r pid; do
            [[ -n "$pid" ]] || continue
            ppid=$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d ' ' || true)
            if ! ps -p "$ppid" -o cmd= 2>/dev/null | grep -qE 'process\.py|evileye run'; then
                kill -KILL "$pid" 2>/dev/null || true
            fi
        done < <(pgrep -f 'multiprocessing.spawn import spawn_main' 2>/dev/null || true)
        log_msg "Killed $killed orphaned multiprocessing worker(s)"
    fi
}

load_gui_env() {
    if [[ -f "$MONITOR_DIR/.display_env" ]]; then
        # shellcheck disable=SC1090
        source "$MONITOR_DIR/.display_env"
    elif [[ -z "${DISPLAY:-}" ]]; then
        for sock in /tmp/.X11-unix/X*; do
            [[ -e "$sock" ]] || continue
            num="${sock##*/X}"
            export DISPLAY=":${num}"
            break
        done
    fi
    if [[ -z "${XAUTHORITY:-}" ]]; then
        if [[ -f "$HOME/.Xauthority" ]]; then
            export XAUTHORITY="$HOME/.Xauthority"
        elif [[ -f "/run/user/$(id -u)/gdm/Xauthority" ]]; then
            export XAUTHORITY="/run/user/$(id -u)/gdm/Xauthority"
        fi
    fi
    if [[ -z "${DBUS_SESSION_BUS_ADDRESS:-}" && -S "/run/user/$(id -u)/bus" ]]; then
        export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$(id -u)/bus"
    fi
}

log_msg() {
    local msg="[$(date -Is)] $*"
    mkdir -p "$MONITOR_DIR"
    echo "$msg" >>"$WATCHDOG_LOG"
    echo "$msg"
}

json_escape() {
    python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))' <<<"$1"
}

find_cli_pid() {
    pgrep -f "$CLI_PATTERN" 2>/dev/null | head -1 || true
}

find_child_pid() {
    pgrep -f "$CHILD_PATTERN" 2>/dev/null | head -1 || true
}

latest_main_log() {
    ls -t "$DEPLOY_DIR"/logs/*_evileye_main.log 2>/dev/null | head -1 || true
}

latest_errors_log() {
    local main_log
    main_log="$(latest_main_log)"
    if [[ -z "$main_log" ]]; then
        return 0
    fi
    echo "${main_log/_evileye_main.log/_evileye_errors.log}"
}

log_age_sec() {
    local log_file="${1:-}"
    if [[ -z "$log_file" || ! -f "$log_file" ]]; then
        echo 999999
        return
    fi
    echo $(($(date +%s) - $(stat -c %Y "$log_file")))
}

in_scheduled_restart_window() {
    local hour minute now_sec window_start window_end
    hour=$(date +%H)
    minute=$(date +%M)
    now_sec=$((10#$hour * 3600 + 10#$minute * 60))
    window_start=$((10#$SCHEDULED_RESTART_HOUR * 3600 + 10#$SCHEDULED_RESTART_MINUTE * 60 - RESTART_WINDOW_SEC))
    window_end=$((10#$SCHEDULED_RESTART_HOUR * 3600 + 10#$SCHEDULED_RESTART_MINUTE * 60 + RESTART_WINDOW_SEC))
    if (( window_start < 0 )); then
        window_start=0
    fi
    (( now_sec >= window_start && now_sec <= window_end ))
}

manual_stop_active() {
    if [[ ! -f "$MANUAL_STOP_FILE" ]]; then
        return 1
    fi
    local until now
    until=$(cat "$MANUAL_STOP_FILE" 2>/dev/null || echo 0)
    now=$(date +%s)
    (( now < until ))
}

set_manual_stop_cooldown() {
    local until
    until=$(($(date +%s) + MANUAL_STOP_COOLDOWN_SEC))
    echo "$until" >"$MANUAL_STOP_FILE"
    log_msg "Manual-stop cooldown set until $(date -d "@$until" -Is)"
}

incident_id_now() {
    date -u +%Y%m%dT%H%M%SZ
}

restart_grace_active() {
    if [[ ! -f "$RESTART_GRACE_FILE" ]]; then
        return 1
    fi
    local until now
    until=$(cat "$RESTART_GRACE_FILE" 2>/dev/null || echo 0)
    now=$(date +%s)
    (( now < until ))
}

set_restart_grace() {
    local until
    until=$(($(date +%s) + RESTART_GRACE_SEC))
    echo "$until" >"$RESTART_GRACE_FILE"
}

restart_backoff_delay_sec() {
    local streak=0
    if [[ -f "$RESTART_BACKOFF_FILE" ]]; then
        streak=$(cat "$RESTART_BACKOFF_FILE" 2>/dev/null || echo 0)
    fi
    streak=$((streak + 1))
    echo "$streak" >"$RESTART_BACKOFF_FILE"
    local delay=$((RESTART_BACKOFF_BASE_SEC * (2 ** (streak - 1))))
    if (( delay > RESTART_BACKOFF_MAX_SEC )); then
        delay=$RESTART_BACKOFF_MAX_SEC
    fi
    echo "$delay"
}

reset_restart_backoff() {
    rm -f "$RESTART_BACKOFF_FILE"
}

restart_backoff_active() {
    if [[ ! -f "$RESTART_BACKOFF_FILE" ]]; then
        return 1
    fi
    local last_ts now streak delay
    last_ts=$(stat -c %Y "$RESTART_BACKOFF_FILE" 2>/dev/null || echo 0)
    now=$(date +%s)
    streak=$(cat "$RESTART_BACKOFF_FILE" 2>/dev/null || echo 0)
    delay=$((RESTART_BACKOFF_BASE_SEC * (2 ** (streak - 1))))
    if (( delay > RESTART_BACKOFF_MAX_SEC )); then
        delay=$RESTART_BACKOFF_MAX_SEC
    fi
    (( now - last_ts < delay ))
}

append_journal() {
    local status="$1"
    local reason="$2"
    local cli_pid="${3:-}"
    local child_pid="${4:-}"
    local log_file="${5:-}"
    local log_age="${6:-}"
    python3 - "$status" "$reason" "$cli_pid" "$child_pid" "$log_file" "$log_age" <<'PY'
import json, sys
from datetime import datetime, timezone

status, reason, cli_pid, child_pid, log_file, log_age = sys.argv[1:7]
entry = {
    "timestamp": datetime.now(timezone.utc).astimezone().isoformat(),
    "status": status,
    "reason": reason,
    "cli_pid": cli_pid or None,
    "child_pid": child_pid or None,
    "log_file": log_file or None,
    "log_age_sec": int(log_age) if log_age.isdigit() else None,
}
print(json.dumps(entry, ensure_ascii=False))
PY
}

update_state() {
    local cli_pid="$1"
    local child_pid="$2"
    local log_file="$3"
    local next_run="${4:-}"
    python3 - "$cli_pid" "$child_pid" "$log_file" "$next_run" "$STATE_FILE" <<'PY'
import json, sys
from datetime import datetime, timezone
from pathlib import Path

cli_pid, child_pid, log_file, next_run, state_file = sys.argv[1:6]
path = Path(state_file)
state = {}
if path.exists():
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        state = {}

state.update({
    "updated_at": datetime.now(timezone.utc).astimezone().isoformat(),
    "cli_pid": int(cli_pid) if cli_pid else None,
    "child_pid": int(child_pid) if child_pid else None,
    "log_file": log_file or None,
    "next_scheduled_restart": next_run or state.get("next_scheduled_restart"),
    "monitoring_started": state.get("monitoring_started") or datetime.now(timezone.utc).astimezone().isoformat(),
    "deploy_dir": str(Path(state_file).resolve().parent.parent),
})
path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
PY
}
