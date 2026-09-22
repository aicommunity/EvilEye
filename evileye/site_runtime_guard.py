"""Per-site singleton guards for pipeline and web launch paths."""

from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Literal, Optional

from evileye.core.filelock import with_file_lock
from evileye.core.paths import monitor_dir, site_root
from evileye.core.process_control import find_pids_by_cmdline_regex, pid_exists, process_cmdline

SingletonPolicy = Literal["fail", "skip", "replace"]

_SITE_ENV = "EVILEYE_SITE_DIR"


class DuplicatePipelineError(RuntimeError):
    """Raised when a pipeline for this site/config is already running."""

    def __init__(
        self,
        message: str,
        *,
        pid: Optional[int] = None,
        config_path: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.pid = pid
        self.config_path = config_path


class DuplicateWebError(RuntimeError):
    """Raised when a web listener for this site is already running."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


@dataclass
class SiteRunSnapshot:
    site_dir: Path
    web_listener_pid: Optional[int] = None
    web_foreground_pids: list[int] = field(default_factory=list)
    pipeline_runs: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class EnsureResult:
    ok: bool = True
    skipped: bool = False
    replaced: bool = False
    existing_pid: Optional[int] = None
    existing_mode: Optional[str] = None
    config_path: Optional[str] = None
    message: str = ""


def _resolve_site(site_dir: Path | None) -> Path:
    return site_root(site_dir)


def _read_proc_env(pid: int, key: str) -> Optional[str]:
    try:
        raw = open(f"/proc/{pid}/environ", "rb").read()
    except OSError:
        return None
    prefix = f"{key}=".encode()
    for part in raw.split(b"\x00"):
        if part.startswith(prefix):
            return part.split(b"=", 1)[1].decode("utf-8", errors="replace")
    return None


def process_site_dir(pid: int) -> Optional[Path]:
    if not pid_exists(pid):
        return None
    env_site = _read_proc_env(pid, _SITE_ENV)
    if env_site:
        return Path(env_site).expanduser().resolve()
    try:
        cwd = os.readlink(f"/proc/{pid}/cwd")
        if cwd:
            return Path(cwd).resolve()
    except OSError:
        pass
    return None


def pid_belongs_to_site(pid: int, site_dir: Path) -> bool:
    proc_site = process_site_dir(pid)
    if proc_site is None:
        return False
    try:
        return proc_site == site_dir.resolve()
    except OSError:
        return str(proc_site) == str(site_dir.resolve())


def record_belongs_to_site(rec: dict[str, Any], site_dir: Path) -> bool:
    pid = rec.get("pid")
    if pid and pid_belongs_to_site(int(pid), site_dir):
        return True
    path = str(rec.get("config_path") or "")
    if not path:
        return False
    try:
        cfg = Path(path).expanduser()
        if not cfg.is_absolute():
            cfg = site_dir / cfg
        cfg.resolve().relative_to(site_dir.resolve())
        return True
    except (OSError, ValueError):
        return False


def config_basename(config: str) -> str:
    from evileye.utils.config_paths import normalize_config_path

    name = Path(normalize_config_path(config)).name
    if not name.endswith(".json"):
        name = f"{name}.json"
    return name


def config_basename_from_rec(rec: dict[str, Any]) -> str:
    path = str(rec.get("config_path") or "")
    if not path:
        return ""
    base = Path(path).name
    if not base.endswith(".json"):
        base = f"{base}.json"
    return base


def _matches_config(rec: dict[str, Any], config: str) -> bool:
    want = config_basename(config)
    path = str(rec.get("config_path") or "")
    base = Path(path).name if path else ""
    return base == want or path.endswith(want)


def _alive_record(rec: dict[str, Any]) -> bool:
    if not isinstance(rec, dict):
        return False
    state = str(rec.get("state") or "")
    return bool(rec.get("alive")) or state in {"running", "starting"}


def _extract_config_from_cmdline(cmd: str) -> str:
    parts = cmd.split()
    for idx, part in enumerate(parts):
        if part in ("--config", "-c") and idx + 1 < len(parts):
            return parts[idx + 1]
    return ""


def _resolve_config_path(config: str, site_dir: Path) -> Path:
    from evileye.utils.config_paths import normalize_config_path

    raw = Path(normalize_config_path(config))
    if raw.is_absolute() and raw.exists():
        return raw.resolve()
    candidate = site_dir / raw
    if candidate.exists():
        return candidate.resolve()
    if raw.exists():
        return raw.resolve()
    return candidate


@contextmanager
def spawn_lock(site_dir: Path | None = None) -> Iterator[None]:
    root = _resolve_site(site_dir)
    lock_path = monitor_dir(root) / ".spawn.lock"
    with with_file_lock(lock_path):
        yield


def discover_site_runs(site_dir: Path | None = None) -> SiteRunSnapshot:
    from evileye.api.core.runtime_registry import list_runtime_records
    from evileye.service_manager import probe_port_scheme
    from evileye.site_profile import service_port
    from evileye.stack_control import _port_listener_pid

    root = _resolve_site(site_dir)
    port = service_port(root)
    scheme = probe_port_scheme(port)
    listener: Optional[int] = None
    if scheme != "closed":
        candidate = _port_listener_pid(port)
        if candidate and pid_belongs_to_site(candidate, root):
            listener = candidate

    server_patterns = [
        r"evileye(\.exe)?\s+server\b",
        r"cli_wrapper.*\s+server\b",
        r"evileye/server\.py",
    ]
    fg_pids = sorted(
        {
            pid
            for pid in find_pids_by_cmdline_regex(server_patterns)
            if pid_belongs_to_site(pid, root)
        }
    )

    pipeline_runs: list[dict[str, Any]] = []
    records = dict(list_runtime_records(discover=True))
    for rec in records.values():
        if not isinstance(rec, dict) or not _alive_record(rec):
            continue
        if not record_belongs_to_site(rec, root):
            continue
        pipeline_runs.append(dict(rec))

    seen_pids = {int(rec["pid"]) for rec in pipeline_runs if rec.get("pid")}
    for pid in find_pids_by_cmdline_regex([r"process\.py\b", r"process_wrapper\b"]):
        if pid in seen_pids or not pid_belongs_to_site(pid, root):
            continue
        cmd = process_cmdline(pid) or ""
        if "process.py" not in cmd and "process_wrapper" not in cmd:
            continue
        pipeline_runs.append(
            {
                "id": None,
                "pid": pid,
                "config_path": _extract_config_from_cmdline(cmd),
                "managed": _read_proc_env(pid, "EVILEYE_MANAGED_RUN") == "1",
                "source": "proc",
                "alive": True,
                "state": "running",
            }
        )

    return SiteRunSnapshot(
        site_dir=root,
        web_listener_pid=listener,
        web_foreground_pids=fg_pids,
        pipeline_runs=pipeline_runs,
    )


def find_alive_pipelines_for_config(
    site_dir: Path | None,
    config: str,
) -> list[dict[str, Any]]:
    root = _resolve_site(site_dir)
    matches: list[dict[str, Any]] = []
    for rec in discover_site_runs(root).pipeline_runs:
        if not _matches_config(rec, config):
            continue
        pid = rec.get("pid")
        if pid and not pid_exists(int(pid)):
            continue
        matches.append(rec)

    from evileye.watchdog_native import find_cli_and_child

    cli_pid, child_pid = find_cli_and_child(config, root=root)
    for pid in (child_pid, cli_pid):
        if not pid or not pid_exists(pid) or not pid_belongs_to_site(pid, root):
            continue
        if any(int(item.get("pid") or 0) == pid for item in matches):
            continue
        matches.append(
            {
                "pid": pid,
                "config_path": str(_resolve_config_path(config, root)),
                "source": "watchdog",
                "alive": True,
                "managed": _read_proc_env(pid, "EVILEYE_MANAGED_RUN") == "1",
            }
        )

    def _sort_key(rec: dict[str, Any]) -> tuple[int, int, int]:
        return (
            0 if rec.get("managed") else 1,
            0 if rec.get("source") == "web" else 1,
            -int(rec.get("id") or 0),
        )

    matches.sort(key=_sort_key)
    return matches


def find_alive_pipeline_for_config(
    site_dir: Path | None,
    config: str,
) -> Optional[dict[str, Any]]:
    matches = find_alive_pipelines_for_config(site_dir, config)
    return matches[0] if matches else None


def ensure_pipeline_singleton(
    config: str,
    site_dir: Path | None = None,
    *,
    policy: SingletonPolicy = "fail",
) -> EnsureResult:
    root = _resolve_site(site_dir)
    config_path = str(_resolve_config_path(config, root))
    alive = find_alive_pipelines_for_config(root, config)
    if not alive:
        return EnsureResult(ok=True, config_path=config_path)

    primary = alive[0]
    pid = int(primary.get("pid") or 0)
    mode = "managed" if primary.get("managed") else "direct"

    if policy == "skip":
        return EnsureResult(
            skipped=True,
            existing_pid=pid or None,
            existing_mode=mode,
            config_path=config_path,
            message=f"Pipeline already running pid={pid}",
        )

    if policy == "fail":
        hint = (
            f"Pipeline already running for {config_basename(config)} "
            f"(pid={pid}). Use: evileye pipeline restart"
            + (f" {config}" if config else "")
            + " (or: pipeline start CONFIG --replace)"
        )
        raise DuplicatePipelineError(hint, pid=pid or None, config_path=config_path)

    from evileye.stack_control import stop_pipelines

    stop_pipelines(site_dir=root, config=config, stop_all=False, hold=False)
    return EnsureResult(ok=True, replaced=True, config_path=config_path)


def _service_process_tree_pids(main_pid: Optional[int]) -> set[int]:
    if main_pid is None:
        return set()
    if not pid_exists(main_pid):
        return set()
    try:
        import psutil

        proc = psutil.Process(main_pid)
        return {main_pid, *[child.pid for child in proc.children(recursive=True)]}
    except Exception:
        return {main_pid}


def ensure_web_singleton(
    site_dir: Path | None = None,
    *,
    policy: SingletonPolicy = "fail",
    port: Optional[int] = None,
    self_pid: Optional[int] = None,
) -> EnsureResult:
    import os

    from evileye.service_manager import (
        is_web_os_service_active,
        probe_port_scheme,
        web_service_main_pid,
    )
    from evileye.site_profile import service_port

    root = _resolve_site(site_dir)
    listen_port = port if port is not None else service_port(root)
    snap = discover_site_runs(root)
    scheme = probe_port_scheme(listen_port)
    collisions: list[str] = []
    current_pid = self_pid if self_pid is not None else os.getpid()
    service_main_pid = web_service_main_pid()
    service_tree = _service_process_tree_pids(service_main_pid)
    we_are_service = current_pid in service_tree

    other_foreground = [pid for pid in snap.web_foreground_pids if pid not in service_tree and pid != current_pid]

    if is_web_os_service_active() and not we_are_service:
        collisions.append("os_service_active")
    if other_foreground:
        collisions.append(
            "foreground_server_pids=" + ",".join(str(pid) for pid in other_foreground)
        )
    if (
        scheme != "closed"
        and snap.web_listener_pid
        and snap.web_listener_pid not in service_tree
        and snap.web_listener_pid != current_pid
    ):
        collisions.append(f"port_{listen_port}_listener_pid={snap.web_listener_pid}")

    if not collisions:
        return EnsureResult(ok=True)

    message = "; ".join(collisions)
    if policy == "skip":
        return EnsureResult(skipped=True, message=message)

    hint = (
        f"Web layer already running for site ({message}). "
        "Stop OS service or foreground server first: evileye service stop"
    )
    raise DuplicateWebError(hint)


def singleton_warnings(site_dir: Path | None = None) -> list[str]:
    from evileye.service_manager import is_web_os_service_active, web_service_main_pid

    root = _resolve_site(site_dir)
    snap = discover_site_runs(root)
    warnings: list[str] = []
    service_main_pid = web_service_main_pid()
    service_tree = _service_process_tree_pids(service_main_pid)
    other_foreground = [pid for pid in snap.web_foreground_pids if pid not in service_tree]

    by_config: dict[str, list[dict[str, Any]]] = {}
    for rec in snap.pipeline_runs:
        pid = rec.get("pid")
        if not pid or not pid_exists(int(pid)):
            continue
        base = config_basename_from_rec(rec)
        if not base:
            continue
        by_config.setdefault(base, []).append(rec)

    for base, runs in by_config.items():
        if len(runs) > 1:
            pids = ",".join(str(rec.get("pid")) for rec in runs)
            warnings.append(f"duplicate_pipeline_detected:{base} pids={pids}")

    if is_web_os_service_active() and other_foreground:
        pids = ",".join(str(pid) for pid in other_foreground)
        warnings.append(f"web_collision:service_active+foreground_pids={pids}")

    return warnings
