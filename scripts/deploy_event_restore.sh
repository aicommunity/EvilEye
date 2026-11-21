#!/usr/bin/env bash
# Deploy an already-tested revision using Git; site configuration is kept in place.
set -euo pipefail
REPO="${1:?repository path required}"
SITE="${2:?site path required}"
REVISION="${3:?tested Git revision required}"
cd "$REPO"
git diff --quiet
git diff --cached --quiet
git fetch origin codex/restore-zone-events
TARGET="$(git rev-parse "$REVISION^{commit}")"
git merge-base --is-ancestor "$TARGET" origin/codex/restore-zone-events
PREVIOUS="$(git rev-parse HEAD)"
CONFIG_HASH="$(sha256sum "$SITE/configs/poly-cameras-gst.json" | cut -d' ' -f1)"
systemctl --user stop evileye-watchdog.timer evileye-event-health.timer 2>/dev/null || true
rollback() {
    local status=$?
    if (( status != 0 )); then
        echo "Deployment failed; restoring Git revision $PREVIOUS" >&2
        systemctl --user stop evileye.service evileye-run-poly-cameras-gst.scope 2>/dev/null || true
        git checkout --detach "$PREVIOUS"
        systemctl --user start evileye.service
        systemctl --user start evileye-watchdog.timer
    fi
    exit "$status"
}
trap rollback EXIT
if systemctl --user is-active --quiet evileye-run-poly-cameras-gst.scope; then
    systemctl --user stop evileye-run-poly-cameras-gst.scope
fi
systemctl --user stop evileye.service
if git show-ref --verify --quiet refs/heads/codex/restore-zone-events; then
    git switch codex/restore-zone-events
    git merge --ff-only "$TARGET"
else
    git switch -c codex/restore-zone-events "$TARGET"
fi
test "$(git rev-parse HEAD)" = "$TARGET"
test "$(sha256sum "$SITE/configs/poly-cameras-gst.json" | cut -d' ' -f1)" = "$CONFIG_HASH"
systemctl --user start evileye.service
for attempt in $(seq 1 90); do
    if python3 - "$SITE" "$TARGET" <<'PY'
import json, sys, time
from pathlib import Path
p = Path(sys.argv[1])/'monitor/event_heartbeat.json'
try:
    state = json.loads(p.read_text())
    assert time.time()-state['updated_at'] < 15
    assert state['identity']['git_sha'] == sys.argv[2]
    assert not state['failures'], state['failures']
except (OSError, ValueError, KeyError, AssertionError):
    raise SystemExit(1)
PY
    then
        DEPLOY_DIR="$SITE" CONFIG_NAME=poly-cameras-gst.json bash "$REPO/evileye/deploy_monitor/scripts/install_timer.sh"
        echo "Deployed $TARGET; configuration SHA256=$CONFIG_HASH"
        trap - EXIT
        exit 0
    fi
    sleep 2
done
echo 'No healthy event heartbeat appeared within 180 seconds' >&2
exit 1
