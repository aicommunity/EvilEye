import atexit
import argparse
import signal
import uvicorn
from fastapi import FastAPI

from evileye.api.app import create_app
from evileye.core.logger import get_module_logger
from evileye.api.core.manager_access import get_manager


def build_app() -> FastAPI:
    return create_app()


def run_api_server(host: str = "127.0.0.1", port: int = 8080, reload: bool = True, log_level: str = "info") -> None:
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

    logger.info("=" * 60)
    logger.info("Starting uvicorn server...")
    logger.info("=" * 60)

    try:
        config = uvicorn.Config(app, host=host, port=port, log_level=log_level)
        if reload:
            logger.warning("Reload mode is not supported when passing app instance directly")
        server = uvicorn.Server(config)
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
    return pars


def main() -> None:
    parser = _create_args_parser()
    args = parser.parse_args()
    run_api_server(host=args.host, port=args.port, reload=args.reload, log_level=args.log_level)


