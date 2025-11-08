import atexit
import argparse
import json
import sys
from pathlib import Path
import signal
import uvicorn
from fastapi import FastAPI

# Add project root to path for imports when running as script
sys.path.insert(0, str(Path(__file__).parent.parent))

from evileye.api.app import create_app
from evileye.core.logger import get_module_logger
from evileye.core.logging_config import setup_evileye_logging, log_system_info
from evileye.api.core.manager_access import get_manager
from evileye.api.core.config_run_access import get_config_run_manager


def build_app() -> FastAPI:
    return create_app()


def run_api_server(host: str = "127.0.0.1", port: int = 8080, reload: bool = True, log_level: str = "info", config: str | None = None) -> None:
    logger = get_module_logger("server")
    logger.info("=" * 60)
    logger.info("EvilEye API Server Initialization")
    logger.info("=" * 60)
    logger.info(f"Starting EvilEye API server on {host}:{port}")
    logger.info(f"API documentation will be available at http://{host}:{port}/docs")

    manager = get_manager()
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

    # Optional autorun of a config immediately (avoids reliance on startup events)
    if config:
        config_name = config  # Save to avoid shadowing
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
            mgr.start(desc["id"]) 
            logger.info(f"Autorun started config run id={desc['id']}")
        except Exception as e:
            logger.error(f"Autorun failed: {e}")

    logger.info("=" * 60)
    logger.info("Starting uvicorn server...")
    logger.info("=" * 60)

    try:
        uvicorn_config = uvicorn.Config(app, host=host, port=port, log_level=log_level)
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
    pars.add_argument("--port", type=int, default=8080, help="Bind port")
    pars.add_argument("--reload", action=argparse.BooleanOptionalAction, default=True, help="Enable auto-reload (note: not supported with app instance)")
    pars.add_argument("--log-level", type=str, default="info", choices=["critical", "error", "warning", "info", "debug", "trace"], help="Logging level")
    pars.add_argument("--config", type=str, default=None, help="Autorun selected config (file path or name from configs/)")
    return pars


def main() -> None:
    """Main entry point for server.py"""
    parser = _create_args_parser()
    args = parser.parse_args()
    
    # Initialize logging before anything else
    logger = setup_evileye_logging(log_level=args.log_level.upper(), log_to_console=True, log_to_file=True)
    log_system_info(logger)
    
    try:
        run_api_server(host=args.host, port=args.port, reload=args.reload, log_level=args.log_level, config=args.config)
    except Exception as e:
        logger.error(f"Failed to start server: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    main()


