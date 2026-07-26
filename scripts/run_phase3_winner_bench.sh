#!/usr/bin/env bash
# Final 5×180 bench using e2e_fps_matrix WINNER env.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

MATRIX_ROOT="${MATRIX_ROOT:-reports/poly_videos_mode_compare/experiments/e2e_fps_matrix}"
OUT_DIR="${OUT_DIR:-reports/poly_videos_mode_compare/phase3_final}"
PYTHON="${PYTHON:-python3}"
WINNER_FILE="$MATRIX_ROOT/WINNER.txt"

if [[ ! -f "$WINNER_FILE" ]]; then
  echo "WINNER.txt not found. Run: ./scripts/run_e2e_fps_matrix.sh all" >&2
  exit 1
fi

EXP="$(head -n1 "$WINNER_FILE" | tr -d '[:space:]')"
ENV_JSON="$MATRIX_ROOT/$EXP/env.json"
if [[ ! -f "$ENV_JSON" ]]; then
  echo "Missing $ENV_JSON for winner $EXP" >&2
  exit 1
fi

echo "Winner experiment: $EXP"
"$PYTHON" - <<'PY' "$ENV_JSON"
import json, os, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
for k, v in data.items():
    if v:
        os.environ[k] = str(v)
    else:
        os.environ.pop(k, None)
for k in sorted(data):
    print(f"  {k}={os.environ.get(k, '')}")
PY

mkdir -p "$OUT_DIR/logs" "$OUT_DIR/samples"
"$PYTHON" scripts/run_poly_videos_mode_compare.py \
  --timeout-sec 180 --runs-per-config 5 --skip-warmup \
  --out-dir "$OUT_DIR"

# collect_poly_mode_output_snapshot uses DEFAULT_OUT_DIR only; skip for phase3_final
"$PYTHON" scripts/analyze_poly_mp_barriers.py --log-dir "$OUT_DIR/logs" --out-dir "$OUT_DIR"
"$PYTHON" scripts/measure_poly_e2e_fps.py \
  --config configs/poly-videos.json \
  --warmup-sec 25 --active-sec 90 --env-note "winner_${EXP}" \
  --out "$OUT_DIR/e2e_opencv_process.json"
"$PYTHON" scripts/measure_poly_e2e_fps.py \
  --config configs/poly-videos-thread.json \
  --warmup-sec 25 --active-sec 90 --env-note "winner_${EXP}" \
  --out "$OUT_DIR/e2e_opencv_thread.json"
"$PYTHON" scripts/render_poly_videos_mode_report.py \
  --out-dir "$OUT_DIR"

"$PYTHON" scripts/compare_poly_bench_runs.py \
  --baseline-dir reports/poly_videos_mode_compare/baseline_pre_fix \
  --current-dir "$OUT_DIR" \
  --out docs/mp_fps_phase3_summary.md

echo "Done. Winner=$EXP OUT=$OUT_DIR"
