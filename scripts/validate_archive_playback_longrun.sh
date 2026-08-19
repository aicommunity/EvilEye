#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CONFIG_NAME="${CONFIG_NAME:-poly-cameras-gst.json}"
CONFIG_PATH="$ROOT/configs/$CONFIG_NAME"

BASE="${EVILEYE_E2E_BASE:-http://127.0.0.1:8181}"
READY_URL="$BASE/ready"

E2E_LONGRUN_SEC="${E2E_LONGRUN_SEC:-1800}"
E2E_LONGRUN_STEP_MS="${E2E_LONGRUN_STEP_MS:-30000}"
RUN_LONGRUN="${RUN_LONGRUN:-1}"

KILL_EXISTING="${KILL_EXISTING:-1}"

if [[ ! -f "$CONFIG_PATH" ]]; then
  echo "FAIL: config not found: $CONFIG_PATH" >&2
  exit 1
fi

if [[ "$KILL_EXISTING" == "1" ]]; then
  # Best-effort kill: avoid being too aggressive with other configs.
  pkill -f "evileye run .*${CONFIG_NAME}" 2>/dev/null || true
  pkill -f "process.py .*${CONFIG_NAME}" 2>/dev/null || true
fi

echo "Ensuring Playwright browsers are installed (chromium)"
npx playwright install chromium >/dev/null 2>&1 || true

echo "Starting evileye run: $CONFIG_NAME"
LOG_FILE="$(mktemp -t evileye-validate-archive-playback-XXXX.log)"
set +e
evileye run "$CONFIG_PATH" --no-gui >"$LOG_FILE" 2>&1 &
PID=$!
set -e
echo "evileye PID=$PID"

echo "Waiting for $READY_URL ..."
for i in {1..120}; do
  if curl -fsS "$READY_URL" >/dev/null 2>&1; then
    echo "Ready after $i*1s"
    break
  fi
  sleep 1
done

if ! curl -fsS "$READY_URL" >/dev/null 2>&1; then
  echo "FAIL: server not ready. Tail log: " >&2
  tail -n 200 "$LOG_FILE" >&2 || true
  kill "$PID" 2>/dev/null || true
  exit 1
fi

echo "Running Playwright web smoke"
npx @playwright/test test tests/e2e/web_smoke.spec.ts --reporter=line

echo "Running Playwright playback seek smoke"
npx @playwright/test test tests/e2e/playback_seek_smoke.spec.ts --reporter=line

if [[ "$RUN_LONGRUN" == "1" ]]; then
  echo "Running Playwright playback long-run seeks (${E2E_LONGRUN_SEC}s)"
  E2E_LONGRUN_SEC="$E2E_LONGRUN_SEC" E2E_LONGRUN_STEP_MS="$E2E_LONGRUN_STEP_MS" npx @playwright/test test tests/e2e/playback_longrun_seek.spec.ts --reporter=line
else
  echo "Skipping long-run (RUN_LONGRUN=0)"
fi

echo "Validation completed."

if [[ "$KILL_EXISTING" == "1" ]]; then
  pkill -f "evileye run .*${CONFIG_NAME}" 2>/dev/null || true
  pkill -f "process.py .*${CONFIG_NAME}" 2>/dev/null || true
fi

