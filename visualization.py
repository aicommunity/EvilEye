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

sys.path.append(str(Path(__file__).parent.parent.parent))

def restart():
    QtCore.QCoreApplication.quit()
    status = QtCore.QProcess.startDetached(sys.executable, sys.argv)
    print(status)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('fullpath', help='Full path to json file with cameras and modules params',
                        type=str, default=None, nargs="?")
    args = parser.parse_args()
    file_path = 'samples/visual_sample.json'
    if args.fullpath is not None:
        file_path = args.fullpath

    with open(file_path, 'r+') as params_file:
        data = json.load(params_file)
    app = QApplication(sys.argv)
    a = MainWindow(file_path, data, 1600, 720)
    a.show()
    ret = app.exec()
    if a.controller.restart_flag:
        restart()
    sys.exit(ret)