#!/usr/bin/env bash
# Start EvilEye in the user's graphical session (cameras + GUI).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=common.sh
source "$SCRIPT_DIR/common.sh"

cleanup_orphan_mp_workers

for pid in $(pgrep -f "$CHILD_PATTERN" 2>/dev/null || true); do kill -TERM "$pid" 2>/dev/null || true; done
for pid in $(pgrep -f "$CLI_PATTERN" 2>/dev/null || true); do kill -TERM "$pid" 2>/dev/null || true; done
sleep 3
for pid in $(pgrep -f "$CHILD_PATTERN" 2>/dev/null || true); do kill -KILL "$pid" 2>/dev/null || true; done
for pid in $(pgrep -f "$CLI_PATTERN" 2>/dev/null || true); do kill -KILL "$pid" 2>/dev/null || true; done
cleanup_orphan_mp_workers

load_gui_env
export EVILEYE_SCHEDULER_GPU_SETTLE_SEC="${EVILEYE_SCHEDULER_GPU_SETTLE_SEC:-15}"

cd "$DEPLOY_DIR"
echo "Starting EvilEye with DISPLAY=${DISPLAY:-} CONFIG=$CONFIG_NAME DEPLOY_DIR=$DEPLOY_DIR"
exec evileye run "$CONFIG_NAME"
