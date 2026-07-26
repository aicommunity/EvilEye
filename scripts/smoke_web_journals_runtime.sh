#!/usr/bin/env bash
# Optional runtime smoke against a running EvilEye API (default http://127.0.0.1:8181).
set -euo pipefail

BASE_URL="${EVILEYE_API_URL:-http://127.0.0.1:8181}"
API="${BASE_URL}/api/v1"
CJ="${EVILEYE_SMOKE_COOKIE_JAR:-/tmp/evileye_smoke_cj}"
USER="${EVILEYE_WEB_USER:-admin}"
PASS="${EVILEYE_WEB_PASS:-admin}"

curl -fsS "${BASE_URL}/ready" >/dev/null

AUTH=()
if ! curl -fsS "${API}/journals/filters/meta" >/dev/null 2>&1; then
  curl -fsS -c "$CJ" -X POST "${API}/auth/login" \
    -H 'Content-Type: application/json' \
    -d "{\"username\":\"${USER}\",\"password\":\"${PASS}\"}" >/dev/null
  AUTH=(-b "$CJ")
fi

curl -fsS "${AUTH[@]}" "${API}/journals/filters/meta" >/dev/null
curl -fsS "${AUTH[@]}" "${API}/journals/events/grouped?page=0&size=5" >/dev/null
curl -fsS "${AUTH[@]}" "${API}/journals/objects/grouped?page=0&size=5" >/dev/null
curl -fsS "${AUTH[@]}" "${API}/journals/stats?date=today" >/dev/null

echo "OK: runtime journal smoke passed (${BASE_URL})"
