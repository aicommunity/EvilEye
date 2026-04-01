import argparse
import os
import sys
import tempfile
from pathlib import Path

try:
    from PyQt6 import QtCore
    from PyQt6.QtWidgets import QApplication
    pyqt_version = 6
except ImportError:
    from PyQt5 import QtCore
    from PyQt5.QtWidgets import QApplication
    pyqt_version = 5

# Add project root to path for imports when running as script
sys.path.insert(0, str(Path(__file__).parent.parent))

from evileye.core.logging_config import setup_evileye_logging, log_system_info
from evileye.api.core.runtime_registry import allocate_pipeline_id, mark_runtime_stopped, register_runtime

def create_args_parser():
    pars = argparse.ArgumentParser()
    pars.add_argument('--config', nargs='?', const="1", type=str,
                      help="system configuration")
    pars.add_argument('--gui', action=argparse.BooleanOptionalAction, default=True,
                      help="Show gui when processing")
    pars.add_argument('--autoclose', action=argparse.BooleanOptionalAction, default=False,
                      help="Automatic close application when video ends")
    pars.add_argument('--sources_preset', nargs='?', const="", type=str,
                      help="Use preset for multiple video sources")
    # Recording is configured only via config file; no CLI overrides
    pars.add_argument('--log-level', type=str, default="INFO",
                      help="Log level: DEBUG, INFO, WARNING, ERROR")

    result = pars.parse_args()
    return result




def run_config(config_path: str, gui: bool = True, autoclose: bool = False) -> int:
    from evileye.run_config_helper import run_config as _run
    return _run(config_path=config_path, gui=gui, autoclose=autoclose)


def main():
    """Main entry point for the EvilEye process application"""
    args = create_args_parser()
    # Инициализация логирования после парсинга аргументов
    logger = setup_evileye_logging(log_level=args.log_level.upper(), log_to_console=True, log_to_file=True)

    logger.info(f"Starting system with CLI arguments: {args}")
    log_system_info(logger)

    if args.config is None:
        logger.error("Configuration file not specified")
        sys.exit(1)

    pipeline_id = os.environ.get("EVILEYE_PIPELINE_ID")
    if not pipeline_id:
        pipeline_id = str(allocate_pipeline_id())
        os.environ["EVILEYE_PIPELINE_ID"] = pipeline_id

    frame_dir = os.environ.get("EVILEYE_FRAME_DIR")
    if not frame_dir:
        frame_dir = str(Path(tempfile.gettempdir()) / "evileye_frames" / pipeline_id)
        os.environ["EVILEYE_FRAME_DIR"] = frame_dir

    Path(frame_dir).mkdir(parents=True, exist_ok=True)
    config_path = str(Path(args.config).resolve())
    config_name = Path(config_path).stem

    register_runtime(
        rid=int(pipeline_id),
        pid=os.getpid(),
        config_path=config_path,
        name=os.environ.get("EVILEYE_PIPELINE_NAME") or config_name,
        frame_dir=frame_dir,
        source="process",
        managed=os.environ.get("EVILEYE_MANAGED_RUN") == "1",
        state="starting",
    )

    try:
        ret = run_config(args.config, gui=args.gui, autoclose=args.autoclose)
    except Exception as exc:
        mark_runtime_stopped(int(pipeline_id), error=str(exc))
        raise
    else:
        mark_runtime_stopped(int(pipeline_id))
        sys.exit(ret)


if __name__ == "__main__":
    main()