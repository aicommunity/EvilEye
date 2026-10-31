#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/common.sh"
CHILD_PID="$(find_child_pid)"
if [[ -z "$CHILD_PID" ]] || restart_grace_active || manual_stop_active; then
    exit 0
fi
# Serialize the lightweight poll with the regular health check.
exec 8>"$MONITOR_DIR/.event_health_lock"
flock -n 8 || exit 0
if ! python3 -m evileye.deploy_monitor.event_health "$DEPLOY_DIR" "$CHILD_PID"; then
    flock -u 8
    exec bash "$SCRIPT_DIR/health_check.sh"
fi
