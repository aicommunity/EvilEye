#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-venv/bin/python}"
BASE_CONFIG="${BASE_CONFIG:-configs/multi_videos.json}"
CONFIG_OUT="${CONFIG_OUT:-reports/linux_perf_matrix/configs}"
MATRIX_MANIFEST="${MATRIX_MANIFEST:-${CONFIG_OUT}/matrix_manifest.json}"
SUMMARY_OUT="${SUMMARY_OUT:-reports/linux_perf_matrix/summary}"

MAX_CAMERAS="${MAX_CAMERAS:-4}"
TARGET_FPS="${TARGET_FPS:-30}"
DETECTION_THREADS="${DETECTION_THREADS:-1}"
DURATION_SEC="${DURATION_SEC:-90}"
WARMUP_DURATION_SEC="${WARMUP_DURATION_SEC:-20}"
TIMEOUT_SEC="${TIMEOUT_SEC:-600}"
DURATION_STOP_GRACE_SEC="${DURATION_STOP_GRACE_SEC:-30}"
SAMPLE_INTERVAL_SEC="${SAMPLE_INTERVAL_SEC:-2}"
PERF_EVERY="${PERF_EVERY:-30}"
WARMUP="${WARMUP:-1}"
RENDER_EACH="${RENDER_EACH:-1}"

export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-offscreen}"
export PYTHONUNBUFFERED=1

prepare_args=(
  scripts/prepare_linux_perf_matrix.py
  --base-config "${BASE_CONFIG}"
  --out-dir "${CONFIG_OUT}"
  --max-cameras "${MAX_CAMERAS}"
  --repeat-cameras
  --target-fps "${TARGET_FPS}"
  --num-detection-threads "${DETECTION_THREADS}"
)

if [[ -n "${DEVICES:-}" ]]; then
  prepare_args+=(--devices ${DEVICES})
fi
if [[ -n "${SCENARIOS:-}" ]]; then
  prepare_args+=(--scenarios ${SCENARIOS})
fi
if [[ -n "${LAYOUTS:-}" ]]; then
  prepare_args+=(--layouts ${LAYOUTS})
fi
if [[ "${ALLOW_MISSING:-0}" == "1" ]]; then
  prepare_args+=(--allow-missing)
fi

"${PYTHON_BIN}" "${prepare_args[@]}"

RUN_LIST="$(mktemp)"
trap 'rm -f "${RUN_LIST}"' EXIT
"${PYTHON_BIN}" - "${MATRIX_MANIFEST}" > "${RUN_LIST}" <<'PY'
import json
import sys

matrix = json.load(open(sys.argv[1], encoding="utf-8"))
for item in matrix["runs"]:
    print(f"{item['device']}\t{item['manifest']}\t{item['result_dir']}")
PY

while IFS=$'\t' read -r device manifest result_dir; do
  echo "==> ${device}: ${manifest}"

  if [[ "${device}" == cpu ]]; then
    export CUDA_VISIBLE_DEVICES=""
  else
    export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"
  fi

  if [[ "${WARMUP}" == "1" ]]; then
    "${PYTHON_BIN}" scripts/run_multiprocessing_benchmark.py \
      --manifest "${manifest}" \
      --out-dir "${result_dir}_warmup" \
      --camera-counts 1 \
      --modes thread process \
      --duration-sec "${WARMUP_DURATION_SEC}" \
      --timeout-sec "${TIMEOUT_SEC}" \
      --duration-hard-stop \
      --duration-stop-grace-sec "${DURATION_STOP_GRACE_SEC}" \
      --sample-interval-sec "${SAMPLE_INTERVAL_SEC}" \
      --perf-every "${PERF_EVERY}" \
      --no-autoclose \
      --python "${PYTHON_BIN}" || true
  fi

  "${PYTHON_BIN}" scripts/run_multiprocessing_benchmark.py \
    --manifest "${manifest}" \
    --out-dir "${result_dir}" \
    --camera-counts 1 2 3 4 \
    --modes thread process \
    --duration-sec "${DURATION_SEC}" \
    --timeout-sec "${TIMEOUT_SEC}" \
    --duration-hard-stop \
    --duration-stop-grace-sec "${DURATION_STOP_GRACE_SEC}" \
    --sample-interval-sec "${SAMPLE_INTERVAL_SEC}" \
    --perf-every "${PERF_EVERY}" \
    --no-autoclose \
    --python "${PYTHON_BIN}"

  if [[ "${RENDER_EACH}" == "1" ]]; then
    "${PYTHON_BIN}" scripts/render_multiprocessing_benchmark_report.py \
      --out-dir "${result_dir}" \
      --warmup-windows 1
  fi
done < "${RUN_LIST}"

"${PYTHON_BIN}" scripts/render_linux_perf_matrix_report.py \
  --matrix-manifest "${MATRIX_MANIFEST}" \
  --out-dir "${SUMMARY_OUT}" \
  --warmup-windows 1
