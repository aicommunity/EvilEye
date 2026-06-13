#!/usr/bin/env bash
# Optional runtime smoke against a running EvilEye API (default http://127.0.0.1:8181).
set -euo pipefail

BASE_URL="${EVILEYE_API_URL:-http://127.0.0.1:8181}"
API="${BASE_URL}/api/v1"

curl -fsS "${API}/journals/filters/meta" >/dev/null
curl -fsS "${API}/journals/events/grouped?page=0&size=5" >/dev/null
curl -fsS "${API}/journals/objects/grouped?page=0&size=5" >/dev/null

echo "OK: runtime journal smoke passed (${BASE_URL})"
