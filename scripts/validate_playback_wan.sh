#!/usr/bin/env bash
# Run playback WAN + cache diagnostics (lab). See docs/PLAYBACK_WAN_TESTING.md
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

OUT_DIR="${WAN_REPORT_DIR:-/tmp/evileye_wan_reports}"
mkdir -p "$OUT_DIR"
TS="$(date +%Y%m%d_%H%M%S)"

echo "==> Ensure test user"
python3 scripts/ensure_playback_test_user.py || true

echo "==> Server probe (all scenarios)"
PROBE_JSON="$OUT_DIR/probe_${TS}.json"
python3 scripts/diagnose_playback_wan.py --scenario all --output "$PROBE_JSON" || true

echo "==> E2E WAN diagnostics (lan)"
export E2E_NETWORK_PROFILE="${E2E_NETWORK_PROFILE:-lan}"
E2E_WAN_JSON="$OUT_DIR/e2e_wan_${TS}.json"
npx playwright test tests/e2e/playback_wan_diagnostics.spec.ts --reporter=json > "$E2E_WAN_JSON" 2>/dev/null || true

echo "==> E2E cache diagnostics"
E2E_CACHE_JSON="$OUT_DIR/e2e_cache_${TS}.json"
npx playwright test tests/e2e/playback_cache_diagnostics.spec.ts --reporter=json > "$E2E_CACHE_JSON" 2>/dev/null || true

REPORT_MD="$OUT_DIR/report_${TS}.md"
python3 scripts/report_playback_wan.py \
  --probe "$PROBE_JSON" \
  --e2e-wan "$E2E_WAN_JSON" \
  --e2e-cache "$E2E_CACHE_JSON" \
  --output "$REPORT_MD"

echo "Reports:"
echo "  $PROBE_JSON"
echo "  $E2E_WAN_JSON"
echo "  $E2E_CACHE_JSON"
echo "  $REPORT_MD"
