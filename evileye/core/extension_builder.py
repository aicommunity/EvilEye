"""Shared application services behind the Web UI and CLI extension workflows."""

from __future__ import annotations

import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import zipfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Mapping

from evileye.core.paths import site_root
from evileye.core.pipeline_configuration import (
    save_config_document,
    schema_mapping,
    validate_configuration,
)
from evileye.core.plugin_scaffold import (
    PluginScaffoldError,
    create_plugin_project,
    normalize_plugin_name,
    template_descriptions,
    template_module_id,
    template_names,
)

_operations_lock = threading.RLock()


@contextmanager
def _installation_lock(root: Path):
    """Serialize editable installs across backend and detached worker processes."""
    lock_path = _operation_directory(root) / "install.lock"
    with lock_path.open("a+b") as stream:
        if os.name == "nt":
            import msvcrt

            if os.fstat(stream.fileno()).st_size == 0:
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
def _json_schema(schema: Any) -> dict[str, Any] | None:
    return schema_mapping(schema)


def extension_catalog() -> dict[str, Any]:
    """Return installed extension metadata without constructing modules or pipelines."""
    from evileye.core.builtin_inventory import register_builtins
    from evileye.core.plugins import plugin_registry

    register_builtins()
    modules = []
    for identity in plugin_registry.list_modules():
        registered = plugin_registry.get_module(identity)
        if registered is None:
            continue
        spec = registered.spec
        modules.append({
            "id": registered.qualified_id,
            "plugin_id": registered.plugin_id,
            "module_id": spec.module_id,
            "kind": spec.kind,
            "display_name": spec.display_name or spec.module_id,
            "description": spec.description or "",
            "stages": list(spec.stages),
            "execution_modes": list(spec.execution_modes),
            "default_execution_mode": spec.default_execution_mode,
            "capabilities": list(spec.capabilities),
            "config_schema": _json_schema(spec.config_schema),
        })
    pipelines = []
    for identity in plugin_registry.list_pipelines():
        registered = plugin_registry.get_pipeline(identity)
        if registered is None:
            continue
        spec = registered.spec
        pipelines.append({
            "id": registered.qualified_id,
            "config_id": spec.pipeline_id if registered.plugin_id == "evileye" else registered.qualified_id,
            "plugin_id": registered.plugin_id,
            "pipeline_id": spec.pipeline_id,
            "display_name": spec.display_name or spec.pipeline_id,
            "description": spec.description or "",
            "config_schema": _json_schema(spec.config_schema),
            "has_topology": callable(spec.topology_provider),
        })
    from evileye.events_detectors.event_registry import DEFAULT_ENABLED_EVENT_DETECTORS

    return {
        "modules": modules,
        "pipelines": pipelines,
        "default_event_detectors": list(DEFAULT_ENABLED_EVENT_DETECTORS),
        "templates": [
            {"id": name, "description": template_descriptions()[name], "module_id": template_module_id(name)}
            for name in template_names()
        ],
    }


def preview_pipeline(config: dict[str, Any]) -> dict[str, Any]:
    from evileye.core.pipeline_topology import build_topology

    if not isinstance(config, dict):
        raise ValueError("Pipeline configuration must be a JSON object")
    diagnostics = validate_configuration(config)
    errors = [item for item in diagnostics if "(preserved for manual configuration)" not in item]
    topology = build_topology(config).to_dict()
    return {"valid": not errors, "errors": errors, "warnings": [item for item in diagnostics if item not in errors], "topology": topology}


def save_pipeline(name: str, config: dict[str, Any], *, create_only: bool = False, root: Path | None = None) -> dict[str, Any]:
    return save_config_document(name, config, root=site_root(root), create_only=create_only)


def plugin_root(root: Path | None = None) -> Path:
    site = site_root(root)
    directory = site / "plugins"
    directory.mkdir(parents=True, exist_ok=True)
    resolved = directory.resolve()
    try:
        resolved.relative_to(site)
    except ValueError as exc:
        raise PluginScaffoldError("Site plugin directory may not point outside the site root") from exc
    return resolved


def _plugin_state_directory(root: Path | None, name: str, *, create: bool = True) -> Path:
    base = plugin_root(root)
    parent = base / ".evileye"
    resolved_parent = parent.resolve()
    try:
        resolved_parent.relative_to(base)
    except ValueError as exc:
        raise PluginScaffoldError("Plugin state storage may not point outside the site plugin directory") from exc
    directory = parent / name
    if create:
        directory.mkdir(parents=True, exist_ok=True)
    resolved = directory.resolve()
    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise PluginScaffoldError("Plugin state storage may not point outside the site plugin directory") from exc
    return resolved


def _operation_directory(root: Path | None = None) -> Path:
    return _plugin_state_directory(root, "operations")


def _artifact_directory(root: Path | None = None, *, create: bool = True) -> Path:
    return _plugin_state_directory(root, "artifacts", create=create)


def _operation_path(operation_id: str, root: Path | None = None) -> Path:
    if not operation_id or any(char not in "0123456789abcdef-" for char in operation_id.lower()):
        raise ValueError("Invalid operation id")
    base = _operation_directory(root)
    path = (base / f"{operation_id}.json").resolve()
    path.relative_to(base)
    return path


def _store_operation(operation: dict[str, Any], root: Path | None = None) -> None:
    path = _operation_path(str(operation["id"]), root)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(operation, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def get_plugin_operation(operation_id: str, *, root: Path | None = None) -> dict[str, Any]:
    path = _operation_path(operation_id, root)
    if not path.is_file():
        raise FileNotFoundError(operation_id)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Invalid operation record")
    return payload


def list_plugin_operations(*, limit: int = 20, root: Path | None = None) -> list[dict[str, Any]]:
    """Return recent persisted plugin operations for reconnecting the Web UI."""
    try:
        page_size = max(1, min(int(limit), 100))
    except (TypeError, ValueError) as exc:
        raise ValueError("Operation limit must be an integer") from exc
    directory = _operation_directory(root)
    if not directory.is_dir():
        return []
    operations = []
    for path in directory.glob("*.json"):
        try:
            operation = get_plugin_operation(path.stem, root=root)
        except (FileNotFoundError, OSError, ValueError):
            continue
        if isinstance(operation.get("updated_at"), (int, float)):
            operations.append(operation)
    operations.sort(key=lambda item: (float(item["updated_at"]), str(item.get("id", ""))), reverse=True)
    return operations[:page_size]


def _update_operation(operation_id: str, *, root: Path | None = None, **updates: Any) -> dict[str, Any]:
    with _operations_lock:
        current = get_plugin_operation(operation_id, root=root)
        current.update(updates)
        current["updated_at"] = time.time()
        _store_operation(current, root)
        return current


def reconcile_plugin_operations(*, root: Path | None = None) -> None:
    """Close a restart handoff after the newly started Web process comes up."""
    candidate = plugin_root(root) / ".evileye" / "operations"
    if not candidate.exists():
        return
    directory = _operation_directory(root)
    if not directory.is_dir():
        return
    for path in directory.glob("*.json"):
        try:
            operation = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(operation, dict) and operation.get("status") == "restarting":
                operation.update(status="completed", message="Web UI restarted and plugin discovery is ready.", updated_at=time.time())
                _store_operation(operation, root)
            elif isinstance(operation, dict) and operation.get("status") == "restart_queued":
                operation.update(status="pending_restart", message="Package installed; the restart helper did not complete. Restart EvilEye Web manually.", updated_at=time.time())
                _store_operation(operation, root)
        except Exception:
            continue


def _make_archive(destination: Path, archive: Path) -> None:
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as output:
        for path in sorted(destination.rglob("*")):
            if path.is_symlink():
                raise PluginScaffoldError("Generated plugin may not contain symlinks")
            if path.is_file():
                output.write(path, Path(destination.name) / path.relative_to(destination))


def create_plugin_archive(project: Path, archive: Path) -> Path:
    """Build a ZIP using the exact generated project tree."""
    project = Path(project).resolve()
    archive = Path(archive).resolve()
    if not project.is_dir():
        raise PluginScaffoldError(f"Plugin project does not exist: {project}")
    if archive.exists():
        raise PluginScaffoldError(f"Plugin archive already exists: {archive}")
    _make_archive(project, archive)
    return archive


def _missing_dependencies(project: Path) -> list[str]:
    try:
        import tomllib
    except ModuleNotFoundError:  # Python 3.10
        try:
            import tomli as tomllib
        except ModuleNotFoundError as exc:
            raise RuntimeError("Reading plugin metadata on Python 3.10 requires the tomli package") from exc
    from packaging.requirements import Requirement
    from packaging.utils import canonicalize_name
    from packaging.version import Version

    data = tomllib.loads((project / "pyproject.toml").read_text(encoding="utf-8"))
    requirements = list(data.get("project", {}).get("dependencies", []))
    requirements.extend(data.get("build-system", {}).get("requires", []))
    missing: list[str] = []
    for raw in requirements:
        requirement = Requirement(str(raw))
        if requirement.marker is not None and not requirement.marker.evaluate():
            continue
        if canonicalize_name(requirement.name) == "evileye":
            continue
        try:
            installed = importlib.metadata.version(requirement.name)
        except importlib.metadata.PackageNotFoundError:
            missing.append(str(requirement))
            continue
        if requirement.specifier and not requirement.specifier.contains(Version(installed), prereleases=True):
            missing.append(f"{requirement} (installed: {installed})")
    return missing


def _validate_installed_entry_point(plugin_id: str) -> None:
    code = (
        "import importlib.metadata as m; "
        f"eps=[e for e in m.entry_points(group='evileye.plugins') if e.name == {plugin_id!r}]; "
        "assert len(eps) == 1, f'expected one entry point, found {len(eps)}'; "
        "loaded=eps[0].load(); spec=loaded() if callable(loaded) else loaded; "
        "from evileye.core.plugins import PluginSpec, PLUGIN_API_VERSION; "
        "assert isinstance(spec, PluginSpec), 'entry point did not return PluginSpec'; "
        "assert spec.plugin_id == " + repr(plugin_id) + ", 'entry point plugin_id mismatch'; "
        "assert spec.api_version == PLUGIN_API_VERSION, 'plugin API version mismatch'"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout or "Plugin entry point validation failed").strip()[-2000:])


def _service_python_matches(root: Path) -> bool:
    from evileye.service_manager.state import load_state

    state = load_state(root)
    configured = state.get("python_executable")
    if not configured:
        return False
    try:
        return Path(str(configured)).expanduser().resolve() == Path(sys.executable).resolve()
    except OSError:
        return False


def dispatch_plugin_service_restart(operation_id: str, root: Path) -> bool:
    """Dispatch installation/restart work outside the web service process."""
    from evileye.service_manager.state import load_state
    from evileye.stack_control import is_in_container

    backend = str(load_state(root).get("backend") or "")
    env = os.environ.copy()
    env["EVILEYE_SITE_DIR"] = str(root.resolve())
    args = [sys.executable, "-m", "evileye.core.plugin_operation_worker", "--operation", operation_id, "--site", str(root.resolve())]
    if backend.startswith("systemd-") and not is_in_container():
        systemd_run = shutil.which("systemd-run")
        if not systemd_run:
            return False
        command = [systemd_run]
        if backend == "systemd-user":
            command.append("--user")
        command.extend([
            "--unit", f"evileye-plugin-restart-{operation_id[:8]}",
            "--collect", "--property=Type=oneshot",
            f"--working-directory={root.resolve()}",
            f"--setenv=EVILEYE_SITE_DIR={root.resolve()}",
            *args,
        ])
        result = subprocess.run(command, capture_output=True, text=True, timeout=20, check=False)
        return result.returncode == 0
    if backend.startswith("systemd-") and not is_in_container():
        return False
    if backend and backend not in {"windows-task", "manual", ""} and not is_in_container():
        return False
    options: dict[str, Any] = {
        "cwd": root,
        "env": env,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if sys.platform.startswith("win"):
        options["creationflags"] = (
            getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "DETACHED_PROCESS", 0)
        )
    else:
        options["start_new_session"] = True
    subprocess.Popen(args, **options)
    return True


def restart_plugin_service(operation_id: str, root: Path) -> None:
    """Run in a detached helper process to restart and verify the web service."""
    from evileye.service_manager import control_service
    from evileye.service_manager.state import load_state
    from evileye.stack_control import wait_web_ready

    try:
        _update_operation(operation_id, root=root, status="restarting", message="Restarting the managed EvilEye Web service.")
        port = int(load_state(root).get("port") or 8181)
        result = control_service("restart", site_dir=root)
        if not result.ok:
            _update_operation(operation_id, root=root, status="pending_restart", message=f"Package installed; service restart failed: {result.message}")
        elif wait_web_ready(port=port, timeout=60.0):
            _update_operation(operation_id, root=root, status="completed", message="Plugin installed and EvilEye Web is ready.")
        else:
            _update_operation(operation_id, root=root, status="pending_restart", message="Service restart was requested but Web UI did not become ready; check service logs.")
    except Exception as exc:
        try:
            _update_operation(operation_id, root=root, status="pending_restart", message=f"Package installed; restart helper failed: {exc}")
        except Exception:
            pass


def _install_and_restart(operation_id: str, root: Path) -> None:
    from evileye.service_manager import is_service_installed

    with _installation_lock(root):
        operation = get_plugin_operation(operation_id, root=root)
        try:
            destination = Path(operation["directory"]).resolve()
            destination.relative_to(plugin_root(root))
            _update_operation(operation_id, root=root, status="validating", message="Checking plugin dependencies and entry point.")
            if is_service_installed(root) and not _service_python_matches(root):
                _update_operation(
                    operation_id,
                    root=root,
                    status="failed",
                    message="The running Web backend and managed service use different Python environments; refusing to install into the wrong environment.",
                )
                return
            missing = _missing_dependencies(destination)
            if missing:
                _update_operation(operation_id, root=root, status="dependencies_missing", message="Install the plugin dependencies manually before installing the package.", missing_dependencies=missing)
                return
            _update_operation(operation_id, root=root, status="installing", message="Installing the editable package into the EvilEye Python environment.")
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--no-deps", "--no-build-isolation", "-e", str(destination)],
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
            )
            if result.returncode:
                raise RuntimeError((result.stderr or result.stdout or "pip install failed").strip()[-3000:])
            _validate_installed_entry_point(str(operation["plugin_id"]))
            _update_operation(operation_id, root=root, status="installed", message="Package installed. Restart is required for discovery.")
            if not is_service_installed(root) or not _service_python_matches(root):
                _update_operation(operation_id, root=root, status="pending_restart", message="Package installed. Restart EvilEye Web to load this plugin.")
                return
            from evileye.stack_control import is_in_container
            if is_in_container():
                _update_operation(operation_id, root=root, status="pending_restart", message="Package installed in the current container. Rebuild or restart the Web container to load this plugin.")
                return
            restart_plugin_service(operation_id, root)
        except Exception as exc:
            try:
                _update_operation(operation_id, root=root, status="failed", message=str(exc))
            except Exception:
                pass


def create_plugin_operation(name: str, template: str, *, root: Path | None = None) -> dict[str, Any]:
    """Create a scaffold/ZIP and start its dependency-safe editable installation."""
    site = site_root(root)
    destination_root = plugin_root(site)
    directory_name, plugin_id = normalize_plugin_name(name)
    from evileye.core.builtin_inventory import register_builtins
    from evileye.core.plugins import plugin_registry

    register_builtins()
    if any(identity.startswith(f"{plugin_id}/") for identity in plugin_registry.list_modules()) or any(
        identity.startswith(f"{plugin_id}/") for identity in plugin_registry.list_pipelines()
    ):
        raise PluginScaffoldError(f"Plugin id '{plugin_id}' is already registered")
    destination = (destination_root / directory_name).resolve()
    try:
        destination.relative_to(destination_root)
    except ValueError as exc:
        raise PluginScaffoldError("Plugin destination escapes the site plugin directory") from exc
    operation_id = str(uuid.uuid4())
    artifact_root = _artifact_directory(site)
    archive = (artifact_root / f"{operation_id}.zip").resolve()
    archive.relative_to(artifact_root)
    operation: dict[str, Any] = {
        "id": operation_id,
        "status": "generating",
        "name": directory_name,
        "plugin_id": plugin_id,
        "template": str(template),
        "created_at": time.time(),
        "updated_at": time.time(),
        "directory": str(destination),
        "archive": str(archive),
        "message": "Generating the plugin package and ZIP archive.",
    }
    _store_operation(operation, site)
    try:
        project = create_plugin_project(directory_name, destination_root, template)
        create_plugin_archive(project, archive)
        operation.update(status="queued", message="Package created; installation queued.", updated_at=time.time())
        _store_operation(operation, site)
    except Exception as exc:
        operation.update(status="failed", message=str(exc), updated_at=time.time())
        _store_operation(operation, site)
        raise
    if not dispatch_plugin_service_restart(operation_id, site):
        _update_operation(
            operation_id,
            root=site,
            status="failed",
            message="Plugin package was generated, but an isolated installer could not be started. Install it manually with the EvilEye Python environment.",
        )
    return get_plugin_operation(operation_id, root=site)


def plugin_operation_archive(operation_id: str, *, root: Path | None = None) -> Path:
    operation = get_plugin_operation(operation_id, root=root)
    archive = Path(str(operation.get("archive") or "")).resolve()
    archive.relative_to(_artifact_directory(root, create=False))
    if not archive.is_file():
        raise FileNotFoundError(operation_id)
    return archive
