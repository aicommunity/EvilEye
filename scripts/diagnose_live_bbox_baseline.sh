#!/usr/bin/env bash
# Capture baseline metrics for Live bbox / RAM investigations.
set -euo pipefail

OUT_DIR="${1:-/home/user/EvilEyeDeploy/logs}"
mkdir -p "$OUT_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"
OUT="$OUT_DIR/live_bbox_baseline_${STAMP}.txt"

{
  echo "=== EvilEye Live bbox baseline ${STAMP} ==="
  echo
  echo "## Pipeline process"
  PID="$(pgrep -f 'poly-cameras-gst.json' | head -1 || true)"
  echo "PID=${PID:-none}"
  if [[ -n "${PID:-}" ]]; then
    ps -p "$PID" -o pid,rss,vsz,%mem,etime,cmd || true
    grep -E 'VmRSS|VmHWM|Threads' "/proc/$PID/status" 2>/dev/null || true
  fi
  echo
  echo "## /ready"
  curl -sS 'http://127.0.0.1:8181/ready' | python3 -m json.tool 2>/dev/null || curl -sS 'http://127.0.0.1:8181/ready' || true
  echo
  echo "## Top evileye memory"
  ps aux --sort=-%mem | grep -E 'evileye|det-mp|tracker' | head -15 || true
} | tee "$OUT"

echo "Wrote $OUT"
