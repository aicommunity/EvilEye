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


from visualization_modules.main_window import MainWindow
import configurer.configurer_window as config

sys.path.append(str(Path(__file__).parent.parent.parent))

def restart():
    QtCore.QCoreApplication.quit()
    status = QtCore.QProcess.startDetached(sys.executable, sys.argv)
    print(status)

def start_app(file_path: str):
    with open(file_path, 'r+') as params_file:
        data = json.load(params_file)
    app = QApplication(sys.argv)
    a = MainWindow(file_path, data, 1600, 720)
    a.show()
    ret = app.exec()
    sys.exit(ret)


def start_configurer():
    app = QApplication(sys.argv)
    a = config.ConfigurerMainWindow(1280, 720)
    a.show()
    ret = app.exec()
    sys.exit(ret)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('fullpath', help='Full path to json file with cameras and modules params',
                        type=str, default=None, nargs="?")
    args = parser.parse_args()
    config_path = 'samples/visual_sample.json'
    if args.fullpath is None:
        if config_path:
            start_app(config_path)
        else:
            start_configurer()
    else:
        start_app(args.fullpath)
