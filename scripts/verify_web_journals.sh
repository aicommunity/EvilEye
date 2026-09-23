#!/usr/bin/env bash
# Automated web journals + Vite SPA verification (audit A13).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "== Unit tests =="
pytest \
  tests/unit/visualization/test_journal_media_resolver.py \
  tests/unit/api/test_journal_grouping.py \
  tests/unit/api/test_journal_merge_logic.py \
  tests/unit/api/test_journal_routes.py \
  tests/unit/api/test_web_improvements.py \
  tests/unit/api/test_playback_memory_cache.py \
  tests/unit/api/test_playback_route_timeouts.py \
  tests/unit/api/test_playback_media_acl.py \
  tests/unit/api/test_reaudit_media_acl.py \
  tests/unit/api/test_reaudit_event_singleflight.py \
  tests/unit/api/test_reaudit_detection_ticks_freshness.py \
  tests/unit/api/test_reaudit_cache_stale.py \
  tests/unit/api/test_reaudit_state_queue_deadline.py \
  tests/unit/api/test_playback_events_acl.py \
  tests/unit/api/test_live_preview_acl.py \
  tests/integration/api/test_journals_smoke.py \
  -q --tb=short

FRONTEND="$ROOT/evileye/api/frontend"
STATIC="$ROOT/evileye/api/static"

echo "== Frontend npm ci / test / build =="
if ! command -v npm >/dev/null 2>&1; then
  echo "ERROR: npm is required"
  exit 1
fi
(cd "$FRONTEND" && npm ci && npm test && npm run build)

echo "== Static SPA sanity =="
test -f "$STATIC/index.html" || { echo "Missing $STATIC/index.html"; exit 1; }
shopt -s nullglob
assets=( "$STATIC"/assets/index-*.js )
if [[ ${#assets[@]} -lt 1 ]]; then
  echo "ERROR: expected $STATIC/assets/index-*.js after Vite build"
  exit 1
fi
grep -E 'assets/index-' "$STATIC/index.html" >/dev/null \
  || { echo "ERROR: index.html does not reference assets/index-*"; exit 1; }

echo "OK: web journals + Vite SPA verification passed"
