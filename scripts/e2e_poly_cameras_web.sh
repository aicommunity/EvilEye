#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CONFIG="$ROOT/configs/poly-cameras.json"
BASE="${EVILEYE_API_URL:-http://127.0.0.1:8181}"
API="$BASE/api/v1"
IMAGE_DIR="${EVILEYE_IMAGE_DIR:-/media/user/Data8/EvilEyeData}"
TODAY="$(date +%F)"
WAIT_SEC="${E2E_EVENT_WAIT_SEC:-300}"

# Pre-flight
test -f "$CONFIG"
test -d "$IMAGE_DIR" || { echo "FAIL: image_dir missing: $IMAGE_DIR"; exit 1; }
curl -fsS "$BASE/ready" >/dev/null

# Baseline event count (JSON fallback path or API total)
BASELINE="$(curl -fsS "$API/journals/events/grouped?page=0&size=1&date=$TODAY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('total',0))")"
echo "Baseline events today: $BASELINE"

# Monitor loop (assumes evileye run already started by agent)
END=$((SECONDS+WAIT_SEC))
while (( SECONDS < END )); do
  CUR="$(curl -fsS "$API/journals/events/grouped?page=0&size=1&date=$TODAY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('total',0))")"
  ZONE_JSON="$IMAGE_DIR/Events/$TODAY/Metadata/zone_events_entered.json"
  if [[ -f "$ZONE_JSON" ]]; then
    LAST_TS="$(python3 -c "import json; d=json.load(open('$ZONE_JSON')); print(d[-1]['ts'] if d else '')")"
    MTIME="$(stat -c %Y "$ZONE_JSON")"
    NOW="$(date +%s)"
    AGE=$((NOW-MTIME))
    COUNT="$(python3 -c "import json; d=json.load(open('$ZONE_JSON')); print(len(d))")"
    echo "zone_events: count=${COUNT} last_ts=$LAST_TS file_age_sec=$AGE cur_total=$CUR"
    if (( CUR > BASELINE )) && (( AGE < 120 )); then
      echo "OK: new events written"
      exit 0
    fi
  fi
  sleep 10
done
echo "FAIL: no new events within ${WAIT_SEC}s"
exit 1
