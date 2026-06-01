#!/usr/bin/env bash
# Диагностика тормозов det-only: диск + опциональный запуск с логом.
# Использование: ./scripts/diag_det_only_slowdown.sh [--run]
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "=== iostat (5 samples, 2s interval) — запустите в другом терминале process.py с det-only ==="
if command -v iostat >/dev/null 2>&1; then
  iostat -xz 2 5 || true
else
  echo "iostat not found: sudo apt install sysstat"
fi

echo ""
echo "=== Запуск det-only с логом в /tmp/det-only-run.log (Ctrl+C для остановки) ==="
if [[ "${1:-}" == "--run" ]]; then
  python evileye/process.py --config configs/poly-videos-opencv-det-only.json --no-gui --autoclose 2>&1 | tee /tmp/det-only-run.log
  echo ""
  echo "=== Grep маркеров ==="
  grep -E "Waiting for|Pre-loading|Loading YOLO|is ready|did not become ready|Model pre-loading|All detectors" /tmp/det-only-run.log || true
fi
