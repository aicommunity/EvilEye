import os
import json
import signal
import subprocess
import threading
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


class ConfigRunManager:
    """Manage starting/stopping configs via separate process (process.py)."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._items: Dict[int, ConfigRunItem] = {}
        self._shutdown_called = False
        self.logger = get_module_logger("api.config_run_manager")

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
            # Spawn separate python process to run config headless (no GUI)
            cmd = [
                os.sys.executable,
                str(Path(__file__).resolve().parents[2] / "process.py"),
                "--config", str(item.config_path),
                "--no-gui",
                "--no-autoclose",
            ]
            self.logger.info(f"Starting config run '{rid}': {' '.join(cmd)}")
            proc = subprocess.Popen(cmd, cwd=str(Path.cwd()))
            item.pid = proc.pid
            item.state = ConfigRunState.RUNNING
            self.logger.info(f"ConfigRun '{rid}' running with pid {item.pid}")
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

        if item.pid is None or item.state not in (ConfigRunState.STARTING, ConfigRunState.RUNNING):
            item.state = ConfigRunState.STOPPED
            return self.describe(rid)

        try:
            item.state = ConfigRunState.STOPPING
            self.logger.info(f"Stopping config run '{rid}', pid={item.pid}")
            os.kill(item.pid, signal.SIGTERM)
            # Wait a bit, escalate if needed
            for _ in range(10):
                try:
                    os.kill(item.pid, 0)
                except OSError:
                    item.pid = None
                    item.state = ConfigRunState.STOPPED
                    break
                else:
                    import time
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


