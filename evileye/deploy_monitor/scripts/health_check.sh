#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

mkdir -p "$INCIDENTS_DIR" "$MONITOR_DIR/reports"
touch "$JOURNAL_FILE" "$WATCHDOG_LOG"

CLI_PID="$(find_cli_pid)"
CHILD_PID="$(find_child_pid)"
MAIN_LOG="$(latest_main_log)"
LOG_AGE="$(log_age_sec "$MAIN_LOG")"
NEXT_RUN=""

if [[ -f "$MAIN_LOG" ]]; then
    NEXT_RUN="$(grep -o 'Next launch scheduled at [0-9T:.-]*' "$MAIN_LOG" 2>/dev/null | tail -1 | sed 's/Next launch scheduled at //' || true)"
fi

STATUS="ok"
REASONS=()
INCIDENT=false
DO_RESTART=false

scan_log_tail() {
    local log_file="$1"
    local lines=300
    if [[ ! -f "$log_file" ]]; then
        return
    fi
    tail -n "$lines" "$log_file"
}

is_recent_log_line() {
    local line="$1"
    local max_age_sec="${2:-600}"
    local ts epoch now
    ts="$(sed -n 's/^\([0-9]\{4\}-[0-9]\{2\}-[0-9]\{2\} [0-9]\{2\}:[0-9]\{2\}:[0-9]\{2\}\).*/\1/p' <<<"$line")"
    [[ -n "$ts" ]] || return 1
    epoch=$(date -d "$ts" +%s 2>/dev/null || echo 0)
    now=$(date +%s)
    (( epoch > 0 && now - epoch <= max_age_sec ))
}

LOG_TAIL="$(scan_log_tail "$MAIN_LOG")"

# Detect intentional GUI shutdown (not scheduler exit after child crash/kill).
if ! watchdog_restarting_recent; then
    if grep -q 'Events journal closed' <<<"$LOG_TAIL" \
        && grep -q 'Database journal closed' <<<"$LOG_TAIL" \
        && grep -q 'aboutToQuit' <<<"$LOG_TAIL"; then
        recent_gui_close=false
        while IFS= read -r line; do
            if grep -q 'Database journal closed' <<<"$line" && is_recent_log_line "$line" 300; then
                recent_gui_close=true
                break
            fi
        done <<<"$(grep 'Database journal closed' <<<"$LOG_TAIL" || true)"
        if $recent_gui_close && ! manual_stop_active; then
            set_manual_stop_cooldown
        fi
    fi
fi

if grep -q 'stopping scheduler loop' <<<"$LOG_TAIL"; then
    recent_scheduler_stop=false
    while IFS= read -r line; do
        if is_recent_log_line "$line" 300; then
            recent_scheduler_stop=true
            break
        fi
    done <<<"$(grep 'stopping scheduler loop' <<<"$LOG_TAIL" || true)"
    if $recent_scheduler_stop && ! in_scheduled_restart_window; then
        INCIDENT=true
        REASONS+=("scheduler_stopped_unexpectedly")
        DO_RESTART=true
    fi
fi

if [[ -z "$CLI_PID" ]]; then
    if pipeline_child_healthy; then
        REASONS+=("managed_child_only")
    elif ! restart_grace_active; then
        INCIDENT=true
        REASONS+=("cli_process_missing")
        DO_RESTART=true
    else
        REASONS+=("cli_missing_during_restart_grace")
    fi
fi

if [[ -z "$CHILD_PID" ]]; then
    if ! restart_grace_active; then
        INCIDENT=true
        REASONS+=("child_process_missing")
        DO_RESTART=true
    else
        REASONS+=("child_missing_during_restart_grace")
    fi
fi

if [[ -n "$CLI_PID" && -n "$CHILD_PID" && -n "$MAIN_LOG" ]]; then
    if (( LOG_AGE > LOG_STALE_SEC )); then
        child_cpu=""
        if [[ -r "/proc/$CHILD_PID/stat" ]]; then
            child_cpu=$(ps -p "$CHILD_PID" -o %cpu= 2>/dev/null | tr -d ' ' || true)
        fi
        cleanup_stuck=false
        if (( LOG_AGE > 1800 )) \
            && grep -q 'Starting cleanup due to constraints violation' <<<"$LOG_TAIL" \
            && ! grep -q 'Total cleanup:' <<<"$LOG_TAIL"; then
            cleanup_stuck=true
        fi
        if in_scheduled_restart_window && grep -q 'terminating process pid=.*for scheduled restart' <<<"$LOG_TAIL"; then
            STATUS="scheduled_restart_in_progress"
            REASONS+=("log_stale_during_scheduled_restart")
        elif $cleanup_stuck; then
            INCIDENT=true
            REASONS+=("log_stale_during_stuck_cleanup_${LOG_AGE}s")
            DO_RESTART=true
        elif [[ -n "$child_cpu" ]] && python3 -c "import sys; sys.exit(0 if float('${child_cpu:-0}') >= 1.0 else 1)" 2>/dev/null; then
            REASONS+=("log_stale_but_child_active_cpu_${child_cpu}")
        else
            INCIDENT=true
            REASONS+=("log_stale_${LOG_AGE}s")
            DO_RESTART=true
        fi
    fi
fi

# Abrupt termination: both processes gone, log has no graceful shutdown in tail.
if [[ -z "$CLI_PID" && -z "$CHILD_PID" && -n "$MAIN_LOG" ]]; then
    if ! grep -qE 'Application finished with code:|scheduler loop stopping' <<<"$LOG_TAIL"; then
        if ! in_scheduled_restart_window && ! restart_grace_active; then
            INCIDENT=true
            REASONS+=("abrupt_log_end_no_shutdown")
            DO_RESTART=true
        fi
    fi
fi

if $INCIDENT; then
    STATUS="incident"
elif ((${#REASONS[@]} > 0)); then
    STATUS="${REASONS[0]}"
fi

if ((${#REASONS[@]} == 0)); then
    REASONS+=("healthy")
fi
REASON_STR="$(IFS=';'; echo "${REASONS[*]}")"

ENTRY="$(append_journal "$STATUS" "$REASON_STR" "$CLI_PID" "$CHILD_PID" "$MAIN_LOG" "$LOG_AGE")"
echo "$ENTRY" >>"$JOURNAL_FILE"
update_state "$CLI_PID" "$CHILD_PID" "$MAIN_LOG" "$NEXT_RUN"

# Memory telemetry (best-effort; never fail the health check).
if [[ -x "$SCRIPT_DIR/collect_memory_snapshot.sh" ]]; then
    "$SCRIPT_DIR/collect_memory_snapshot.sh" >>"$WATCHDOG_LOG" 2>&1 || true
fi

if $INCIDENT; then
    INCIDENT_ID="$(incident_id_now)"
    log_msg "INCIDENT detected: $REASON_STR"
    "$SCRIPT_DIR/collect_incident.sh" "$REASON_STR" "$INCIDENT_ID"

    if $DO_RESTART; then
        if manual_stop_active; then
            log_msg "Restart suppressed: manual-stop cooldown active"
        elif in_scheduled_restart_window && grep -q 'terminating process pid=.*for scheduled restart' <<<"$LOG_TAIL"; then
            log_msg "Restart suppressed: scheduled restart in progress"
        elif restart_backoff_active; then
            log_msg "Restart suppressed: backoff active (streak=$(cat "$RESTART_BACKOFF_FILE" 2>/dev/null || echo 0))"
        else
            mark_watchdog_restarting
            restart_backoff_delay_sec >/dev/null
            "$SCRIPT_DIR/restart_evileye.sh" "$REASON_STR" || log_msg "Restart failed"
        fi
    fi
else
    reset_restart_backoff
    log_msg "Health OK: cli=$CLI_PID child=$CHILD_PID log_age=${LOG_AGE}s"
fi
