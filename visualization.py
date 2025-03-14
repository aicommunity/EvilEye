import argparse
import json
import sys
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from visualization_modules.main_window import MainWindow

sys.path.append(str(Path(__file__).parent.parent.parent))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('fullpath', help='Full path to json file with cameras and modules params',
                        type=str, default=None, nargs="?")
    args = parser.parse_args()
    file_path = 'samples/video_file.json'
    if args.fullpath is None:
        with open(file_path, 'r+') as params_file:
            data = json.load(params_file)
    else:
        with open(file_path, 'r+') as params_file:
            data = json.load(params_file)
    app = QApplication(sys.argv)
    a = MainWindow(file_path, data, 1280, 720)
    a.show()
    ret = app.exec()
    sys.exit(ret)