import argparse
import json
import sys
import os
from pathlib import Path
try:
    from PyQt6 import QtCore
    from PyQt6.QtWidgets import QApplication
    pyqt_version = 6
except ImportError:
    from PyQt5 import QtCore
    from PyQt5.QtWidgets import QApplication
    pyqt_version = 5

from controller import controller
from visualization_modules.main_window import MainWindow
# import configurer.configurer_window as config

sys.path.append(str(Path(__file__).parent.parent.parent))

def restart():
    QtCore.QCoreApplication.quit()
    status = QtCore.QProcess.startDetached(sys.executable, sys.argv)
    print(status)

def init_controller(file_path: str):
    with open(file_path, 'r+') as params_file:
        params = json.load(params_file)

    controller_instance = controller.Controller()
    controller_instance.init(params)
    return controller_instance, params

def start_app(app, file_path: str, params: dict,  controller_instance):
    a = MainWindow(controller_instance, file_path, params, 1600, 720)
    controller_instance.init_main_window(a, a.slots, a.signals)
    if controller_instance.show_main_gui:
        a.show()

    if controller_instance.show_journal:
        a.open_journal()
    controller_instance.start()


    ret = app.exec()
    sys.exit(ret)

def create_app():
    controller_instance = controller.Controller()
    params = dict()
    controller_instance.init(params)
    controller_instance.save_params(params)
    current_directory = os.getcwd()
    file_name = os.path.join(current_directory, "config.json")
    with open(file_name, 'w', encoding='utf-8') as json_file:
        json.dump(params, json_file, ensure_ascii=False, indent=4)

    return file_name, controller_instance, params

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('fullpath', help='Full path to json file with cameras and modules params',
                        type=str, default=None, nargs="?")
    args = parser.parse_args()
    config_path = ''
    if args.fullpath is None:
        config_path = args.fullpath

    app = QApplication(sys.argv)

    if config_path:
        controller, params = init_controller(config_path)
    else:
        config_path, controller, params = create_app()
    start_app(app, config_path, params, controller)
