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

import configurer.configurer_window as config

sys.path.append(str(Path(__file__).parent.parent.parent))

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
    config_path = 'samples/visual_sample.json'
    if args.fullpath:
        config_path = args.fullpath
    start_configurer(config_path)
