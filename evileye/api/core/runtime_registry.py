import json
import os
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Iterable, Optional

from evileye.core.logger import get_module_logger

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX fallback
    fcntl = None

logger = get_module_logger("api.runtime_registry")

RUNTIME_ROOT = Path(tempfile.gettempdir()) / "evileye_runtime"
REGISTRY_DIR = RUNTIME_ROOT / "pipelines"
SNAPSHOT_DIR = RUNTIME_ROOT / "snapshots"
LOCK_FILE = RUNTIME_ROOT / ".lock"
_corrupt_record_logged: set[int] = set()
_corrupt_snapshot_logged: set[int] = set()
_last_discover_ts: float = 0.0
_DISCOVER_MIN_INTERVAL_SEC = 5.0
_STUB_FIELDS = (
    "id",
    "pid",
    "state",
    "alive",
    "updated_at",
    "stopped_at",
    "started_at",
    "config_path",
    "name",
    "source",
    "managed",
    "frame_dir",
    "error",
    "log_session_id",
)

def _ensure_dirs() -> None:
    REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)


def _record_path(rid: int) -> Path:
    _ensure_dirs()
    return REGISTRY_DIR / f"{int(rid)}.json"


def _snapshot_path(rid: int) -> Path:
    _ensure_dirs()
    return SNAPSHOT_DIR / f"{int(rid)}.json"


def _atomic_write_text(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` via temp file + ``os.replace`` (atomic on POSIX)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _is_pid_alive(pid: Optional[int]) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        os.kill(int(pid), 0)
    except OSError:
        return False
    return True


@contextmanager
def _registry_lock():
    _ensure_dirs()
    with open(LOCK_FILE, "a+", encoding="utf-8") as handle:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def allocate_pipeline_id(extra_ids: Optional[Iterable[int]] = None) -> int:
    extra_set = {int(v) for v in (extra_ids or [])}
    with _registry_lock():
        known_ids = set(extra_set)
        for path in REGISTRY_DIR.glob("*.json"):
            try:
                known_ids.add(int(path.stem))
            except ValueError:
                continue
        next_id = (max(known_ids) + 1) if known_ids else 1
        return next_id


def _parse_process_cmdline(pid: int) -> Optional[dict]:
    proc_dir = Path("/proc") / str(pid)
    try:
        raw_cmdline = (proc_dir / "cmdline").read_bytes()
        parts = [p.decode("utf-8", errors="ignore") for p in raw_cmdline.split(b"\0") if p]
    except Exception:
        return None
    if not parts:
        return None
    joined = " ".join(parts)
    if "evileye/process.py" not in joined:
        return None
    config_path = None
    for idx, part in enumerate(parts[:-1]):
        if part == "--config":
            config_path = parts[idx + 1]
            break
    if not config_path:
        return None
    env: dict[str, str] = {}
    try:
        raw_env = (proc_dir / "environ").read_bytes().split(b"\0")
        for item in raw_env:
            if b"=" not in item:
                continue
            key, value = item.split(b"=", 1)
            env[key.decode("utf-8", errors="ignore")] = value.decode("utf-8", errors="ignore")
    except Exception:
        pass
    return {
        "pid": pid,
        "config_path": config_path,
        "pipeline_id": env.get("EVILEYE_PIPELINE_ID"),
        "frame_dir": env.get("EVILEYE_FRAME_DIR"),
        "name": env.get("EVILEYE_PIPELINE_NAME"),
        "managed": env.get("EVILEYE_MANAGED_RUN") == "1",
    }


def discover_process_runtimes() -> None:
    global _last_discover_ts
    _ensure_dirs()
    known_by_pid: dict[int, int] = {}
    for path in REGISTRY_DIR.glob("*.json"):
        try:
            rid = int(path.stem)
        except ValueError:
            continue
        record = load_runtime_record(rid, refresh_state=False)
        if record and record.get("pid"):
            known_by_pid[int(record["pid"])] = rid
    for proc_dir in Path("/proc").iterdir():
        if not proc_dir.name.isdigit():
            continue
        pid = int(proc_dir.name)
        info = _parse_process_cmdline(pid)
        if not info:
            continue
        rid_raw = info.get("pipeline_id")
        if rid_raw:
            rid = int(rid_raw)
        elif pid in known_by_pid:
            rid = known_by_pid[pid]
        else:
            rid = allocate_pipeline_id()
        config_path = str(Path(info["config_path"]).resolve())
        frame_dir = info.get("frame_dir")
        if not frame_dir:
            candidate = Path(tempfile.gettempdir()) / "evileye_frames" / str(rid)
            frame_dir = str(candidate) if candidate.exists() else None
        register_runtime(
            rid=rid,
            pid=pid,
            config_path=config_path,
            name=info.get("name") or Path(config_path).stem,
            frame_dir=frame_dir,
            source="process",
            managed=bool(info.get("managed")),
            state="running",
        )
    _last_discover_ts = time.time()


def maybe_discover_process_runtimes(*, force: bool = False) -> None:
    """Throttle /proc discovery so hot UI polls do not rescan every request."""
    global _last_discover_ts
    now = time.time()
    if not force and (now - _last_discover_ts) < _DISCOVER_MIN_INTERVAL_SEC:
        return
    discover_process_runtimes()

def load_runtime_record(rid: int, *, refresh_state: bool = True) -> Optional[Dict]:
    path = _record_path(rid)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        rid_int = int(rid)
        if rid_int not in _corrupt_record_logged:
            logger.warning("Failed to read runtime record %s: %s", path, exc)
            _corrupt_record_logged.add(rid_int)
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass
        return None
    _corrupt_record_logged.discard(int(rid))
    if refresh_state:
        data = refresh_runtime_record(data)
    return data


def refresh_runtime_record(data: Dict) -> Dict:
    record = dict(data)
    pid = record.get("pid")
    alive = _is_pid_alive(pid)
    record["alive"] = alive
    if alive:
        if record.get("state") not in {"running", "starting"}:
            record["state"] = "running"
    elif record.get("state") in {"running", "starting", "stopping"}:
        record["state"] = "stopped"
        record["pid"] = None
        record["stopped_at"] = record.get("stopped_at") or time.time()
    return record


def save_runtime_record(record: Dict) -> Dict:
    _ensure_dirs()
    normalized = refresh_runtime_record(record)
    normalized["id"] = int(normalized["id"])
    normalized.setdefault("updated_at", time.time())
    payload = json.dumps(normalized, ensure_ascii=False, indent=2)
    with _registry_lock():
        _atomic_write_text(_record_path(normalized["id"]), payload)
    _corrupt_record_logged.discard(normalized["id"])
    return normalized


def save_runtime_snapshot(rid: int, snapshot: Dict) -> Dict:
    _ensure_dirs()
    normalized = dict(snapshot)
    normalized["id"] = int(rid)
    normalized["updated_at"] = time.time()
    payload = json.dumps(normalized, ensure_ascii=False, indent=2)
    with _registry_lock():
        _atomic_write_text(_snapshot_path(rid), payload)
    _corrupt_snapshot_logged.discard(int(rid))
    return normalized


def load_runtime_snapshot(rid: int) -> Optional[Dict]:
    path = _snapshot_path(rid)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        rid_int = int(rid)
        if rid_int not in _corrupt_snapshot_logged:
            logger.warning("Failed to read runtime snapshot %s: %s", path, exc)
            _corrupt_snapshot_logged.add(rid_int)
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass
        return None
    _corrupt_snapshot_logged.discard(int(rid))
    data["id"] = int(rid)
    return data


def delete_runtime_snapshot(rid: int) -> bool:
    path = _snapshot_path(rid)
    if not path.exists():
        return False
    path.unlink()
    return True


def update_runtime_snapshot(rid: int, **updates) -> Dict:
    existing = load_runtime_snapshot(rid) or {}
    merged = {**existing, **updates}
    return save_runtime_snapshot(rid, merged)


def register_runtime(
        *,
        rid: int,
        pid: int,
        config_path: Optional[str],
        name: Optional[str],
        frame_dir: Optional[str],
        source: str,
        managed: bool = False,
        state: str = "running",
        error: Optional[str] = None,
        session_id: Optional[str] = None,
        log_session_id: Optional[str] = None,
) -> Dict:
    now = time.time()
    existing = load_runtime_record(rid, refresh_state=False) or {}
    record = {
        **existing,
        "id": int(rid),
        "pid": int(pid) if pid else None,
        "config_path": str(config_path) if config_path else existing.get("config_path"),
        "name": name if name is not None else existing.get("name"),
        "frame_dir": str(frame_dir) if frame_dir else existing.get("frame_dir"),
        "source": source or existing.get("source") or "process",
        "managed": bool(managed or existing.get("managed")),
        "state": state,
        "error": error,
        "session_id": session_id or existing.get("session_id"),
        "log_session_id": log_session_id or existing.get("log_session_id"),
        "started_at": existing.get("started_at") or now,
        "updated_at": now,
    }
    return save_runtime_record(record)


def update_runtime(
        rid: int,
        **updates,
) -> Optional[Dict]:
    existing = load_runtime_record(rid, refresh_state=False)
    if existing is None:
        return None
    existing.update(updates)
    existing["updated_at"] = time.time()
    return save_runtime_record(existing)


def mark_runtime_stopped(rid: int, *, error: Optional[str] = None) -> Optional[Dict]:
    return update_runtime(rid, state="stopped", pid=None, error=error, stopped_at=time.time())


def delete_runtime_record(rid: int) -> bool:
    path = _record_path(rid)
    if not path.exists():
        return False
    path.unlink()
    delete_runtime_snapshot(rid)
    return True


def _record_to_stub(record: Dict) -> Dict:
    stub = {key: record.get(key) for key in _STUB_FIELDS}
    stub["id"] = int(record.get("id") or 0)
    stub["alive"] = bool(record.get("alive"))
    stub["managed"] = bool(record.get("managed"))
    return stub


def list_runtime_record_stubs(*, discover: bool = False) -> Dict[int, Dict]:
    """Light registry scan: id/pid/state/alive/paths only (no snapshots)."""
    _ensure_dirs()
    if discover:
        maybe_discover_process_runtimes()
    items: Dict[int, Dict] = {}
    for path in REGISTRY_DIR.glob("*.json"):
        try:
            rid = int(path.stem)
        except ValueError:
            continue
        record = load_runtime_record(rid, refresh_state=True)
        if not record:
            continue
        items[rid] = _record_to_stub(record)
    return dict(sorted(items.items(), key=lambda pair: pair[0]))


def prune_stale_runtime_records(
        *,
        max_stopped_age_sec: float = 7 * 86400,
        keep_recent_stopped: int = 50,
        max_total_records: int = 200,
) -> int:
    """Delete dead/stopped registry entries to keep UI scans cheap.

    Keeps all alive PIDs. Among stopped/dead records keeps the newest
    ``keep_recent_stopped`` (and anything newer than ``max_stopped_age_sec``
    until total exceeds ``max_total_records``).
    """
    _ensure_dirs()
    now = time.time()
    stubs: list[Dict] = []
    for path in list(REGISTRY_DIR.glob("*.json")):
        try:
            rid = int(path.stem)
        except ValueError:
            continue
        record = load_runtime_record(rid, refresh_state=True)
        if not record:
            continue
        stubs.append(_record_to_stub(record))

    alive = [s for s in stubs if s.get("alive") and _is_pid_alive(s.get("pid"))]
    alive_ids = {int(s["id"]) for s in alive}
    dead = [s for s in stubs if int(s.get("id") or 0) not in alive_ids]
    def _recency(stub: Dict) -> float:
        for key in ("stopped_at", "updated_at", "started_at"):
            try:
                return float(stub.get(key) or 0.0)
            except (TypeError, ValueError):
                continue
        return 0.0

    dead_sorted = sorted(dead, key=_recency, reverse=True)
    keep_dead: list[Dict] = []
    for stub in dead_sorted:
        if len(keep_dead) >= max(0, int(keep_recent_stopped)):
            break
        age = now - _recency(stub)
        if float(max_stopped_age_sec) > 0 and age > float(max_stopped_age_sec):
            continue
        keep_dead.append(stub)
    while len(alive) + len(keep_dead) > max(1, int(max_total_records)) and keep_dead:
        keep_dead.pop()

    keep_ids = {int(s["id"]) for s in alive} | {int(s["id"]) for s in keep_dead}
    pruned = 0
    for stub in stubs:
        rid = int(stub.get("id") or 0)
        if rid in keep_ids:
            continue
        if delete_runtime_record(rid):
            pruned += 1
    if pruned:
        logger.info(
            "Pruned %d stale runtime registry record(s); kept alive=%d stopped=%d",
            pruned,
            len(alive),
            len(keep_dead),
        )
    return pruned


def list_runtime_records(*, include_stopped: bool = True, discover: bool = True) -> Dict[int, Dict]:
    _ensure_dirs()
    if discover:
        maybe_discover_process_runtimes()
    items: Dict[int, Dict] = {}
    for path in sorted(REGISTRY_DIR.glob("*.json")):
        try:
            rid = int(path.stem)
        except ValueError:
            continue
        record = load_runtime_record(rid)
        if not record:
            continue
        if not include_stopped and record.get("state") == "stopped":
            continue
        items[rid] = record
    return items
