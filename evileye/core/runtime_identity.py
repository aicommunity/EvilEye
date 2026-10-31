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
    for name, source in (components.get('pipeline', {}).get('module_instances') or {}).items():
        health = source.get('capture_health') or {}
        pending = health.get('teardown_pending_since')
        if pending is not None and now-pending > 30:
            reasons.append(name + ':native_teardown_stalled')
    return reasons


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
