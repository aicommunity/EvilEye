#!/usr/bin/env bash
# Long-run MP memory soak: log RSS periodically (MEM-4 gate).
set -euo pipefail

CONFIG="${1:-configs/poly-videos.json}"
DURATION_SEC="${SOAK_DURATION_SEC:-1800}"
INTERVAL_SEC="${SOAK_RSS_INTERVAL_SEC:-60}"
PIDFILE="${SOAK_PIDFILE:-/tmp/evileye_soak.pid}"
LOG="${SOAK_LOG:-reports/soak_mp_rss.log}"

mkdir -p "$(dirname "$LOG")"
echo "# soak started $(date -Is) config=$CONFIG duration=${DURATION_SEC}s" | tee -a "$LOG"

evileye run "$CONFIG" --no-gui &
EPID=$!
echo "$EPID" > "$PIDFILE"
echo "pid=$EPID" | tee -a "$LOG"

end=$((SECONDS + DURATION_SEC))
while (( SECONDS < end )); do
  if ! kill -0 "$EPID" 2>/dev/null; then
    echo "process exited early at $(date -Is)" | tee -a "$LOG"
    break
  fi
  rss_kb=$(ps -o rss= -p "$EPID" 2>/dev/null | tr -d ' ' || echo 0)
  echo "$(date -Is) rss_kb=$rss_kb" | tee -a "$LOG"
  sleep "$INTERVAL_SEC"
done

kill "$EPID" 2>/dev/null || true
wait "$EPID" 2>/dev/null || true
rm -f "$PIDFILE"
echo "# soak finished $(date -Is)" | tee -a "$LOG"
