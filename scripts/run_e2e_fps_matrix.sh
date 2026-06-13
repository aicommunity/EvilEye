#!/usr/bin/env bash
# E2E FPS matrix F0–F7 (3×120s process + E2E 90s).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

MATRIX_ROOT="${MATRIX_ROOT:-reports/poly_videos_mode_compare/experiments/e2e_fps_matrix}"
PYTHON="${PYTHON:-python3}"

apply_env() {
  local exp="$1"
  unset EVILEYE_CONTROLLER_BACKPRESSURE EVILEYE_PIPELINE_SYNC_MP
  unset EVILEYE_PIPELINE_SYNC_MP_MS EVILEYE_SYNC_MP_PENDING_MAX
  unset EVILEYE_MP_PENDING_CAP EVILEYE_MP_PENDING_CAP_TRACKER
  unset EVILEYE_MP_DRAIN_MAX_ITEMS
  export EVILEYE_MP_QUEUE_SCALE=1
  case "$exp" in
    F0)
      export EVILEYE_MP_DRAIN_POLL_SEC=0.01
      export EVILEYE_PIPELINE_SYNC_MP=1
      export EVILEYE_PIPELINE_SYNC_MP_MS=8
      ;;
    F1)
      export EVILEYE_MP_DRAIN_POLL_SEC=0.01
      ;;
    F2)
      export EVILEYE_MP_DRAIN_POLL_SEC=0.01
      export EVILEYE_CONTROLLER_BACKPRESSURE=soft
      ;;
    F3)
      export EVILEYE_MP_DRAIN_POLL_SEC=0.005
      export EVILEYE_CONTROLLER_BACKPRESSURE=soft
      ;;
    F4)
      export EVILEYE_MP_DRAIN_POLL_SEC=0.01
      export EVILEYE_CONTROLLER_BACKPRESSURE=soft
      export EVILEYE_PIPELINE_SYNC_MP=adaptive
      export EVILEYE_PIPELINE_SYNC_MP_MS=8
      export EVILEYE_SYNC_MP_PENDING_MAX=10
      ;;
    F5)
      export EVILEYE_MP_DRAIN_POLL_SEC=0.01
      export EVILEYE_CONTROLLER_BACKPRESSURE=soft
      export EVILEYE_PIPELINE_SYNC_MP=1
      export EVILEYE_PIPELINE_SYNC_MP_MS=3
      ;;
    F6)
      export EVILEYE_MP_DRAIN_POLL_SEC=0.01
      export EVILEYE_CONTROLLER_BACKPRESSURE=soft
      export EVILEYE_MP_DRAIN_MAX_ITEMS=128
      ;;
    F7)
      export EVILEYE_MP_DRAIN_POLL_SEC=0.01
      export EVILEYE_CONTROLLER_BACKPRESSURE=soft
      export EVILEYE_PIPELINE_SYNC_MP=adaptive
      export EVILEYE_PIPELINE_SYNC_MP_MS=8
      export EVILEYE_SYNC_MP_PENDING_MAX=10
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
    "EVILEYE_SYNC_MP_PENDING_MAX",
    "EVILEYE_MP_DRAIN_MAX_ITEMS",
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
  "$PYTHON" scripts/compare_poly_e2e_fps_matrix.py --matrix-dir "$MATRIX_ROOT"
}

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 F1|F2|...|F7|all|quick" >&2
  exit 1
fi

target="${1}"
if [[ "$target" == "all" ]]; then
  for exp in F1 F2 F3 F4 F5 F6 F0; do
    run_one "$exp"
  done
elif [[ "$target" == "quick" ]]; then
  for exp in F1 F2 F4; do
    run_one "$exp"
  done
else
  run_one "$target"
fi

"$PYTHON" scripts/compare_poly_e2e_fps_matrix.py --matrix-dir "$MATRIX_ROOT" --write-winner
