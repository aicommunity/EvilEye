import atexit
import argparse
import json
import sys
import multiprocessing as mp
import threading
import time
from pathlib import Path
import os
import signal
import uvicorn
from fastapi import FastAPI

sys.path.insert(0, str(Path(__file__).parent.parent))

from evileye.core.logger import get_module_logger
from evileye.core.logging_config import setup_evileye_logging, log_system_info
from evileye.core.runtime_services import get_frame_broker, get_pipeline_manager
from evileye.api.core.config_run_access import get_config_run_manager

_PREVIEW_LEVEL_RANK = {"idle": 0, "grid": 1, "stream": 2}
_VALID_PREVIEW_LEVELS = frozenset(_PREVIEW_LEVEL_RANK)


def _preview_demand_ttl_sec() -> float:
    try:
        return max(5.0, float(os.getenv("EVILEYE_PREVIEW_DEMAND_TTL_SEC", "45")))
    except Exception:
        return 45.0


def _normalize_preview_level(level: str | None) -> str:
    normalized = (level or "grid").strip().lower()
    if normalized in _VALID_PREVIEW_LEVELS:
        return normalized
    return "grid"


def _create_app() -> FastAPI:
    """Load the FastAPI app lazily so missing optional API deps do not break import of this module."""
    from evileye.api.app import create_app

    return create_app()


def build_app() -> FastAPI:
    return _create_app()


def _uvicorn_access_log_enabled() -> bool:
    value = os.getenv("EVILEYE_UVICORN_ACCESS_LOG", "").strip().lower()
    return value in {"1", "true", "yes", "on"}


# -- Standalone entry point for child process ----------------------------

def _run_server_in_process(host, port, log_level, frame_queue, demand_queue, ssl_certfile=None, ssl_keyfile=None):
    """Entry point for the web server child process

    Receives JPEG frames from the main process via *frame_queue* and
    serves them through the MJPEG streaming endpoint
    """
    from evileye.api.core.ssl_files import apply_ssl_env, ssl_enabled

    apply_ssl_env(ssl_certfile, ssl_keyfile)
    setup_evileye_logging(log_level=log_level.upper(), log_to_console=True, log_to_file=True)
    logger = get_module_logger("server.child")
    scheme = "https" if ssl_enabled(ssl_certfile, ssl_keyfile) else "http"
    logger.info(f"Web server child process starting on {scheme}://{host}:{port}")
    if ssl_certfile:
        logger.info("TLS certificate: %s", ssl_certfile)

    try:
        app = _create_app()
    except ModuleNotFoundError as e:
        logger.error(
            "Web server child exiting: missing dependency %r (%s). Install API requirements (e.g. pip install -r requirements.txt).",
            e.name,
            e,
        )
        return
    except Exception as e:
        logger.error("Web server child exiting: failed to create FastAPI app: %s", e, exc_info=True)
        return

    app.state.preview_demand_queue = demand_queue

    # Wire the IPC queue into the broker so frames arrive from main process
    broker = get_frame_broker()
    if frame_queue is not None:
        broker.set_ipc_queue(frame_queue)

    try:
        uvicorn_config = uvicorn.Config(
            app,
            host=host,
            port=port,
            log_level=log_level,
            access_log=_uvicorn_access_log_enabled(),
            ssl_certfile=ssl_certfile,
            ssl_keyfile=ssl_keyfile,
            proxy_headers=True,
            timeout_keep_alive=5,
        )
        server = uvicorn.Server(uvicorn_config)
        server.run()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.error(f"Server child process error: {e}")
    finally:
        broker.stop_ipc()
        logger.info("Web server child process exiting")


class ServerProcessManager:
    """Manages the web server as a separate OS process

    The main process creates a ``frame_queue`` and passes it to the
    child.  Frames are published by calling ``publish_frame()``
    """

    def __init__(self):
        self.logger = get_module_logger("server_process_manager")
        self._process: mp.Process | None = None
        self._frame_queue: mp.Queue | None = None
        self._demand_queue: mp.Queue | None = None
        self._demand_thread: threading.Thread | None = None
        self._demand_stop = threading.Event()
        self._preview_demand: dict[str, tuple[float, str]] = {}
        self._dropped_frames = 0
        self._published_frames = 0

    def start(self, host="127.0.0.1", port=8181, log_level="info", ssl_certfile=None, ssl_keyfile=None):
        if self._process is not None and self._process.is_alive():
            self.logger.warning("Server process already running")
            return

        try:
            frame_queue_size = int(os.getenv("EVILEYE_SERVER_FRAME_QUEUE_MAXSIZE", "8") or "8")
        except Exception:
            frame_queue_size = 8
        self._frame_queue = mp.Queue(maxsize=max(2, frame_queue_size))
        self._demand_queue = mp.Queue(maxsize=200)
        self._demand_stop.clear()
        self._demand_thread = threading.Thread(target=self._demand_listener_loop, daemon=True,
                                               name="server-preview-demand")
        self._demand_thread.start()
        self._process = mp.Process(
            target=_run_server_in_process,
            args=(host, port, log_level, self._frame_queue, self._demand_queue, ssl_certfile, ssl_keyfile),
            daemon=True,
            name="evileye-web-server",
        )
        self._process.start()
        self.logger.info(f"Web server process started, pid={self._process.pid}")

    def _demand_listener_loop(self):
        while not self._demand_stop.is_set():
            if self._demand_queue is None:
                break
            try:
                item = self._demand_queue.get(timeout=0.5)
                if item is None:
                    break
                if isinstance(item, tuple) and len(item) >= 2:
                    key, touched_at = item[0], item[1]
                    level = item[2] if len(item) >= 3 else "grid"
                    force = bool(item[3]) if len(item) >= 4 else False
                    self.touch_preview_demand(
                        str(key),
                        touched_at=float(touched_at),
                        level=str(level),
                        force=force,
                    )
            except Exception:
                continue

    def _merge_preview_demand(
        self,
        pipeline_key: str,
        touched_at: float,
        level: str,
        *,
        force: bool = False,
    ) -> None:
        key = str(pipeline_key)
        normalized_level = _normalize_preview_level(level)
        existing = self._preview_demand.get(key)
        if existing is None or force:
            self._preview_demand[key] = (touched_at, normalized_level)
            return
        _, existing_level = existing
        if _PREVIEW_LEVEL_RANK[normalized_level] >= _PREVIEW_LEVEL_RANK[existing_level]:
            self._preview_demand[key] = (touched_at, normalized_level)
        else:
            self._preview_demand[key] = (touched_at, existing_level)

    def touch_preview_demand(
        self,
        pipeline_key: str,
        *,
        touched_at: float | None = None,
        level: str = "grid",
        force: bool = False,
    ) -> None:
        self._merge_preview_demand(
            pipeline_key,
            float(touched_at or time.time()),
            level,
            force=force,
        )

    def _demand_entry_level(self, key: str, *, ttl_sec: float, now: float) -> str | None:
        entry = self._preview_demand.get(key)
        if entry is None:
            return None
        touched_at, level = entry
        if (now - touched_at) > ttl_sec:
            return None
        return level

    def get_preview_demand_level(self, pipeline_key: str, *, ttl_sec: float | None = None) -> str:
        now = time.time()
        effective_ttl = _preview_demand_ttl_sec() if ttl_sec is None else ttl_sec
        key = str(pipeline_key)
        level = self._demand_entry_level(key, ttl_sec=effective_ttl, now=now)
        if level is not None:
            return level
        # Full-frame keys are opt-in (split editor / ?full=true). Do not inherit root
        # Live/grid demand — that would encode native frames and starve crop previews.
        if ":full:" in key:
            return "idle"
        root_key = key.split(":", 1)[0]
        root_level = self._demand_entry_level(root_key, ttl_sec=effective_ttl, now=now)
        if root_level is not None:
            return root_level
        return "idle"

    def has_preview_demand(self, pipeline_key: str, *, ttl_sec: float | None = None) -> bool:
        return self.get_preview_demand_level(pipeline_key, ttl_sec=ttl_sec) != "idle"

    def publish_frame(self, pipeline_id: str, jpeg_bytes: bytes, metadata=None):
        """Send a JPEG frame to the web server process"""
        if self._frame_queue is None:
            return
        try:
            if self._frame_queue.full():
                try:
                    self._frame_queue.get_nowait()
                    self._dropped_frames += 1
                except Exception:
                    pass
            self._frame_queue.put_nowait((pipeline_id, jpeg_bytes, metadata or {}))
            self._published_frames += 1
        except Exception:
            pass

    def get_runtime_stats(self) -> dict:
        queue_size = None
        if self._frame_queue is not None:
            try:
                queue_size = self._frame_queue.qsize()
            except Exception:
                queue_size = None
        return {
            "published_frames": self._published_frames,
            "dropped_frames": self._dropped_frames,
            "queue_size": queue_size,
            "demand_keys": len(self._preview_demand),
            "alive": self.is_alive(),
        }

    def stop(self, timeout=5.0):
        if self._frame_queue is not None:
            try:
                self._frame_queue.put_nowait(None)
            except Exception:
                pass
        if self._demand_queue is not None:
            try:
                self._demand_queue.put_nowait(None)
            except Exception:
                pass
        self._demand_stop.set()
        if self._demand_thread is not None and self._demand_thread.is_alive():
            self._demand_thread.join(timeout=2.0)
        self._demand_thread = None

        if self._process is not None:
            try:
                # Ask uvicorn to stop gracefully before escalating.
                if self._process.is_alive():
                    os.kill(self._process.pid, signal.SIGTERM)
            except Exception:
                pass
            self._process.join(timeout=timeout)
            if self._process.is_alive():
                self.logger.warning("Force-terminating web server process")
                self._process.terminate()
                self._process.join(timeout=2.0)
                if self._process.is_alive():
                    self._process.kill()
            self._process = None
        self._frame_queue = None
        self._demand_queue = None
        self._preview_demand.clear()
        self.logger.info("Web server process stopped")

    def is_alive(self) -> bool:
        return self._process is not None and self._process.is_alive()


# -- Original single-process entry point ---------------------------------

def run_api_server(host: str = "127.0.0.1", port: int = 8181,
                   reload: bool = True, log_level: str = "info",
                   config: str | None = None, workers: int = 1,
                   verbose: bool = False, ssl_certfile: str | None = None,
                   ssl_keyfile: str | None = None) -> None:
    from evileye.api.core.ssl_files import apply_ssl_env, resolve_ssl_files, ssl_enabled

    cert, key = resolve_ssl_files(cli_cert=ssl_certfile, cli_key=ssl_keyfile)
    apply_ssl_env(cert, key)
    ssl_certfile = str(cert) if cert else None
    ssl_keyfile = str(key) if key else None

    logger = get_module_logger("server")
    effective_log_level = "debug" if verbose and log_level == "info" else log_level
    logger.info("=" * 60)
    logger.info("EvilEye API Server Initialization")
    logger.info("=" * 60)
    scheme = "https" if ssl_enabled(ssl_certfile, ssl_keyfile) else "http"
    logger.info(f"Starting EvilEye API server on {scheme}://{host}:{port}")
    logger.info(f"API documentation will be available at {scheme}://{host}:{port}/docs")
    if ssl_certfile:
        logger.info("TLS certificate: %s", ssl_certfile)
    if workers != 1:
        logger.warning(
            "workers=%s requested, but EvilEye API currently uses shared in-process state. "
            "Falling back to a single worker.",
            workers,
        )
        workers = 1

    manager = get_pipeline_manager()
    logger.info("PipelineManager initialized")

    cleanup_called = False

    def cleanup():
        nonlocal cleanup_called
        if cleanup_called:
            return
        cleanup_called = True
        try:
            logger.info("API cleanup sequence initiated")
            manager.shutdown()
            logger.info("API cleanup completed")
        except Exception as e:
            logger.error(f"API cleanup error: {e}")

    def signal_handler(signum, _frame):
        logger.info(f"Received signal {signum}, initiating shutdown...")
        cleanup()
        raise SystemExit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    atexit.register(cleanup)
    logger.info("Registered signal handlers and atexit cleanup")

    logger.info("Creating FastAPI application...")
    app = build_app()
    logger.info("FastAPI application created successfully")

    if config:
        config_name = config
        logger.info(f"Autorun requested for config: {config_name}")
        try:
            mgr = get_config_run_manager()
            rid = len(mgr.list()) + 1
            cfg_path = Path(config_name)
            if cfg_path.exists():
                with open(cfg_path, "r", encoding="utf-8") as f:
                    body = json.load(f)
                desc = mgr.create(rid, cfg_path.stem, config_body=body)
            else:
                desc = mgr.create(rid, Path(config_name).stem, config_name=config_name)
            logger.info(f"Autorun created config run id={desc['id']}")
            effective_host = host if host != "0.0.0.0" else "127.0.0.1"
            api_base_url = f"{scheme}://{effective_host}:{port}/api/v1"
            mgr.start(desc["id"], api_base_url=api_base_url)
            logger.info(f"Autorun started config run id={desc['id']} (relay → {api_base_url})")
        except Exception as e:
            logger.error(f"Autorun failed: {e}")

    logger.info("=" * 60)
    logger.info("Starting uvicorn server...")
    logger.info("=" * 60)

    try:
        os.environ.setdefault("EVILEYE_HTTP_PORT", str(port))
        uvicorn_config = uvicorn.Config(
            app,
            host=host,
            port=port,
            log_level=effective_log_level,
            access_log=_uvicorn_access_log_enabled(),
            ssl_certfile=ssl_certfile,
            ssl_keyfile=ssl_keyfile,
            proxy_headers=True,
            timeout_keep_alive=5,
        )
        if reload:
            logger.warning("Reload mode is not supported when passing app instance directly")
        server = uvicorn.Server(uvicorn_config)
        server.run()
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
        cleanup()
    except Exception as e:
        logger.error(f"Server error: {e}")
        cleanup()
        raise


def _create_args_parser() -> argparse.ArgumentParser:
    pars = argparse.ArgumentParser(description="EvilEye API server wrapper")
    pars.add_argument("--host", type=str, default="127.0.0.1", help="Bind host")
    pars.add_argument("--port", type=int, default=8181, help="Bind port")
    pars.add_argument("--reload", action=argparse.BooleanOptionalAction, default=True,
                      help="Enable auto-reload (note: not supported with app instance)")
    pars.add_argument("--workers", type=int, default=1, help="Number of worker processes")
    pars.add_argument("--verbose", action="store_true", help="Enable verbose logging")
    pars.add_argument("--log-level", type=str, default="info",
                      choices=["critical", "error", "warning", "info", "debug", "trace"], help="Logging level")
    pars.add_argument("--config", type=str, default=None,
                      help="Autorun selected config (file path or name from configs/)")
    pars.add_argument("--ssl-certfile", type=str, default=None, help="Path to TLS certificate file (PEM)")
    pars.add_argument("--ssl-keyfile", type=str, default=None, help="Path to TLS private key file (PEM)")
    return pars


def main() -> None:
    """Main entry point for server.py"""
    parser = _create_args_parser()
    args = parser.parse_args()

    effective_log_level = "DEBUG" if args.verbose and args.log_level == "info" else args.log_level.upper()
    logger = setup_evileye_logging(log_level=effective_log_level, log_to_console=True, log_to_file=True)
    log_system_info(logger)

    try:
        run_api_server(
            host=args.host,
            port=args.port,
            reload=args.reload,
            log_level=args.log_level,
            config=args.config,
            workers=args.workers,
            verbose=args.verbose,
            ssl_certfile=args.ssl_certfile,
            ssl_keyfile=args.ssl_keyfile,
        )
    except Exception as e:
        logger.error(f"Failed to start server: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()
