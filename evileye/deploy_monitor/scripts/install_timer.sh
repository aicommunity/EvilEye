#!/usr/bin/env bash
# Install EvilEye user systemd watchdog + morning-report timers.
#
# Usage:
#   DEPLOY_DIR=/path/to/site ./install_timer.sh
#   ./install_timer.sh /path/to/site
#
# Optional env:
#   CONFIG_NAME=poly-cameras-gst.json
#   DISPLAY=:1
#   XAUTHORITY=...
#   SYNC_SCRIPTS=1   (default) copy package scripts into $DEPLOY_DIR/monitor/scripts
#
# Critical: KillMode=process — oneshot must NOT kill children on exit.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PACKAGE_MONITOR="$(cd "$SCRIPT_DIR/.." && pwd)"
SYSTEMD_USER_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

DEPLOY_DIR="${DEPLOY_DIR:-${1:-}}"
if [[ -z "$DEPLOY_DIR" ]]; then
    # If scripts already live under <site>/monitor/scripts, use that site.
    if [[ "$(basename "$(dirname "$SCRIPT_DIR")")" == "monitor" ]]; then
        DEPLOY_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
    fi
fi
if [[ -z "$DEPLOY_DIR" || ! -d "$DEPLOY_DIR" ]]; then
    echo "ERROR: set DEPLOY_DIR to the EvilEye site directory (configs/, logs/)." >&2
    echo "Example: DEPLOY_DIR=/opt/EvilEyeSite $0" >&2
    exit 1
fi
DEPLOY_DIR="$(cd "$DEPLOY_DIR" && pwd)"
MONITOR_DIR="${MONITOR_DIR:-$DEPLOY_DIR/monitor}"
HEALTH_CHECK="$MONITOR_DIR/scripts/health_check.sh"
CONFIG_NAME="${CONFIG_NAME:-poly-cameras-gst.json}"
SYNC_SCRIPTS="${SYNC_SCRIPTS:-1}"

mkdir -p "$MONITOR_DIR/scripts" "$MONITOR_DIR/systemd" "$MONITOR_DIR/incidents" "$MONITOR_DIR/reports" \
    "$DEPLOY_DIR/logs" "$SYSTEMD_USER_DIR"

_package_scripts="$(cd "$PACKAGE_MONITOR/scripts" && pwd)"
_monitor_scripts="$(cd "$MONITOR_DIR/scripts" && pwd)"
if [[ "$SYNC_SCRIPTS" == "1" && "$_package_scripts" == "$_monitor_scripts" ]]; then
    echo "Site monitor scripts already in place; skipping script sync."
    SYNC_SCRIPTS=0
fi

if [[ "$SYNC_SCRIPTS" == "1" ]]; then
    cp -a "$PACKAGE_MONITOR/scripts/"*.sh "$MONITOR_DIR/scripts/"
    chmod +x "$MONITOR_DIR/scripts/"*.sh
    if [[ -d "$PACKAGE_MONITOR/systemd" ]]; then
        cp -a "$PACKAGE_MONITOR/systemd/"*.service "$PACKAGE_MONITOR/systemd/"*.timer \
            "$MONITOR_DIR/systemd/" 2>/dev/null || \
        cp -a "$PACKAGE_MONITOR/systemd/"* "$MONITOR_DIR/systemd/" 2>/dev/null || true
    fi
    if [[ -f "$PACKAGE_MONITOR/README.md" && ! -f "$MONITOR_DIR/README.md" ]]; then
        cp -a "$PACKAGE_MONITOR/README.md" "$MONITOR_DIR/README.md"
    fi
fi

# Resolve GUI env for the installed unit.
load_display() {
    if [[ -n "${DISPLAY:-}" ]]; then
        return
    fi
    if [[ -f "$MONITOR_DIR/.display_env" ]]; then
        # shellcheck disable=SC1090
        source "$MONITOR_DIR/.display_env"
    fi
    if [[ -z "${DISPLAY:-}" ]]; then
        for sock in /tmp/.X11-unix/X*; do
            [[ -e "$sock" ]] || continue
            DISPLAY=":${sock##*/X}"
            break
        done
    fi
    DISPLAY="${DISPLAY:-:0}"
}
load_display

if [[ -z "${XAUTHORITY:-}" ]]; then
    if [[ -f "$HOME/.Xauthority" ]]; then
        XAUTHORITY="$HOME/.Xauthority"
    elif [[ -f "/run/user/$(id -u)/gdm/Xauthority" ]]; then
        XAUTHORITY="/run/user/$(id -u)/gdm/Xauthority"
    else
        XAUTHORITY=""
    fi
fi

DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=/run/user/$(id -u)/bus}"

# Persist display for future restarts from systemd.
cat >"$MONITOR_DIR/.display_env" <<EOF
export DISPLAY=${DISPLAY}
export XAUTHORITY=${XAUTHORITY}
export DBUS_SESSION_BUS_ADDRESS=${DBUS_SESSION_BUS_ADDRESS}
EOF

ENV_LINES="Environment=DEPLOY_DIR=${DEPLOY_DIR}
Environment=MONITOR_DIR=${MONITOR_DIR}
Environment=CONFIG_NAME=${CONFIG_NAME}
Environment=DISPLAY=${DISPLAY}"
if [[ -n "$XAUTHORITY" ]]; then
    ENV_LINES+="
Environment=XAUTHORITY=${XAUTHORITY}"
fi
ENV_LINES+="
Environment=DBUS_SESSION_BUS_ADDRESS=${DBUS_SESSION_BUS_ADDRESS}"

cat >"$SYSTEMD_USER_DIR/evileye-watchdog.service" <<EOF
[Unit]
Description=EvilEye health watchdog
After=network.target

[Service]
Type=oneshot
# Critical: default KillMode=control-group kills evileye children spawned by
# restart_evileye.sh when this oneshot exits.
KillMode=process
${ENV_LINES}
ExecStart=${HEALTH_CHECK}
WorkingDirectory=${DEPLOY_DIR}
EOF

cat >"$SYSTEMD_USER_DIR/evileye-watchdog.timer" <<EOF
[Unit]
Description=Run EvilEye health watchdog every 5 minutes

[Timer]
OnCalendar=*:0/5
Persistent=true
Unit=evileye-watchdog.service

[Install]
WantedBy=timers.target
EOF

cat >"$SYSTEMD_USER_DIR/evileye-morning-report.service" <<EOF
[Unit]
Description=EvilEye morning monitoring report

[Service]
Type=oneshot
KillMode=process
${ENV_LINES}
ExecStart=${MONITOR_DIR}/scripts/morning_report.sh
WorkingDirectory=${DEPLOY_DIR}
EOF

cat >"$SYSTEMD_USER_DIR/evileye-morning-report.timer" <<EOF
[Unit]
Description=EvilEye morning report at 09:00

[Timer]
OnCalendar=*-*-* 09:00:00
Persistent=true
Unit=evileye-morning-report.service

[Install]
WantedBy=timers.target
EOF

# Keep site-local templates in sync (placeholders already expanded in user units).
cat >"$MONITOR_DIR/systemd/evileye-watchdog.service" <<EOF
[Unit]
Description=EvilEye health watchdog
After=network.target

[Service]
Type=oneshot
KillMode=process
${ENV_LINES}
ExecStart=${HEALTH_CHECK}
WorkingDirectory=${DEPLOY_DIR}
EOF

systemctl --user daemon-reload
systemctl --user enable --now evileye-watchdog.timer
systemctl --user enable --now evileye-morning-report.timer 2>/dev/null || true
systemctl --user status evileye-watchdog.timer --no-pager || true

echo
echo "Installed user timer: evileye-watchdog.timer (every 5 minutes)"
echo "Installed user timer: evileye-morning-report.timer (daily 09:00)"
echo "DEPLOY_DIR=$DEPLOY_DIR"
echo "MONITOR_DIR=$MONITOR_DIR"
echo "CONFIG_NAME=$CONFIG_NAME"
echo "DISPLAY=$DISPLAY KillMode=process"
echo "Manual run: systemctl --user start evileye-watchdog.service"
echo "Logs: $MONITOR_DIR/watchdog.log"
