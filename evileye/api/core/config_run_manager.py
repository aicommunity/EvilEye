import os
import json
import signal
import subprocess
import threading
import time
import uuid
from pathlib import Path
from evileye.core.paths import configs_dir, site_root
from typing import Dict, Optional

from evileye.api.core.runtime_registry import (
    allocate_pipeline_id,
    delete_runtime_record,
    load_runtime_record,
    mark_runtime_stopped,
    register_runtime,
)
from evileye.api.security import load_web_auth_config
from evileye.core.logger import get_module_logger
from evileye.core.runtime_services import get_frame_broker


class ConfigRunState:
    CREATED = "created"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


class ConfigRunItem:
    def __init__(self, run_id: int, name: str, config_path: Path):
        self.id = run_id
        self.name = name or f"ConfigRun-{run_id}"
        self.config_path = Path(config_path)
        self.pid: Optional[int] = None
        self.state: str = ConfigRunState.CREATED
        self.error: Optional[str] = None
        self.session_id: Optional[str] = None
        self._proc: subprocess.Popen | None = None


class _FramePoller:
    """Background thread that reads frame files written by child processes
    and publishes them to the FrameBroker so streaming endpoints work."""

    def __init__(self, logger):
        self._lock = threading.Lock()
        self._watched: Dict[int, Path] = {}
        self._mtimes: Dict[int, float] = {}
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True, name="frame-poller")
        self._logger = logger
        self._thread.start()

    def watch(self, rid: int, frame_dir: Path) -> None:
        with self._lock:
            self._watched[rid] = frame_dir / "latest.jpg"
            self._mtimes[rid] = 0.0
        self._logger.info(f"Frame poller watching rid={rid} at {frame_dir}")

    def unwatch(self, rid: int) -> None:
        with self._lock:
            self._watched.pop(rid, None)
            self._mtimes.pop(rid, None)

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=3.0)

    def _loop(self) -> None:
        broker = get_frame_broker()
        first_frame_logged: dict = {}
        miss_counter: dict = {}
        while not self._stop.is_set():
            with self._lock:
                items = list(self._watched.items())
            for rid, fpath in items:
                try:
                    if not fpath.exists():
                        cnt = miss_counter.get(rid, 0) + 1
                        miss_counter[rid] = cnt
                        if cnt == 250:
                            self._logger.warning(
                                "Frame file %s still missing after ~10s", fpath
                            )
                        continue
                    mtime = fpath.stat().st_mtime
                    prev = self._mtimes.get(rid, 0.0)
                    if mtime <= prev:
                        continue
                    data = fpath.read_bytes()
                    if data:
                        broker.publish_jpeg(
                            str(rid),
                            data,
                            metadata={
                                "timestamp": time.time(),
                                "content_type": "image/jpeg",
                                "transport": "file_ipc",
                            },
                        )
                        with self._lock:
                            self._mtimes[rid] = mtime
                        if rid not in first_frame_logged:
                            first_frame_logged[rid] = True
                            self._logger.info(
                                "First frame read for rid=%s (%d bytes, mtime=%.3f)",
                                rid, len(data), mtime,
                            )
                except Exception as e:
                    self._logger.warning("FramePoller error for rid=%s: %s", rid, e)
            self._stop.wait(0.04)


class ConfigRunManager:
    """Manage starting/stopping configs via separate process (process.py)."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._items: Dict[int, ConfigRunItem] = {}
        self._shutdown_called = False
        self.logger = get_module_logger("api.config_run_manager")

    @staticmethod
    def _stop_grace_sec() -> float:
        try:
            return max(1.0, float(os.getenv("EVILEYE_RUN_STOP_GRACE_SEC", "60")))
        except ValueError:
            return 60.0

    def _terminate_process_tree(self, pid: int, *, grace_sec: float) -> bool:
        if not pid:
            return True
        from evileye.api.core.process_restart import pid_hosts_current_process
        from evileye.core.process_control import pid_exists, terminate_tree

        if pid_hosts_current_process(int(pid)):
            raise RuntimeError(
                "Refusing to stop the process that hosts this API; use POST /api/v1/system/restart"
            )
        try:
            terminate_tree(int(pid), grace_sec=grace_sec)
        except Exception:
            return False
        return not pid_exists(int(pid))

    def restart_for_config(
        self,
        config_name: str,
        *,
        api_base_url: str | None = None,
    ) -> Dict:
        """
        Safely restart the pipeline for a config.

        - If the running process hosts this API (evileye run + embedded server):
          spawn a detached helper, SIGTERM the pipeline PID only, return immediately.
        - Otherwise (standalone API / managed run): stop → create → start.
        """
        from evileye.api.core.process_restart import (
            build_process_cmd,
            cmdline_config_path,
            cmdline_has_gui,
            find_matching_runtime,
            pid_hosts_current_process,
            read_cmdline,
            signal_pid_term,
            spawn_detached_restart_helper,
        )
        from evileye.api.core.runtime_registry import list_runtime_records
        from evileye.api.core.safe_paths import safe_config_name

        safe_name = safe_config_name(
            config_name if str(config_name).endswith(".json") else f"{config_name}.json"
        )
        # Merge live registry + manager items for discovery
        records = dict(list_runtime_records())
        for rid, item in self.list().items():
            existing = records.get(rid, {})
            records[rid] = {**existing, **item, "id": rid}

        matching = find_matching_runtime(records, safe_name)
        if matching is None:
            # No running process — just create and start a managed run.
            rid = self.next_run_id()
            self.create(rid, Path(safe_name).stem, config_name=safe_name)
            started = self.start(rid, api_base_url=api_base_url)
            return {
                "mode": "managed_start",
                "scheduled": False,
                "config_name": safe_name,
                "run": started,
            }

        rid = int(matching.get("id"))
        pid = matching.get("pid")
        config_path = matching.get("config_path") or str(configs_dir() / safe_name)
        managed = bool(matching.get("managed"))

        if pid and pid_hosts_current_process(int(pid)):
            argv = read_cmdline(int(pid))
            gui = cmdline_has_gui(argv) if argv else False
            # Prefer config path from cmdline when present
            cfg_from_cmd = cmdline_config_path(argv) if argv else None
            if cfg_from_cmd:
                config_path = cfg_from_cmd
            cmd = build_process_cmd(config_path, gui=gui, autoclose=False)
            helper_pid = spawn_detached_restart_helper(
                wait_pid=int(pid),
                cmd=cmd,
                cwd=site_root(),
                grace_sec=max(self._stop_grace_sec(), 90.0),
            )
            # Graceful controller shutdown without killpg (would suicide the API).
            try:
                signal_pid_term(int(pid))
            except ProcessLookupError:
                pass
            self.logger.info(
                "Self-hosted restart scheduled: rid=%s pid=%s helper=%s gui=%s",
                rid,
                pid,
                helper_pid,
                gui,
            )
            return {
                "mode": "self_hosted_detached",
                "scheduled": True,
                "config_name": safe_name,
                "stopped_rid": rid,
                "stopped_pid": int(pid),
                "helper_pid": helper_pid,
                "restart_cmd": cmd,
            }

        # External / managed run under standalone API: classic stop + recreate.
        try:
            self.stop(rid)
        except KeyError:
            pass
        except RuntimeError as exc:
            # Should not be self-hosted here, but surface clearly.
            raise
        new_rid = self.next_run_id()
        self.create(new_rid, Path(safe_name).stem, config_name=safe_name)
        started = self.start(new_rid, api_base_url=api_base_url)
        return {
            "mode": "managed_restart",
            "scheduled": False,
            "config_name": safe_name,
            "previous_rid": rid,
            "run": started,
            "managed": managed,
        }

    def _cleanup_run_session(self, item: ConfigRunItem) -> None:
        if not item.session_id:
            return
        try:
            from evileye.core.mp_session_registry import cleanup_session_by_id

            cleanup_session_by_id(item.session_id)
        except Exception as exc:
            self.logger.warning("MP session cleanup failed for run %s: %s", item.id, exc)

    def _describe_locked(self, item: ConfigRunItem) -> Dict:
        return {
            "id": item.id,
            "name": item.name,
            "config_path": str(item.config_path),
            "pid": item.pid,
            "state": item.state,
            "error": item.error,
            "session_id": item.session_id,
        }

    def _refresh_item_state_locked(self, item: ConfigRunItem) -> None:
        pid = item.pid
        if not pid or item.state not in (
                ConfigRunState.STARTING,
                ConfigRunState.RUNNING,
                ConfigRunState.STOPPING,
        ):
            return
        try:
            os.kill(pid, 0)
            return
        except OSError:
            item.pid = None
            item.state = ConfigRunState.STOPPED
            item.error = None
        try:
            mark_runtime_stopped(item.id)
        except Exception:
            pass

    def list(self) -> Dict[int, Dict]:
        with self._lock:
            for item in self._items.values():
                self._refresh_item_state_locked(item)
            return {rid: self._describe_locked(it) for rid, it in self._items.items()}

    def next_run_id(self) -> int:
        with self._lock:
            return allocate_pipeline_id(self._items.keys())

    def describe(self, rid: int) -> Dict:
        with self._lock:
            item = self._items.get(rid)
            if item is None:
                raise KeyError("Config run not found")
            self._refresh_item_state_locked(item)
            return self._describe_locked(item)

    def _ensure_configs_dir(self) -> Path:
        cfg_dir = configs_dir()
        cfg_dir.mkdir(parents=True, exist_ok=True)
        return cfg_dir

    def _write_config_file(self, rid: int, name: Optional[str], body: dict) -> Path:
        from evileye.api.core.safe_paths import UnsafePathError, assert_under_dir, safe_config_name

        cfg_dir = self._ensure_configs_dir()
        raw = (name or f"config_run_{rid}.json").strip()
        if not raw.endswith(".json"):
            raw += ".json"
        try:
            safe_name = safe_config_name(raw)
            target = assert_under_dir(cfg_dir / safe_name, cfg_dir)
        except UnsafePathError as exc:
            raise ValueError(str(exc)) from exc
        with open(target, "w", encoding="utf-8") as f:
            json.dump(body, f, ensure_ascii=False, indent=2)
        return target

    def create(self, rid: int, name: Optional[str], *, config_name: Optional[str] = None,
               config_body: Optional[dict] = None) -> Dict:
        with self._lock:
            if rid in self._items:
                raise ValueError("Config run already exists")

            if config_body is None and config_name:
                from evileye.api.core.safe_paths import UnsafePathError, assert_under_dir, safe_config_name

                try:
                    safe = safe_config_name(
                        config_name if str(config_name).endswith(".json") else f"{config_name}.json"
                    )
                    path = assert_under_dir(self._ensure_configs_dir() / safe, self._ensure_configs_dir())
                except UnsafePathError as exc:
                    raise ValueError(str(exc)) from exc
                if not path.exists():
                    raise FileNotFoundError("Config file not found")
            elif config_body is not None:
                path = self._write_config_file(rid, name or None, config_body)
            else:
                raise ValueError("Provide config_body or config_name")

            item = ConfigRunItem(rid, name or None, path)
            self._items[rid] = item
            self.logger.info(f"ConfigRun '{rid}' created: {item.name}, path={item.config_path}")
            return self._describe_locked(item)

    def delete(self, rid: int) -> Dict:
        with self._lock:
            item = self._items.get(rid)
            if item is None:
                runtime = load_runtime_record(rid)
                if runtime is None:
                    raise KeyError("Config run not found")
                if runtime.get("state") == ConfigRunState.RUNNING:
                    raise RuntimeError("Stop config run before delete")
                delete_runtime_record(rid)
                return {"id": rid, "status": "deleted"}
            if item.state == ConfigRunState.RUNNING:
                raise RuntimeError("Stop config run before delete")
            self._items.pop(rid)
            delete_runtime_record(rid)
            self.logger.info(f"ConfigRun '{rid}' deleted")
            return {"id": rid, "status": "deleted"}

    def start(self, rid: int, *, api_base_url: str | None = None) -> Dict:
        with self._lock:
            item = self._items.get(rid)
            if item is None:
                runtime = load_runtime_record(rid)
                if runtime and runtime.get("config_path"):
                    item = ConfigRunItem(
                        rid,
                        runtime.get("name") or Path(runtime["config_path"]).stem,
                        Path(runtime["config_path"]),
                    )
                    self._items[rid] = item
                else:
                    raise KeyError("Config run not found")

        if item.state in (ConfigRunState.RUNNING, ConfigRunState.STARTING):
            return self.describe(rid)

        try:
            item.state = ConfigRunState.STARTING
            auth = load_web_auth_config()

            session_id = uuid.uuid4().hex
            from evileye.api.core.log_service import allocate_log_session_id

            log_session_id = allocate_log_session_id()
            env = {
                **os.environ,
                "EVILEYE_PIPELINE_ID": str(rid),
                "EVILEYE_PIPELINE_NAME": item.name,
                "EVILEYE_MANAGED_RUN": "1",
                "EVILEYE_SESSION_ID": session_id,
                "EVILEYE_LOG_SESSION_ID": log_session_id,
                "PYTHONUNBUFFERED": "1",
            }
            if api_base_url:
                env["EVILEYE_WEB_API_BASE"] = api_base_url
            if auth.internal_token:
                env["EVILEYE_INTERNAL_TOKEN"] = auth.internal_token
            cmd = [
                os.sys.executable,
                str(Path(__file__).resolve().parents[2] / "process.py"),
                "--config", str(item.config_path),
                "--no-gui",
                "--no-autoclose",
            ]
            self.logger.info(f"Starting config run '{rid}': {' '.join(cmd)}")
            proc = subprocess.Popen(
                cmd,
                cwd=str(site_root()),
                env=env,
                start_new_session=True,
            )
            item._proc = proc
            item.pid = proc.pid
            item.session_id = session_id
            item.state = ConfigRunState.RUNNING
            item.error = None
            register_runtime(
                rid=rid,
                pid=proc.pid,
                config_path=str(item.config_path),
                name=item.name,
                frame_dir=None,
                source="web",
                managed=True,
                state="running",
                session_id=session_id,
                log_session_id=log_session_id,
            )
            self.logger.info(f"ConfigRun '{rid}' running with pid {item.pid}")
        except Exception as e:
            item.state = ConfigRunState.ERROR
            item.error = str(e)
            mark_runtime_stopped(rid, error=str(e))
            self.logger.error(f"ConfigRun '{rid}' failed to start: {e}")

        return self.describe(rid)

    def stop(self, rid: int) -> Dict:
        with self._lock:
            item = self._items.get(rid)
            if item is None:
                runtime = load_runtime_record(rid)
                if runtime is None:
                    raise KeyError("Config run not found")
                pid = runtime.get("pid")
                session_id = runtime.get("session_id")
                if not pid:
                    return runtime
                try:
                    self._terminate_process_tree(int(pid), grace_sec=self._stop_grace_sec())
                except Exception as e:
                    mark_runtime_stopped(rid, error=str(e))
                    raise
                if session_id:
                    try:
                        from evileye.core.mp_session_registry import cleanup_session_by_id

                        cleanup_session_by_id(str(session_id))
                    except Exception:
                        pass
                mark_runtime_stopped(rid)
                runtime = load_runtime_record(rid)
                if runtime is None:
                    raise KeyError("Config run not found")
                return runtime

        if item.pid is None or item.state not in (ConfigRunState.STARTING, ConfigRunState.RUNNING):
            item.state = ConfigRunState.STOPPED
            mark_runtime_stopped(rid)
            return self.describe(rid)

        try:
            item.state = ConfigRunState.STOPPING
            self.logger.info(f"Stopping config run '{rid}', pid={item.pid}")
            pid = item.pid
            if pid is not None:
                self._terminate_process_tree(int(pid), grace_sec=self._stop_grace_sec())
            if item._proc is not None:
                try:
                    item._proc.wait(timeout=1.0)
                except Exception:
                    pass
                item._proc = None
            item.pid = None
            item.state = ConfigRunState.STOPPED
            self._cleanup_run_session(item)
        except RuntimeError:
            # e.g. refusing to kill API host — surface to caller (HTTP 409)
            item.state = ConfigRunState.RUNNING
            raise
        except Exception as e:
            item.state = ConfigRunState.ERROR
            item.error = str(e)
            self.logger.error(f"ConfigRun '{rid}' failed to stop: {e}")

        mark_runtime_stopped(rid, error=item.error if item.state == ConfigRunState.ERROR else None)
        return self.describe(rid)

    def shutdown(self) -> None:
        with self._lock:
            if self._shutdown_called:
                self.logger.info("ConfigRunManager shutdown already called, skipping")
                return
            self._shutdown_called = True

        self.logger.info("ConfigRunManager shutdown initiated")
        with self._lock:
            ids = list(self._items.keys())
        for rid in ids:
            try:
                self.stop(rid)
            except Exception as e:
                self.logger.error(f"Error stopping config run '{rid}': {e}")
        self.logger.info("ConfigRunManager shutdown completed")
