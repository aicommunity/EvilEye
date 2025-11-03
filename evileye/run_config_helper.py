import json
import os
import sys
from pathlib import Path

try:
    from PyQt6.QtWidgets import QApplication
except ImportError:
    from PyQt5.QtWidgets import QApplication

from evileye.controller import controller
from evileye.visualization_modules.main_window import MainWindow
from evileye.utils.utils import normalize_config_path
from evileye.core.logger import get_module_logger


def run_config(config_path: str, gui: bool = True, autoclose: bool = False) -> int:
    """Run EvilEye configuration using provided configuration.

    Returns Qt application exit code.
    """
    logger = get_module_logger("run_config")

    config_file_name = normalize_config_path(config_path)
    config_dir = os.path.dirname(os.path.abspath(config_file_name))
    if config_dir:
        if os.path.basename(config_dir) == 'configs':
            parent_dir = os.path.dirname(config_dir)
            os.chdir(parent_dir)
            logger.info(f"Changed working directory to parent of configs folder: {parent_dir}")
        else:
            os.chdir(config_dir)
            logger.info(f"Changed working directory to: {config_dir}")

    with open(config_file_name) as config_file:
        config_data = json.load(config_file)

    logger.info("Configuration loaded successfully")

    if "controller" not in config_data:
        config_data["controller"] = {}
    if not gui:
        config_data["controller"]["gui_enabled"] = False
        config_data["controller"]["show_main_gui"] = False
        logger.info("GUI disabled")
    else:
        config_data["controller"]["gui_enabled"] = True
        logger.info("GUI enabled")

    if autoclose:
        sources = config_data.get("pipeline", {}).get("sources", [])
        for source in sources:
            source["loop_play"] = False
        config_data["autoclose"] = True
        logger.info("Auto-close enabled")

    logger.info("Creating controller")
    controller_instance = controller.Controller()
    controller_instance.init(config_data)

    logger.info("Initializing PyQt application (headless-safe)")
    qt_app = QApplication.instance() or QApplication(sys.argv)

    logger.info("Creating main window (no-show in headless mode)")
    a = MainWindow(controller_instance, config_file_name, config_data, 1600, 720)
    controller_instance.init_main_window(a, a.slots, a.signals)
    if gui and controller_instance.show_main_gui:
        a.show()
        logger.info("Main window displayed")
        if controller_instance.show_journal:
            a.open_journal()
            logger.info("Journal opened")

    logger.info("Starting controller")
    controller_instance.start()

    logger.info("Starting main application loop")
    ret = qt_app.exec()
    logger.info(f"Application finished with code: {ret}")
    return ret


