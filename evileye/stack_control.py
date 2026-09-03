"""Orchestration for EvilEye web service + pipeline stack."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from evileye.core.paths import monitor_dir, site_root
from evileye.core.process_control import find_pids_by_cmdline_regex, pid_exists, terminate_tree
from evileye.site_profile import (
    gui_default,
    pipeline_launch_mode,
    resolve_production_config,
    resolve_watchdog_config,
    service_port,
)


class ContainerOperationError(RuntimeError):
    """Raised when an OS-service operation is requested inside Docker."""


COMMAND_CATALOG: list[tuple[str, str]] = [
    ("status", "Show this overview"),
    ("prod up / down", "Start/stop production stack"),
    ("service start|stop|restart", "Manage OS web service"),
    ("pipeline start|stop|restart [CONFIG]", "Pipeline lifecycle (CONFIG optional when unique)"),
    ("reload web [--with-pipeline]", "Rebuild/restart web; optional pipeline restart"),
    ("reload pipeline [CONFIG]", "Restart pipeline only"),
    ("web build|check", "Frontend/deps"),
    ("run CONFIG", "Direct pipeline (dev)"),
]

CONFIG_RESOLVE_HINT = (
    "Specify CONFIG, or set production_config via: evileye prod init CONFIG / "
    "evileye service install CONFIG"
)


class AmbiguousPipelineConfigError(RuntimeError):
    """Raised when multiple alive pipelines exist and CONFIG was not specified."""


@dataclass
class StackState:
    site_dir: Path
    in_container: bool
    service_installed: bool = False
    service_backend: Optional[str] = None
    service_enabled: bool = False
    service_active: bool = False
    port: int = 8181
    port_scheme: str = "closed"
    port_listener_pid: Optional[int] = None
    foreground_server_pids: list[int] = field(default_factory=list)
    runtimes: dict[int, dict[str, Any]] = field(default_factory=dict)
    console_runs: list[dict[str, Any]] = field(default_factory=list)
    managed_runs: list[dict[str, Any]] = field(default_factory=list)
    watchdog_config: Optional[str] = None
    watchdog_grace_active: bool = False
    manual_stop_active: bool = False
    warnings: list[str] = field(default_factory=list)
    suggested_command: Optional[str] = None
    suggested_commands: list[str] = field(default_factory=list)


@dataclass
class StopResult:
    stopped_pids: list[int] = field(default_factory=list)
    hold_applied: bool = False


@dataclass
class SpawnResult:
    pid: int
    mode: str
    config_path: str


@dataclass
class ReloadResult:
    ok: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)


def is_in_container() -> bool:
    if os.environ.get("EVILEYE_IN_CONTAINER", "").strip().lower() in {"1", "true", "yes"}:
        return True
    return Path("/.dockerenv").exists()


def _stop_grace_sec() -> float:
    try:
        return max(1.0, float(os.getenv("EVILEYE_RUN_STOP_GRACE_SEC", "60")))
    except ValueError:
        return 60.0


def _resolve_site(site_dir: Path | None) -> Path:
    return Path(site_dir).resolve() if site_dir is not None else site_root()


def _alive_pipeline_configs(site_dir: Path | None = None) -> list[str]:
    """Unique config paths from alive pipeline runs on this site."""
    root = _resolve_site(site_dir)
    paths: list[str] = []
    seen: set[str] = set()
    runs: list[dict[str, Any]] = []
    try:
        from evileye.site_runtime_guard import discover_site_runs

        runs = list(discover_site_runs(root).pipeline_runs)
    except Exception:
        try:
            from evileye.api.core.runtime_registry import list_runtime_records

            for rec in list_runtime_records(discover=True).values():
                if not isinstance(rec, dict):
                    continue
                alive = bool(rec.get("alive")) or rec.get("state") in {"running", "starting"}
                if alive:
                    runs.append(rec)
        except Exception:
            runs = []
    for rec in runs:
        if not isinstance(rec, dict):
            continue
        path = str(rec.get("config_path") or "").strip()
        if not path or path in seen:
            continue
        seen.add(path)
        paths.append(path)
    return paths


def resolve_pipeline_config(
    site_dir: Path | None = None,
    *,
    explicit: Optional[str] = None,
    allow_running: bool = True,
) -> Optional[str]:
    """Resolve pipeline config: CLI → unique running → production → watchdog.

    Raises AmbiguousPipelineConfigError when allow_running and multiple distinct
    alive configs exist without an explicit choice.
    """
    if explicit is not None and str(explicit).strip():
        return str(explicit).strip()

    root = _resolve_site(site_dir)
    if allow_running:
        configs = _alive_pipeline_configs(root)
        if len(configs) == 1:
            return configs[0]
        if len(configs) > 1:
            listed = ", ".join(configs)
            raise AmbiguousPipelineConfigError(
                f"Multiple pipeline configs are running ({listed}). "
                f"Specify CONFIG explicitly. {CONFIG_RESOLVE_HINT}"
            )

    return resolve_production_config(root) or resolve_watchdog_config(root)


def require_pipeline_config(
    site_dir: Path | None = None,
    *,
    explicit: Optional[str] = None,
    allow_running: bool = True,
) -> str:
    cfg = resolve_pipeline_config(site_dir, explicit=explicit, allow_running=allow_running)
    if cfg:
        return cfg
    raise FileNotFoundError(
        f"No pipeline config resolved. {CONFIG_RESOLVE_HINT}"
    )


def _port_listener_pid(port: int, host: str = "127.0.0.1") -> Optional[int]:
    if shutil.which("ss"):
        proc = subprocess.run(
            ["ss", "-ltnp", f"sport = :{port}"],
            capture_output=True,
            text=True,
            check=False,
        )
        for line in (proc.stdout or "").splitlines():
            if "pid=" not in line:
                continue
            try:
                fragment = line.split("pid=", 1)[1]
                return int(fragment.split(",", 1)[0])
            except (IndexError, ValueError):
                continue
    if sys.platform.startswith("linux"):
        try:
            for entry in Path("/proc/net/tcp").read_text(encoding="utf-8").splitlines()[1:]:
                parts = entry.split()
                if len(parts) < 10:
                    continue
                local = parts[1]
                port_hex = local.split(":", 1)[1]
                if int(port_hex, 16) != port:
                    continue
                inode = parts[9]
                for proc_dir in Path("/proc").iterdir():
                    if not proc_dir.name.isdigit():
                        continue
                    fd_dir = proc_dir / "fd"
                    if not fd_dir.is_dir():
                        continue
                    for fd in fd_dir.iterdir():
                        try:
                            target = os.readlink(fd)
                        except OSError:
                            continue
                        if f"socket:[{inode}]" in target:
                            return int(proc_dir.name)
        except OSError:
            pass
    return None


def discover_stack_state(site_dir: Path | None = None) -> StackState:
    from evileye.api.core.runtime_registry import list_runtime_records
    from evileye.service_manager import (
        is_web_os_service_active,
        is_web_os_service_enabled,
        load_state,
        probe_port_scheme,
    )
    from evileye.watchdog_native import manual_stop_active, restart_grace_active

    root = _resolve_site(site_dir)
    state = load_state(root)
    port = service_port(root)
    scheme = probe_port_scheme(port)
    listener_pid = _port_listener_pid(port) if scheme != "closed" else None

    server_pids = find_pids_by_cmdline_regex(
        [
            r"evileye(\.exe)?\s+server\b",
            r"cli_wrapper.*\s+server\b",
            r"evileye/server\.py",
        ]
    )

    runtimes = dict(list_runtime_records(discover=True))
    console_runs: list[dict[str, Any]] = []
    managed_runs: list[dict[str, Any]] = []
    for rec in runtimes.values():
        if not isinstance(rec, dict):
            continue
        alive = bool(rec.get("alive")) or rec.get("state") in {"running", "starting"}
        if not alive:
            continue
        if rec.get("managed"):
            managed_runs.append(rec)
        else:
            console_runs.append(rec)

    stack = StackState(
        site_dir=root,
        in_container=is_in_container(),
        service_installed=bool(state.get("installed")),
        service_backend=state.get("backend") if isinstance(state.get("backend"), str) else None,
        service_enabled=is_web_os_service_enabled(),
        service_active=is_web_os_service_active(),
        port=port,
        port_scheme=scheme,
        port_listener_pid=listener_pid,
        foreground_server_pids=sorted(set(server_pids)),
        runtimes=runtimes,
        console_runs=console_runs,
        managed_runs=managed_runs,
        watchdog_config=resolve_watchdog_config(root),
        watchdog_grace_active=restart_grace_active(root),
        manual_stop_active=manual_stop_active(root),
    )

    if stack.service_enabled and not stack.service_active and scheme == "closed":
        stack.warnings.append(
            "OS web service is enabled but not active; run: evileye service start"
        )
    if scheme != "closed" and stack.service_installed and not stack.service_active:
        if stack.foreground_server_pids:
            stack.warnings.append(
                "Foreground evileye server is running while OS service is not active"
            )
    if stack.manual_stop_active:
        stack.warnings.append("Watchdog manual stop is active (pipeline auto-restart suppressed)")
    from evileye.site_runtime_guard import singleton_warnings

    for warning in singleton_warnings(root):
        stack.warnings.append(warning)

    # Default recommendation by site mode, then override with problem-specific hints.
    if stack.in_container:
        defaults = ["docker compose restart web"]
    elif stack.service_installed:
        defaults = ["evileye reload web"]
    else:
        defaults = ["evileye dev server"]

    problem_hints: list[str] = []
    for warning in stack.warnings:
        if warning.startswith("duplicate_pipeline_detected"):
            problem_hints.append("evileye pipeline stop --all")
        elif warning.startswith("web_collision"):
            problem_hints.append("evileye service restart")
        elif "OS web service is enabled but not active" in warning:
            problem_hints.append("evileye service start")
        elif "manual stop" in warning.lower():
            cfg = stack.watchdog_config or resolve_production_config(root)
            if cfg:
                problem_hints.append(f"evileye pipeline start {cfg} --release")
            else:
                problem_hints.append("evileye pipeline start CONFIG --release")

    # Preserve order, unique
    seen: set[str] = set()
    suggested: list[str] = []
    for cmd in problem_hints + defaults:
        if cmd not in seen:
            seen.add(cmd)
            suggested.append(cmd)
    stack.suggested_commands = suggested[:3]
    stack.suggested_command = stack.suggested_commands[0] if stack.suggested_commands else None
    return stack


def wait_web_ready(
    host: str = "127.0.0.1",
    port: int = 8181,
    timeout: float = 60.0,
    *,
    verify_tls: bool = False,
) -> bool:
    from evileye.service_manager import probe_port_scheme

    deadline = time.time() + max(1.0, timeout)
    scheme = probe_port_scheme(port, host=host)
    url_scheme = scheme if scheme in {"http", "https"} else "http"
    if verify_tls and scheme == "https":
        url_scheme = "https"
    url = f"{url_scheme}://{host}:{port}/ready"
    while time.time() < deadline:
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                if resp.status == 200:
                    return True
        except urllib.error.HTTPError as exc:
            if exc.code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def _cleanup_mp_sessions(session_ids: list[str]) -> None:
    for sid in session_ids:
        if not sid:
            continue
        try:
            from evileye.core.mp_session_registry import cleanup_session_by_id

            cleanup_session_by_id(str(sid))
        except Exception:
            pass


def stop_pipelines(
    *,
    site_dir: Path | None = None,
    config: Optional[str] = None,
    stop_all: bool = False,
    hold: bool = False,
    hold_seconds: int = 3600,
) -> StopResult:
    from evileye.api.core.process_restart import find_matching_runtime
    from evileye.api.core.runtime_registry import list_runtime_records, mark_runtime_stopped
    from evileye.watchdog_native import (
        find_cli_and_child,
        set_manual_stop_cooldown,
        set_restart_grace,
        stop_evileye_run_scope,
    )

    root = _resolve_site(site_dir)
    result = StopResult()
    if hold:
        set_manual_stop_cooldown(seconds=hold_seconds, root=root)
        set_restart_grace(root=root)
        result.hold_applied = True

    records = dict(list_runtime_records(discover=True))
    targets: list[dict[str, Any]] = []
    if stop_all or not config:
        targets = [
            rec
            for rec in records.values()
            if isinstance(rec, dict)
            and (rec.get("alive") or rec.get("state") in {"running", "starting"})
            and rec.get("pid")
        ]
    elif config:
        match = find_matching_runtime(records, config, site_dir=root)
        if match:
            targets = [match]

    session_ids: list[str] = []
    grace = _stop_grace_sec()
    for rec in targets:
        pid = rec.get("pid")
        rid = rec.get("id")
        if rec.get("session_id"):
            session_ids.append(str(rec["session_id"]))
        if not pid:
            continue
        try:
            terminate_tree(int(pid), grace_sec=grace)
            result.stopped_pids.append(int(pid))
            if rid is not None:
                mark_runtime_stopped(int(rid))
        except Exception:
            continue

    wd_cfg = config or resolve_watchdog_config(root)
    if wd_cfg:
        cli_pid, child_pid = find_cli_and_child(wd_cfg, root=root)
        for pid in (child_pid, cli_pid):
            if pid and pid_exists(pid):
                try:
                    terminate_tree(int(pid), grace_sec=grace)
                    result.stopped_pids.append(int(pid))
                except Exception:
                    pass

    stop_evileye_run_scope()
    _cleanup_mp_sessions(session_ids)
    result.stopped_pids = sorted(set(result.stopped_pids))
    return result


def _resolve_config_path(config: str, site_dir: Path) -> Path:
    from evileye.utils.config_paths import normalize_config_path

    normalized = Path(normalize_config_path(config))
    if not normalized.is_absolute():
        candidate = (site_dir / normalized).resolve()
        if candidate.exists():
            return candidate
    if normalized.exists():
        return normalized.resolve()
    raise FileNotFoundError(f"Configuration file not found: {config}")


def _api_base_url(site_dir: Path, port: int) -> str:
    from evileye.service_manager import probe_port_scheme

    scheme = probe_port_scheme(port)
    if scheme not in {"http", "https"}:
        scheme = "http"
    return f"{scheme}://127.0.0.1:{port}/api/v1"


def should_use_managed_launch(site_dir: Path | None = None) -> bool:
    from evileye.service_manager import is_web_os_service_active, probe_port_scheme

    mode = pipeline_launch_mode(site_dir)
    root = _resolve_site(site_dir)
    port = service_port(root)
    if mode == "managed":
        return True
    if mode == "direct":
        return False
    if is_web_os_service_active():
        return True
    return probe_port_scheme(port) != "closed"


def spawn_managed_pipeline(
    config: str,
    *,
    site_dir: Path | None = None,
    api_base_url: Optional[str] = None,
) -> SpawnResult:
    import uuid

    root = _resolve_site(site_dir)
    config_path = _resolve_config_path(config, root)
    port = service_port(root)
    base = api_base_url or _api_base_url(root, port)

    from evileye.api.core.log_service import allocate_log_session_id
    from evileye.api.core.runtime_registry import allocate_pipeline_id
    from evileye.api.security import load_web_auth_config

    auth = load_web_auth_config()
    session_id = uuid.uuid4().hex
    log_session_id = allocate_log_session_id()
    rid = allocate_pipeline_id()
    env = {
        **os.environ,
        "EVILEYE_SITE_DIR": str(root),
        "EVILEYE_PIPELINE_ID": str(rid),
        "EVILEYE_PIPELINE_NAME": config_path.stem,
        "EVILEYE_MANAGED_RUN": "1",
        "EVILEYE_SESSION_ID": session_id,
        "EVILEYE_LOG_SESSION_ID": log_session_id,
        "EVILEYE_WEB_API_BASE": base,
        "PYTHONUNBUFFERED": "1",
    }
    if auth.internal_token:
        env["EVILEYE_INTERNAL_TOKEN"] = auth.internal_token

    process_py = Path(__file__).resolve().parent / "process.py"
    cmd = [
        sys.executable,
        str(process_py),
        "--config",
        str(config_path),
        "--no-gui",
        "--no-autoclose",
    ]
    proc = subprocess.Popen(cmd, cwd=str(root), env=env, start_new_session=True)
    return SpawnResult(pid=proc.pid, mode="managed", config_path=str(config_path))


def spawn_direct_pipeline(
    config: str,
    *,
    site_dir: Path | None = None,
    gui: Optional[bool] = None,
    detach: bool = False,
) -> SpawnResult:
    root = _resolve_site(site_dir)
    config_path = _resolve_config_path(config, root)
    use_gui = gui_default(root) if gui is None else gui
    env = os.environ.copy()
    env["EVILEYE_SITE_DIR"] = str(root)
    env["EVILEYE_CLI_LAUNCHED"] = "1"
    env.setdefault("EVILEYE_SCHEDULER_GPU_SETTLE_SEC", "15")

    if detach and sys.platform.startswith("linux") and shutil.which("systemd-run"):
        from evileye.watchdog_native import stop_evileye_run_scope

        stop_evileye_run_scope()
        log_path = monitor_dir(root) / "pipeline_stdout.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        gui_flag = "--gui" if use_gui else "--no-gui"
        cmd = (
            f"exec {shutil.which('evileye') or sys.executable + ' -m evileye.cli_wrapper'} "
            f"run {config_path} {gui_flag} >>{log_path} 2>&1"
        )
        proc = subprocess.run(
            [
                "systemd-run",
                "--user",
                "--scope",
                "--unit=evileye-run",
                f"--working-directory={root}",
                f"--setenv=EVILEYE_SITE_DIR={root}",
                "bash",
                "-c",
                cmd,
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            raise RuntimeError((proc.stderr or proc.stdout or "systemd-run failed").strip())
        time.sleep(1.0)
        from evileye.watchdog_native import find_cli_and_child

        cli_pid, child_pid = find_cli_and_child(str(config_path), root=root)
        pid = child_pid or cli_pid or 0
        return SpawnResult(pid=int(pid or 0), mode="direct-detach", config_path=str(config_path))

    cmd = [sys.executable, "-m", "evileye.cli_wrapper", "run", str(config_path)]
    cmd.append("--gui" if use_gui else "--no-gui")
    proc = subprocess.Popen(cmd, cwd=str(root), env=env, start_new_session=detach)
    return SpawnResult(pid=proc.pid, mode="direct", config_path=str(config_path))


def _wait_pipeline_alive(pid: int, *, timeout: float = 5.0) -> None:
    """Ensure a freshly spawned pipeline process is still alive after start."""
    if not pid:
        raise RuntimeError("Pipeline did not return a pid")
    deadline = time.time() + max(0.5, float(timeout))
    while time.time() < deadline:
        if pid_exists(int(pid)):
            return
        time.sleep(0.2)
    raise RuntimeError(f"Pipeline process {pid} exited immediately after start")


def pipeline_start(
    config: str,
    *,
    site_dir: Path | None = None,
    gui: Optional[bool] = None,
    detach: bool = False,
    release_hold: bool = False,
    replace: bool = False,
    skip_if_running: bool = False,
    api_base_url: Optional[str] = None,
) -> SpawnResult:
    from evileye.site_runtime_guard import ensure_pipeline_singleton, spawn_lock
    from evileye.watchdog_native import clear_manual_stop_cooldown

    root = _resolve_site(site_dir)
    if release_hold:
        clear_manual_stop_cooldown(root)

    if skip_if_running:
        policy = "skip"
    elif replace:
        policy = "replace"
    else:
        policy = "fail"

    with spawn_lock(root):
        guard = ensure_pipeline_singleton(config, root, policy=policy)
        if guard.skipped:
            mode = guard.existing_mode or "existing"
            return SpawnResult(
                pid=int(guard.existing_pid or 0),
                mode=mode,
                config_path=guard.config_path or config,
            )
        if should_use_managed_launch(root):
            return spawn_managed_pipeline(config, site_dir=root, api_base_url=api_base_url)
        return spawn_direct_pipeline(config, site_dir=root, gui=gui, detach=detach)


def pipeline_restart(
    config: str,
    *,
    site_dir: Path | None = None,
    hold: bool = True,
    gui: Optional[bool] = None,
    detach: bool = False,
    api_base_url: Optional[str] = None,
) -> SpawnResult:
    stop_pipelines(site_dir=site_dir, config=config, stop_all=False, hold=hold)
    time.sleep(1.0)
    result = pipeline_start(
        config,
        site_dir=site_dir,
        gui=gui,
        detach=detach,
        release_hold=not hold,
        replace=True,
        api_base_url=api_base_url,
    )
    _wait_pipeline_alive(result.pid)
    return result


def frontend_needs_build(site_dir: Path | None = None) -> bool:
    from evileye.setup_web import frontend_dir, static_dir

    static_index = static_dir() / "index.html"
    frontend_pkg = frontend_dir() / "package.json"
    if not static_index.is_file():
        return True
    if not frontend_pkg.is_file():
        return False
    try:
        return frontend_pkg.stat().st_mtime > static_index.stat().st_mtime
    except OSError:
        return False


def _stop_stray_foreground_web_servers(site_dir: Path) -> list[int]:
    """Terminate foreground evileye server processes that are not the OS service MainPID."""
    from evileye.service_manager import web_service_main_pid
    from evileye.site_runtime_guard import _service_process_tree_pids, discover_site_runs

    service_main_pid = web_service_main_pid()
    stopped: list[int] = []
    service_tree = _service_process_tree_pids(service_main_pid)
    for pid in discover_site_runs(site_dir).web_foreground_pids:
        if pid in service_tree:
            continue
        try:
            terminate_tree(int(pid), grace_sec=_stop_grace_sec())
            stopped.append(int(pid))
        except Exception:
            continue
    return stopped


def restart_web_layer(
    *,
    site_dir: Path | None = None,
    force_build: bool = False,
    log: Optional[Callable[[str], None]] = None,
) -> None:
    from evileye import setup_web as sw
    from evileye.service_manager import control_service, is_service_installed

    root = _resolve_site(site_dir)
    if is_in_container():
        raise ContainerOperationError(
            "Inside a container, restart the web service with: docker compose restart web"
        )

    should_build = force_build or frontend_needs_build(root)
    if should_build:
        if log:
            log("Building frontend (npm install && npm run build)…")
        sw.build_frontend()

    if is_service_installed(root):
        stray = _stop_stray_foreground_web_servers(root)
        if stray and log:
            log(f"Stopped stray foreground web server PIDs: {', '.join(str(p) for p in stray)}")
        result = control_service("restart", site_dir=root)
        if not result.ok:
            raise RuntimeError(result.message)
        if log:
            log(result.message)
        return

    if log:
        log("No OS service installed; start the web server manually: evileye dev server")


def reload_web(
    *,
    site_dir: Path | None = None,
    force_build: bool = False,
    with_pipeline: bool = False,
    config: Optional[str] = None,
    release_hold: bool = False,
    log: Optional[Callable[[str], None]] = None,
) -> ReloadResult:
    state = discover_stack_state(site_dir)
    root = state.site_dir
    cfg: Optional[str] = config
    if with_pipeline:
        try:
            cfg = resolve_pipeline_config(root, explicit=config, allow_running=True)
        except AmbiguousPipelineConfigError as exc:
            return ReloadResult(ok=False, message=str(exc))

    try:
        if with_pipeline:
            stop_pipelines(site_dir=root, stop_all=True, hold=True)
        restart_web_layer(site_dir=root, force_build=force_build, log=log)
        if not wait_web_ready(port=state.port, timeout=60.0):
            return ReloadResult(ok=False, message=f"Web server not ready on port {state.port}")
        if with_pipeline:
            if not cfg:
                return ReloadResult(
                    ok=False,
                    message=(
                        "Pipeline restart requested but no config specified (--config or site profile). "
                        f"{CONFIG_RESOLVE_HINT}"
                    ),
                )
            spawn = pipeline_start(
                cfg,
                site_dir=root,
                detach=True,
                gui=False,
                release_hold=release_hold or True,
                replace=True,
            )
            return ReloadResult(
                ok=True,
                message="Web layer reloaded and pipeline restarted",
                details={"pipeline_pid": spawn.pid, "pipeline_mode": spawn.mode, "config": cfg},
            )
        return ReloadResult(ok=True, message="Web layer reloaded", details={})
    except ContainerOperationError as exc:
        return ReloadResult(ok=False, message=str(exc))
    except Exception as exc:
        return ReloadResult(ok=False, message=str(exc))


def reload_backend(*, site_dir: Path | None = None) -> ReloadResult:
    from evileye.service_manager import control_service, is_service_installed

    root = _resolve_site(site_dir)
    if is_in_container():
        return ReloadResult(
            ok=False,
            message="Inside a container use: docker compose restart web",
        )
    if not is_service_installed(root):
        return ReloadResult(ok=False, message="OS web service is not installed")
    result = control_service("restart", site_dir=root)
    port = service_port(root)
    ready = wait_web_ready(port=port, timeout=60.0) if result.ok else False
    return ReloadResult(
        ok=result.ok and ready,
        message=result.message,
        details={"ready": ready},
    )


def stack_state_to_json(state: StackState) -> dict[str, Any]:
    return {
        "site_dir": str(state.site_dir),
        "in_container": state.in_container,
        "service_installed": state.service_installed,
        "service_backend": state.service_backend,
        "service_enabled": state.service_enabled,
        "service_active": state.service_active,
        "port": state.port,
        "port_scheme": state.port_scheme,
        "port_listener_pid": state.port_listener_pid,
        "foreground_server_pids": state.foreground_server_pids,
        "runtimes": state.runtimes,
        "console_runs": state.console_runs,
        "managed_runs": state.managed_runs,
        "watchdog_config": state.watchdog_config,
        "watchdog_grace_active": state.watchdog_grace_active,
        "manual_stop_active": state.manual_stop_active,
        "warnings": state.warnings,
        "suggested_command": state.suggested_command,
        "suggested_commands": list(state.suggested_commands),
        "command_catalog": [{"command": cmd, "description": desc} for cmd, desc in COMMAND_CATALOG],
    }
