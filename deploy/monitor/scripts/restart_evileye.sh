#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

REASON="${1:-watchdog_restart}"
# Require a healthy boot marker before declaring restart success.
BOOT_OK_PATTERN="${BOOT_OK_PATTERN:-GUI shown|Starting main application loop|Controller started in headless mode|Starting controller initialization synchronously \\(headless mode\\)}"
# How long to wait for boot marker after child appears.
BOOT_WAIT_SEC="${BOOT_WAIT_SEC:-120}"
# Extra settle time after marker (or after child) before final liveness check.
POST_BOOT_SETTLE_SEC="${POST_BOOT_SETTLE_SEC:-20}"

if [[ -f "$RESTART_LOCK" ]]; then
    lock_age=$(($(date +%s) - $(stat -c %Y "$RESTART_LOCK")))
    if (( lock_age < 300 )); then
        log_msg "Restart skipped: lock active (${lock_age}s old)"
        exit 0
    fi
    rm -f "$RESTART_LOCK"
fi

touch "$RESTART_LOCK"
trap 'rm -f "$RESTART_LOCK"' EXIT

SPAWN_LOCK="$MONITOR_DIR/.spawn.lock"
exec 200>"$SPAWN_LOCK"
if ! flock -w 30 200; then
    log_msg "Restart skipped: could not acquire spawn lock"
    exit 0
fi

mark_watchdog_restarting
log_msg "Starting EvilEye restart (reason=$REASON)"

# Stop existing processes gracefully, then force-kill leftovers.
for pid in $(pgrep -f "$CHILD_PATTERN" 2>/dev/null || true); do
    kill -TERM "$pid" 2>/dev/null || true
done
for pid in $(pgrep -f "$CLI_PATTERN" 2>/dev/null || true); do
    kill -TERM "$pid" 2>/dev/null || true
done
sleep 5
for pid in $(pgrep -f "$CHILD_PATTERN" 2>/dev/null || true); do
    kill -KILL "$pid" 2>/dev/null || true
done
for pid in $(pgrep -f "$CLI_PATTERN" 2>/dev/null || true); do
    kill -KILL "$pid" 2>/dev/null || true
done

cleanup_orphan_mp_workers

if [[ -n "$(find_child_pid)" ]]; then
    log_msg "Child already running after stop (another agent); skip restart"
    exit 0
fi

# Cleanup stale MP workers if EvilEye package is importable.
(
    cd "$DEPLOY_DIR"
    python3 - <<'PY' 2>/dev/null || true
try:
    from evileye.core.mp_session_registry import cleanup_stale_sessions
    cleaned = cleanup_stale_sessions()
    if cleaned:
        print(f"cleaned_stale_sessions={cleaned}")
except Exception as exc:
    print(f"cleanup_skipped={exc}")
PY
) || true

export EVILEYE_SCHEDULER_GPU_SETTLE_SEC="${EVILEYE_SCHEDULER_GPU_SETTLE_SEC:-15}"
export EVILEYE_CLI_LAUNCHED=1
export EVILEYE_SITE_DIR="${EVILEYE_SITE_DIR:-$DEPLOY_DIR}"

load_gui_env

USE_NO_GUI=1
if [[ "$(profile_gui_default)" == "1" && -n "${DISPLAY:-}" ]]; then
    USE_NO_GUI=0
fi
if [[ "$USE_NO_GUI" -eq 1 ]]; then
    log_msg "Restarting headless (--no-gui)"
fi

# Snapshot latest log so we only match markers from the new run.
pre_log="$(latest_main_log)"
pre_log_size=0
if [[ -n "$pre_log" && -f "$pre_log" ]]; then
    pre_log_size=$(stat -c %s "$pre_log" 2>/dev/null || echo 0)
fi

cd "$DEPLOY_DIR"

# Launch outside the watchdog oneshot cgroup when possible (defense in depth for
# KillMode). Falls back to setsid+nohup.
launch_evileye() {
    local port="${EVILEYE_PORT:-8181}"
    if command -v systemctl >/dev/null 2>&1; then
        if ! systemctl --user is-active evileye.service >/dev/null 2>&1; then
            log_msg "Web service inactive; starting evileye.service before pipeline"
            systemctl --user start evileye.service 2>/dev/null || true
            sleep 3
        fi
    fi
    if ! curl -sf "http://127.0.0.1:${port}/ready" >/dev/null 2>&1; then
        log_msg "ERROR: Web UI not ready on :${port}; skip pipeline restart (run: evileye service start)"
        exit 1
    fi

    if command -v evileye >/dev/null 2>&1; then
        local gui_args=(--no-gui)
        if [[ "$USE_NO_GUI" -eq 0 ]]; then
            gui_args=(--gui)
        fi
        (
            cd "$DEPLOY_DIR"
            evileye pipeline start "$CONFIG_NAME" --release "${gui_args[@]}"
        ) >>"$MONITOR_DIR/watchdog_stdout.log" 2>&1 &
        echo $!
        return
    fi

    local run_cmd
    run_cmd=(env
        "DISPLAY=${DISPLAY:-}"
        "XAUTHORITY=${XAUTHORITY:-}"
        "DBUS_SESSION_BUS_ADDRESS=${DBUS_SESSION_BUS_ADDRESS:-}"
        "EVILEYE_SCHEDULER_GPU_SETTLE_SEC=${EVILEYE_SCHEDULER_GPU_SETTLE_SEC}"
        "EVILEYE_CLI_LAUNCHED=1"
        evileye run "$CONFIG_NAME"
    )
    if [[ "$USE_NO_GUI" -eq 1 ]]; then
        run_cmd=(env
            "EVILEYE_SCHEDULER_GPU_SETTLE_SEC=${EVILEYE_SCHEDULER_GPU_SETTLE_SEC}"
            "EVILEYE_CLI_LAUNCHED=1"
            evileye run "$CONFIG_NAME" --no-gui
        )
    fi

    if command -v systemd-run >/dev/null 2>&1; then
        # Transient scope survives watchdog oneshot exit even if KillMode regresses.
        systemctl --user stop evileye-run.scope 2>/dev/null || true
        # Discard stale failed unit state if any.
        systemctl --user reset-failed evileye-run.scope 2>/dev/null || true
        systemd-run --user --scope --unit=evileye-run \
            --working-directory="$DEPLOY_DIR" \
            --setenv="DISPLAY=${DISPLAY:-}" \
            --setenv="XAUTHORITY=${XAUTHORITY:-}" \
            --setenv="DBUS_SESSION_BUS_ADDRESS=${DBUS_SESSION_BUS_ADDRESS:-}" \
            --setenv="EVILEYE_SCHEDULER_GPU_SETTLE_SEC=${EVILEYE_SCHEDULER_GPU_SETTLE_SEC}" \
            --setenv="EVILEYE_CLI_LAUNCHED=1" \
            bash -c 'if [[ "$2" == 1 ]]; then exec evileye run "$0" --no-gui >>"$1" 2>&1; else exec evileye run "$0" >>"$1" 2>&1; fi' \
            "$CONFIG_NAME" "$MONITOR_DIR/watchdog_stdout.log" "$USE_NO_GUI" &
        echo $!
        return
    fi

    setsid nohup "${run_cmd[@]}" >>"$MONITOR_DIR/watchdog_stdout.log" 2>&1 </dev/null &
    echo $!
}

launcher_pid="$(launch_evileye)"
log_msg "Launched evileye via pid=$launcher_pid DISPLAY=$DISPLAY config=$CONFIG_NAME (GPU settle=${EVILEYE_SCHEDULER_GPU_SETTLE_SEC}s)"

# Wait up to 90s for child process.py to appear.
child_pid=""
cli_pid=""
for _ in $(seq 1 18); do
    sleep 5
    cli_pid="$(find_cli_pid)"
    child_pid="$(find_child_pid)"
    if [[ -n "$child_pid" && -n "$cli_pid" ]]; then
        break
    fi
done

if [[ -z "$child_pid" || -z "$cli_pid" ]]; then
    log_msg "ERROR: process.py/cli did not start within 90s after restart (cli=$cli_pid child=$child_pid)"
    exit 1
fi

log_msg "Child appeared: cli_pid=$cli_pid child_pid=$child_pid — waiting for boot marker"

boot_ok=false
deadline=$(($(date +%s) + BOOT_WAIT_SEC))
while (( $(date +%s) < deadline )); do
    # Processes must stay alive while we wait for the marker.
    if ! kill -0 "$cli_pid" 2>/dev/null || ! kill -0 "$child_pid" 2>/dev/null; then
        log_msg "ERROR: process died before boot marker (cli=$cli_pid child=$child_pid)"
        exit 1
    fi
    # Prefer the newest main log; also accept growth of the previous file.
    main_log="$(latest_main_log)"
    if [[ -n "$main_log" && -f "$main_log" ]]; then
        if [[ "$main_log" != "$pre_log" ]] || (( $(stat -c %s "$main_log" 2>/dev/null || echo 0) > pre_log_size )); then
            if grep -qE "$BOOT_OK_PATTERN" "$main_log" 2>/dev/null; then
                # Only accept marker if it is from this launch window (last 5 min).
                if grep -E "$BOOT_OK_PATTERN" "$main_log" | tail -1 | grep -q .; then
                    marker_line="$(grep -E "$BOOT_OK_PATTERN" "$main_log" | tail -1)"
                    marker_ts="$(sed -n 's/^\([0-9]\{4\}-[0-9]\{2\}-[0-9]\{2\} [0-9]\{2\}:[0-9]\{2\}:[0-9]\{2\}\).*/\1/p' <<<"$marker_line")"
                    if [[ -n "$marker_ts" ]]; then
                        marker_epoch=$(date -d "$marker_ts" +%s 2>/dev/null || echo 0)
                        now=$(date +%s)
                        if (( marker_epoch > 0 && now - marker_epoch <= 300 )); then
                            boot_ok=true
                            log_msg "Boot marker OK: $marker_line"
                            break
                        fi
                    fi
                fi
            fi
        fi
    fi
    sleep 3
done

if ! $boot_ok; then
    log_msg "ERROR: boot marker not found within ${BOOT_WAIT_SEC}s (pattern=$BOOT_OK_PATTERN)"
    exit 1
fi

sleep "$POST_BOOT_SETTLE_SEC"

# Re-resolve pids (CLI pid from systemd-run wrapper may differ from evileye pid).
cli_pid="$(find_cli_pid)"
child_pid="$(find_child_pid)"
if [[ -z "$cli_pid" || -z "$child_pid" ]]; then
    log_msg "ERROR: process disappeared after boot settle (cli=$cli_pid child=$child_pid)"
    exit 1
fi
if ! kill -0 "$cli_pid" 2>/dev/null || ! kill -0 "$child_pid" 2>/dev/null; then
    log_msg "ERROR: process not alive after boot settle (cli=$cli_pid child=$child_pid)"
    exit 1
fi

log_msg "Restart OK: cli_pid=$cli_pid child_pid=$child_pid"
set_restart_grace
reset_restart_backoff
update_state "$cli_pid" "$child_pid" "$(latest_main_log)" ""
