import argparse
import json
import sys
import os
import asyncio
from pathlib import Path
try:
    from PyQt6 import QtCore
    from PyQt6.QtWidgets import QApplication
    pyqt_version = 6
except ImportError:
    from PyQt5 import QtCore
    from PyQt5.QtWidgets import QApplication
    pyqt_version = 5

from controller.async_controller import AsyncController
from visualization_modules.main_window import MainWindow
# import configurer.configurer_window as config

sys.path.append(str(Path(__file__).parent.parent.parent))

def restart():
    QtCore.QCoreApplication.quit()
    status = QtCore.QProcess.startDetached(sys.executable, sys.argv)
    print(status)

async def init_controller_async(file_path: str):
    """Асинхронная инициализация контроллера"""
    with open(file_path, 'r+') as params_file:
        params = json.load(params_file)

    controller_instance = AsyncController()
    await controller_instance.initialize(params)
    return controller_instance, params

def init_controller(file_path: str):
    """Синхронная обертка для обратной совместимости"""
    return asyncio.run(init_controller_async(file_path))

async def start_app_async(app, file_path: str, params: dict, controller_instance):
    """Асинхронный запуск приложения"""
    a = MainWindow(controller_instance, file_path, params, 1600, 720)
    
    # Адаптация для совместимости с AsyncController
    if hasattr(controller_instance, 'init_main_window'):
        controller_instance.init_main_window(a, a.slots, a.signals)
    
    if getattr(controller_instance, 'show_main_gui', True):
        a.show()

    if getattr(controller_instance, 'show_journal', False):
        a.open_journal()
    
    await controller_instance.start()

    ret = app.exec()
    await controller_instance.stop()
    sys.exit(ret)

def start_app(app, file_path: str, params: dict, controller_instance):
    """Синхронная обертка для обратной совместимости"""
    return asyncio.run(start_app_async(app, file_path, params, controller_instance))

async def create_app_async():
    """Асинхронное создание приложения"""
    controller_instance = AsyncController()
    params = dict()
    await controller_instance.initialize(params)
    controller_instance.save_params(params)
    current_directory = os.getcwd()
    file_name = os.path.join(current_directory, "config.json")
    with open(file_name, 'w', encoding='utf-8') as json_file:
        json.dump(params, json_file, ensure_ascii=False, indent=4)

    return file_name, controller_instance, params

def create_app():
    """Синхронная обертка для обратной совместимости"""
    return asyncio.run(create_app_async())

async def main_async():
    """Асинхронная основная функция"""
    parser = argparse.ArgumentParser()
    parser.add_argument('fullpath', help='Full path to json file with cameras and modules params',
                        type=str, default=None, nargs="?")
    args = parser.parse_args()
    config_path = ''
    if args.fullpath is None:
        config_path = args.fullpath

    app = QApplication(sys.argv)

    if config_path:
        controller, params = await init_controller_async(config_path)
    else:
        config_path, controller, params = await create_app_async()
    
    await start_app_async(app, config_path, params, controller)

if __name__ == "__main__":
    asyncio.run(main_async())
