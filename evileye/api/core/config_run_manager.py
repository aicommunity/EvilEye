import os
import json
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Dict, Optional

from evileye.core.logger import get_module_logger


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
        self.frame_dir: Optional[Path] = None


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
        from evileye.api.core.broker_access import get_broker
        broker = get_broker()
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
                        broker.publish_jpeg(str(rid), data)
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
        self._frame_poller = _FramePoller(self.logger)

    def _describe_locked(self, item: ConfigRunItem) -> Dict:
        return {
            "id": item.id,
            "name": item.name,
            "config_path": str(item.config_path),
            "pid": item.pid,
            "state": item.state,
            "error": item.error,
        }

    def list(self) -> Dict[int, Dict]:
        with self._lock:
            return {rid: self._describe_locked(it) for rid, it in self._items.items()}

    def describe(self, rid: int) -> Dict:
        with self._lock:
            item = self._items.get(rid)
            if item is None:
                raise KeyError("Config run not found")
            return self._describe_locked(item)

    def _ensure_configs_dir(self) -> Path:
        cfg_dir = Path("configs")
        cfg_dir.mkdir(parents=True, exist_ok=True)
        return cfg_dir

    def _write_config_file(self, rid: int, name: Optional[str], body: dict) -> Path:
        cfg_dir = self._ensure_configs_dir()
        safe_name = (name or f"config_run_{rid}.json").strip()
        if not safe_name.endswith(".json"):
            safe_name += ".json"
        target = cfg_dir / safe_name
        with open(target, "w", encoding="utf-8") as f:
            json.dump(body, f, ensure_ascii=False, indent=2)
        return target

    def create(self, rid: int, name: Optional[str], *, config_name: Optional[str] = None, config_body: Optional[dict] = None) -> Dict:
        with self._lock:
            if rid in self._items:
                raise ValueError("Config run already exists")

            if config_body is None and config_name:
                path = self._ensure_configs_dir() / Path(config_name).name
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
                raise KeyError("Config run not found")
            if item.state == ConfigRunState.RUNNING:
                raise RuntimeError("Stop config run before delete")
            self._items.pop(rid)
            self.logger.info(f"ConfigRun '{rid}' deleted")
            return {"id": rid, "status": "deleted"}

    def start(self, rid: int) -> Dict:
        with self._lock:
            item = self._items.get(rid)
            if item is None:
                raise KeyError("Config run not found")

        if item.state in (ConfigRunState.RUNNING, ConfigRunState.STARTING):
            return self.describe(rid)

        try:
            item.state = ConfigRunState.STARTING

            frame_dir = Path(tempfile.gettempdir()) / "evileye_frames" / str(rid)
            frame_dir.mkdir(parents=True, exist_ok=True)
            item.frame_dir = frame_dir

            env = {
                **os.environ,
                "EVILEYE_PIPELINE_ID": str(rid),
                "EVILEYE_FRAME_DIR": str(frame_dir),
                "PYTHONUNBUFFERED": "1",
            }
            cmd = [
                os.sys.executable,
                str(Path(__file__).resolve().parents[2] / "process.py"),
                "--config", str(item.config_path),
                "--no-gui",
                "--no-autoclose",
            ]
            self.logger.info(f"Starting config run '{rid}': {' '.join(cmd)}")
            proc = subprocess.Popen(cmd, cwd=str(Path.cwd()), env=env)
            item.pid = proc.pid
            item.state = ConfigRunState.RUNNING
            self._frame_poller.watch(rid, frame_dir)
            self.logger.info(f"ConfigRun '{rid}' running with pid {item.pid}, frame_dir={frame_dir}")
        except Exception as e:
            item.state = ConfigRunState.ERROR
            item.error = str(e)
            self.logger.error(f"ConfigRun '{rid}' failed to start: {e}")

        return self.describe(rid)

    def stop(self, rid: int) -> Dict:
        with self._lock:
            item = self._items.get(rid)
            if item is None:
                raise KeyError("Config run not found")

        self._frame_poller.unwatch(rid)

        if item.pid is None or item.state not in (ConfigRunState.STARTING, ConfigRunState.RUNNING):
            item.state = ConfigRunState.STOPPED
            self._cleanup_frame_dir(item)
            return self.describe(rid)

        try:
            item.state = ConfigRunState.STOPPING
            self.logger.info(f"Stopping config run '{rid}', pid={item.pid}")
            os.kill(item.pid, signal.SIGTERM)
            for _ in range(10):
                try:
                    os.kill(item.pid, 0)
                except OSError:
                    item.pid = None
                    item.state = ConfigRunState.STOPPED
                    break
                else:
                    time.sleep(0.2)
            if item.state != ConfigRunState.STOPPED and item.pid is not None:
                self.logger.warning(f"Force killing config run '{rid}', pid={item.pid}")
                try:
                    os.kill(item.pid, signal.SIGKILL)
                except Exception:
                    pass
                item.pid = None
                item.state = ConfigRunState.STOPPED
        except Exception as e:
            item.state = ConfigRunState.ERROR
            item.error = str(e)
            self.logger.error(f"ConfigRun '{rid}' failed to stop: {e}")

        self._cleanup_frame_dir(item)
        return self.describe(rid)

    def _cleanup_frame_dir(self, item: ConfigRunItem) -> None:
        if item.frame_dir and item.frame_dir.exists():
            try:
                shutil.rmtree(item.frame_dir, ignore_errors=True)
            except Exception:
                pass
            item.frame_dir = None

    def shutdown(self) -> None:
        with self._lock:
            if self._shutdown_called:
                self.logger.info("ConfigRunManager shutdown already called, skipping")
                return
            self._shutdown_called = True

        self.logger.info("ConfigRunManager shutdown initiated")
        self._frame_poller.stop()
        with self._lock:
            ids = list(self._items.keys())
        for rid in ids:
            try:
                self.stop(rid)
            except Exception as e:
                self.logger.error(f"Error stopping config run '{rid}': {e}")
        self.logger.info("ConfigRunManager shutdown completed")


