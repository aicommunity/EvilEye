"""Check the event heartbeat without importing inference libraries."""
import json
import sys
import time
from pathlib import Path


def evaluate(payload, pid, state, now):
    if state.get('pid') != pid:
        state = {'pid': pid, 'streak': 0, 'first_seen_at': now}
    reasons = []
    if not payload or payload.get('pid') != pid:
        if now - state['first_seen_at'] > 90:
            reasons = ['heartbeat_missing']
    elif now - payload.get('updated_at', 0) > 30:
        reasons = ['heartbeat_stale']
    else:
        reasons = payload.get('failures') or []
    if now - state.get('checked_at', 0) >= 9:
        state['streak'] = state.get('streak', 0) + 1 if reasons else 0
        state['checked_at'] = now
    stopped = any('worker_stopped' in reason for reason in reasons)
    failed = stopped or bool(reasons and state.get('streak', 0) >= 3)
    return state, ';'.join(reasons) if failed else ''


def main():
    site, pid = Path(sys.argv[1]), int(sys.argv[2])
    monitor = site / 'monitor'
    state_path = monitor / '.event_health_state.json'
    def read(path):
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return {}
    state, reason = evaluate(read(monitor / 'event_heartbeat.json'), pid,
                             read(state_path), time.time())
    monitor.mkdir(parents=True, exist_ok=True)
    temporary = state_path.with_suffix('.tmp')
    temporary.write_text(json.dumps(state), encoding='utf-8')
    temporary.replace(state_path)
    if reason:
        print('event_health:' + reason)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
