#!/usr/bin/env bash
# Automated web journal parity verification.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "== Unit tests =="
pytest \
  tests/unit/visualization/test_journal_media_resolver.py \
  tests/unit/api/test_journal_grouping.py \
  tests/unit/api/test_journal_routes.py \
  tests/unit/api/test_web_improvements.py \
  tests/integration/api/test_journals_smoke.py \
  -q --tb=short

echo "== TypeScript build =="
FRONTEND="$ROOT/evileye/api/frontend"
STATIC="$ROOT/evileye/api/static"
TSC="${TSC:-/tmp/package/lib/tsc.js}"
if [[ ! -f "$TSC" ]]; then
  echo "ERROR: tsc not found at $TSC (install typescript to /tmp/package first)"
  exit 1
fi
(cd "$FRONTEND" && node "$TSC")
cp "$FRONTEND/index.html" "$STATIC/index.html"
cp "$FRONTEND/styles/main.css" "$STATIC/main.css"
cp "$FRONTEND/styles/main.css" "$STATIC/styles/main.css"
for f in api dashboard journal-ui; do
  test -f "$STATIC/${f}.js" || { echo "Missing $STATIC/${f}.js"; exit 1; }
done

echo "== Static sanity =="
grep -q 'journal-tab-events' "$STATIC/index.html"
grep -q 'journal-detail-modal' "$STATIC/index.html"

echo "OK: web journals verification passed"
