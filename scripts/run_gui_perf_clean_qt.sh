#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

CONFIG_PATH="${1:-configs/poly-cameras.json}"
shift $(( $# > 0 ? 1 : 0 ))

export EVILEYE_PERF_DIAG="${EVILEYE_PERF_DIAG:-1}"
export EVILEYE_PERF_DIAG_EVERY="${EVILEYE_PERF_DIAG_EVERY:-10}"

echo "Running EvilEye GUI with clean Qt environment"
echo "Config: $CONFIG_PATH"
echo "EVILEYE_PERF_DIAG=$EVILEYE_PERF_DIAG"
echo "EVILEYE_PERF_DIAG_EVERY=$EVILEYE_PERF_DIAG_EVERY"

exec env \
    -u LD_LIBRARY_PATH \
    -u QT_PLUGIN_PATH \
    -u QT_QPA_PLATFORM_PLUGIN_PATH \
    EVILEYE_PERF_DIAG="$EVILEYE_PERF_DIAG" \
    EVILEYE_PERF_DIAG_EVERY="$EVILEYE_PERF_DIAG_EVERY" \
    python evileye/process.py --config "$CONFIG_PATH" --gui "$@"
