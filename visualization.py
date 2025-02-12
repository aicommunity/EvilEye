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
    if args.fullpath is None:
        params_file = open('samples/video_file.json')
    else:
        params_file = open(args.fullpath)
    data = json.load(params_file)
    app = QApplication(sys.argv)
    a = MainWindow(data, 1280, 720)
    a.show()
    ret = app.exec()
    sys.exit(ret)