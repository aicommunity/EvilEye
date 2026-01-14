import argparse
import json
import sys
import os
from pathlib import Path
import onnxruntime as ort
import atexit
import signal

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

from evileye.controller import controller
from evileye.visualization_modules.main_window import MainWindow
from evileye.utils.utils import normalize_config_path
from evileye.core.logging_config import setup_evileye_logging, log_system_info
from evileye.core.logger import get_module_logger

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

    ret = run_config(args.config, gui=args.gui, autoclose=args.autoclose)
    sys.exit(ret)


if __name__ == "__main__":
    main()