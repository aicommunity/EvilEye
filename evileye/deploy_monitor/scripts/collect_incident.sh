#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

REASON="${1:-unknown}"
INCIDENT_ID="${2:-$(incident_id_now)}"
INCIDENT_DIR="$INCIDENTS_DIR/$INCIDENT_ID"
mkdir -p "$INCIDENT_DIR"

MAIN_LOG="$(latest_main_log)"
ERRORS_LOG="$(latest_errors_log)"
CLI_PID="$(find_cli_pid)"
CHILD_PID="$(find_child_pid)"

{
    echo "incident_id=$INCIDENT_ID"
    echo "collected_at=$(date -Is)"
    echo "reason=$REASON"
    echo "cli_pid=${CLI_PID:-none}"
    echo "child_pid=${CHILD_PID:-none}"
    echo "main_log=${MAIN_LOG:-none}"
    echo "errors_log=${ERRORS_LOG:-none}"
    echo "in_scheduled_restart_window=$(in_scheduled_restart_window && echo yes || echo no)"
    echo "manual_stop_active=$(manual_stop_active && echo yes || echo no)"
} >"$INCIDENT_DIR/summary.txt"

{
    echo "=== ps aux (evileye) ==="
    ps aux 2>/dev/null | grep -E 'evileye|process\.py' | grep -v grep || true
    echo
    echo "=== pgrep ==="
    pgrep -af 'evileye|process\.py' 2>/dev/null || true
} >"$INCIDENT_DIR/ps.txt"

if [[ -n "$MAIN_LOG" && -f "$MAIN_LOG" ]]; then
    tail -n 500 "$MAIN_LOG" >"$INCIDENT_DIR/main.log.tail"
fi

if [[ -n "$ERRORS_LOG" && -f "$ERRORS_LOG" ]]; then
    tail -n 200 "$ERRORS_LOG" >"$INCIDENT_DIR/errors.log.tail"
fi

if command -v nvidia-smi >/dev/null 2>&1; then
    nvidia-smi >"$INCIDENT_DIR/nvidia-smi.txt" 2>&1 || true
else
    echo "nvidia-smi not available" >"$INCIDENT_DIR/nvidia-smi.txt"
fi

if command -v dmesg >/dev/null 2>&1; then
    dmesg -T 2>/dev/null | tail -n 100 >"$INCIDENT_DIR/dmesg.tail" || \
        dmesg 2>/dev/null | tail -n 100 >"$INCIDENT_DIR/dmesg.tail" || true
fi
if [[ ! -s "$INCIDENT_DIR/dmesg.tail" ]]; then
    for kern_log in /var/log/kern.log /var/log/syslog; do
        if [[ -r "$kern_log" ]]; then
            grep -E 'Out of memory|Killed process|oom-kill' "$kern_log" 2>/dev/null | tail -n 50 \
                >"$INCIDENT_DIR/dmesg.tail" || true
            if [[ -s "$INCIDENT_DIR/dmesg.tail" ]]; then
                break
            fi
            tail -n 100 "$kern_log" >"$INCIDENT_DIR/dmesg.tail" 2>/dev/null || true
            break
        fi
    done
fi
if [[ ! -s "$INCIDENT_DIR/dmesg.tail" ]]; then
    echo "dmesg unavailable" >"$INCIDENT_DIR/dmesg.tail"
fi

if [[ -f "$WATCHDOG_LOG" ]]; then
    tail -n 100 "$WATCHDOG_LOG" >"$INCIDENT_DIR/watchdog.log"
fi

if [[ -f "$STATE_FILE" ]]; then
    cp "$STATE_FILE" "$INCIDENT_DIR/state.json"
fi

log_msg "Incident bundle collected: $INCIDENT_DIR ($REASON)"
echo "$INCIDENT_ID" >>"$PENDING_NOTIFY"
