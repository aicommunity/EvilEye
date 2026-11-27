"""Process identity and safe diagnostics shared by API and pipeline workers."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

_STARTED_AT = time.time()
_IDENTITY = None
_SECRET_KEY = re.compile(r'password|passwd|secret|token|credential', re.I)
_URL_AUTH = re.compile(r'(\w+://)[^\s/@]+(?::[^\s/@]*)?@')


def redact(value):
    if isinstance(value, dict):
        return {str(k): '[redacted]' if _SECRET_KEY.search(str(k)) else redact(v)
                for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    if isinstance(value, str):
        value = _URL_AUTH.sub(r'\1[redacted]@', value)
        return re.sub(r'(?i)((?:password|passwd|token|secret)=)[^\s&;]+', r'\1[redacted]', value)
    return value


def process_identity(config=None):
    global _IDENTITY
    if _IDENTITY is None:
        import evileye
        package_path = Path(evileye.__file__).resolve()
        revision, commit_time = None, None
        try:
            result = subprocess.run(
                ['git', '-C', str(package_path.parent.parent), 'show', '-s', '--format=%H%n%cI', 'HEAD'],
                capture_output=True, text=True, timeout=3, check=True)
            revision, commit_time = result.stdout.strip().splitlines()
        except (OSError, subprocess.SubprocessError, ValueError):
            pass
        try:
            import psutil
            started_at = psutil.Process().create_time()
        except (ImportError, OSError):
            started_at = _STARTED_AT
        _IDENTITY = dict(pid=os.getpid(), git_sha=os.getenv('EVILEYE_BUILD_SHA') or revision,
                         build_time=os.getenv('EVILEYE_BUILD_TIME') or commit_time, source_commit_time=commit_time,
                         started_at=started_at, package_path=str(package_path))
    result = dict(_IDENTITY)
    result['config_sha256'] = hashlib.sha256(json.dumps(
        config or {}, sort_keys=True, separators=(',', ':'), default=str).encode()).hexdigest()
    return result


def event_health(stats, *, now=None):
    """Idle event streams are healthy; stopped or stalled required workers are not."""
    now = time.time() if now is None else now
    reasons = []
    components = stats.get('components') or {}
    for name in ('events_controller', 'events_processor'):
        component = components.get(name)
        if not isinstance(component, dict):
            reasons.append(name + ':missing')
            continue
        if component.get('worker_alive') is False:
            reasons.append(name + ':worker_stopped')
        last = component.get('last_success_at')
        if last is not None and now - last > 30:
            reasons.append(name + ':heartbeat_stale')
    for name, detector in (components.get('events_controller', {}).get('detectors') or {}).items():
        if detector.get('started') and not detector.get('worker_running'):
            reasons.append(name + ':worker_stopped')
        submitted = detector.get('updates_submitted', 0)
        completed = detector.get('updates_completed', 0)
        last = detector.get('last_success_at') or detector.get('started_at')
        if submitted > completed and last is not None and now - last > 30:
            reasons.append(name + ':updates_stalled')
    capture_names = []
    down_names = []
    for name, source in (components.get('pipeline', {}).get('module_instances') or {}).items():
        if not isinstance(source, dict) or 'capture_health' not in source:
            continue
        health = source.get('capture_health') or {}
        capture_names.append(name)
        pending = health.get('teardown_pending_since')
        if pending is not None and now-pending > 30:
            reasons.append(name + ':native_teardown_stalled')
        down_since = health.get('capture_down_since')
        if (
            health.get('working') is False
            and isinstance(down_since, (int, float))
            and now - down_since > 120
        ):
            reasons.append(name + ':source_down')
            down_names.append(name)
    if capture_names and len(down_names) == len(capture_names):
        reasons.append('capture:all_sources_down')
    return reasons


def capture_outage_restarts_pipeline(reasons) -> bool:
    """One live camera must keep recording. Restart only when every capture is down
    or the failure is not a partial source outage."""
    cleaned = []
    for reason in reasons or []:
        text = str(reason).strip()
        if text.startswith('event_health:'):
            text = text[len('event_health:'):]
        if text:
            cleaned.extend(part for part in text.split(';') if part)
    if not cleaned:
        return False
    if 'capture:all_sources_down' in cleaned:
        return True
    return any(not item.endswith(':source_down') for item in cleaned)


def publish_heartbeat(site_dir, stats):
    path = Path(site_dir) / 'monitor' / 'event_heartbeat.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(pid=os.getpid(), updated_at=time.time(),
                   failures=event_health(stats), identity=stats.get('identity'),
                   components={k: v for k, v in stats.get('components', {}).items()
                               if k in ('events_controller', 'events_processor')})
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(redact(payload), default=str), encoding='utf-8')
    temporary.replace(path)
