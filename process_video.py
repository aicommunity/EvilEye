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

from controller import controller
from visualization_modules.main_window import MainWindow

file_path = 'samples/vehicle_perpocessing.json'

sys.path.append(str(Path(__file__).parent.parent.parent))

def create_args_parser():
    pars = argparse.ArgumentParser()
    pars.add_argument('--video', nargs='?', const="1", type=str,
                      help="file name for processing")
    pars.add_argument('--config', nargs='?', const="1", type=str,
                      help="system configuration")
    pars.add_argument('--gui', action=argparse.BooleanOptionalAction, default=True,
                      help="Show gui when processing")
    pars.add_argument('--autoclose', action=argparse.BooleanOptionalAction, default=False,
                      help="Automatic close application when video ends")
    pars.add_argument('--sources_preset', nargs='?', const="", type=str,
                      help="Use preset for multiple video sources")

    result = pars.parse_args()
    return result


if __name__ == "__main__":
    args = create_args_parser()

    print(f"Launch system with CLI arguments: {args}")

    if args.config is None and args.video is None:
        print("Video file doesn't set")
        exit(1)

    use_default_config = True
    video_file = None
    if args.config is not None:
        config_file_name = args.config
        use_default_config = False
        print(f"Using configuration from {config_file_name}")
    else:
        if args.sources_preset is not None:
            print(f"Sources presets doesn't supports now")
            config_file_name = 'samples/video_file.json'
            print(f"Using default configuration from {config_file_name}")
        else:
            config_file_name = 'samples/video_file.json'
            print(f"Using default configuration from {config_file_name}")

    with open(config_file_name) as config_file:
        config_data = json.load(config_file)

    if args.video is not None:
        video_file = args.video
        config_data["sources"][0]["camera"] = video_file
        print(f"Using video source file from cli: {video_file}")
    else:
        video_file = config_data["sources"][0]["camera"]
        print(f"Using video source file from config: {video_file}")

    if not args.gui:
        config_data["visualizer"]["gui_enabled"] = False
    else:
        config_data["visualizer"]["gui_enabled"] = True

    if args.autoclose:
        sources = config_data["sources"]
        for source in sources:
            source["loop_play"] = False
        config_data["autoclose"] = True

    app = QApplication(sys.argv)

    controller_instance = controller.Controller()
    controller_instance.init(config_data)

    a = MainWindow(controller_instance, file_path, config_data, 1600, 720)
    controller_instance.init_main_window(a, a.slots, a.signals)
    if controller_instance.show_main_gui:
        a.show()

    if controller_instance.show_journal:
        a.open_journal()
    controller_instance.start()

    ret = app.exec()
    sys.exit(ret)