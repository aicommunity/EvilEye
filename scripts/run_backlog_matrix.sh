#!/usr/bin/env bash
# Run backlog matrix experiment(s): B0–B5 (3×120s process + E2E).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

MATRIX_ROOT="${MATRIX_ROOT:-reports/poly_videos_mode_compare/experiments/backlog_matrix}"
PYTHON="${PYTHON:-python3}"

apply_env() {
  local exp="$1"
  unset EVILEYE_CONTROLLER_BACKPRESSURE EVILEYE_PIPELINE_SYNC_MP
  unset EVILEYE_PIPELINE_SYNC_MP_MS EVILEYE_MP_PENDING_CAP EVILEYE_MP_PENDING_CAP_TRACKER
  case "$exp" in
    B0)
      export EVILEYE_MP_QUEUE_SCALE=1
      export EVILEYE_MP_DRAIN_POLL_SEC=0.05
      ;;
    B1)
      export EVILEYE_MP_QUEUE_SCALE=1
      export EVILEYE_MP_DRAIN_POLL_SEC=0.01
      ;;
    B2)
      export EVILEYE_MP_QUEUE_SCALE=1
      export EVILEYE_MP_DRAIN_POLL_SEC=0.01
      export EVILEYE_CONTROLLER_BACKPRESSURE=1
      ;;
    B3)
      export EVILEYE_MP_QUEUE_SCALE=1
      export EVILEYE_MP_DRAIN_POLL_SEC=0.01
      export EVILEYE_PIPELINE_SYNC_MP=1
      export EVILEYE_PIPELINE_SYNC_MP_MS=8
      ;;
    B4)
      export EVILEYE_MP_QUEUE_SCALE=1
      export EVILEYE_MP_DRAIN_POLL_SEC=0.01
      export EVILEYE_CONTROLLER_BACKPRESSURE=1
      export EVILEYE_MP_PENDING_CAP=4
      export EVILEYE_MP_PENDING_CAP_TRACKER=4
      ;;
    B5)
      export EVILEYE_MP_QUEUE_SCALE=2
      export EVILEYE_MP_DRAIN_POLL_SEC=0.01
      ;;
    *)
      echo "Unknown experiment: $exp" >&2
      return 1
      ;;
  esac
}

write_env_json() {
  local exp_dir="$1"
  "$PYTHON" - <<'PY' "$exp_dir"
import json, os, sys
out = sys.argv[1]
keys = [
    "EVILEYE_MP_QUEUE_SCALE",
    "EVILEYE_MP_DRAIN_POLL_SEC",
    "EVILEYE_CONTROLLER_BACKPRESSURE",
    "EVILEYE_PIPELINE_SYNC_MP",
    "EVILEYE_PIPELINE_SYNC_MP_MS",
    "EVILEYE_MP_PENDING_CAP",
    "EVILEYE_MP_PENDING_CAP_TRACKER",
]
data = {k: os.environ.get(k, "") for k in keys}
with open(os.path.join(out, "env.json"), "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
PY
}

run_one() {
  local exp="$1"
  local root="$MATRIX_ROOT/$exp"
  mkdir -p "$root/logs" "$root/samples"
  apply_env "$exp"
  write_env_json "$root"
  echo "=== Running $exp ==="
  "$PYTHON" scripts/run_poly_videos_mode_compare.py \
    --configs poly-videos_opencv_process \
    --runs-per-config 3 \
    --timeout-sec 120 \
    --skip-warmup \
    --out-dir "$root"
  "$PYTHON" scripts/analyze_poly_mp_barriers.py --log-dir "$root/logs" --out-dir "$root"
  "$PYTHON" scripts/measure_poly_e2e_fps.py \
    --config configs/poly-videos.json \
    --warmup-sec 25 --active-sec 90 --env-note "$exp" \
    --out "$root/e2e_opencv_process.json"
  "$PYTHON" scripts/measure_poly_e2e_fps.py \
    --config configs/poly-videos-thread.json \
    --warmup-sec 25 --active-sec 90 --env-note "$exp" \
    --out "$root/e2e_opencv_thread.json"
  "$PYTHON" scripts/compare_poly_backlog_matrix.py --matrix-dir "$MATRIX_ROOT"
}

usage() {
  echo "Usage: $0 B1|B0|B2|B3|B4|B5|all" >&2
}

if [[ $# -lt 1 ]]; then
  usage
  exit 1
fi

target="${1}"
if [[ "$target" == "all" ]]; then
  for exp in B1 B0 B2 B3 B4 B5; do
    run_one "$exp"
  done
else
  run_one "$target"
fi

"$PYTHON" scripts/compare_poly_backlog_matrix.py --matrix-dir "$MATRIX_ROOT" --write-winner
