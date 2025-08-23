import argparse
import json
import sys
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

from evileye.visualization_modules.configurer import configurer_window as config
from evileye.utils.utils import normalize_config_path

def start_configurer(config_file_name):
    app = QApplication(sys.argv)
    a = config.ConfigurerMainWindow(config_file_name, 1280, 720)
    a.show()
    ret = app.exec()
    sys.exit(ret)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('fullpath', help='Full path to json file with cameras and modules params',
                        type=str, default=None, nargs="?")
    args = parser.parse_args()
    config_path = ''
    if args.fullpath:
        config_path = normalize_config_path(args.fullpath)
    start_configurer(config_path)
