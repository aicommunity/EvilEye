"""
Поток для инициализации контроллера с обновлением прогресса
"""

try:
    from PyQt6.QtCore import QThread, pyqtSignal
    pyqt_version = 6
except ImportError:
    from PyQt5.QtCore import QThread, pyqtSignal
    pyqt_version = 5

from ..controller import controller
from ..core.logger import get_module_logger


class ControllerInitThread(QThread):
    """Поток для инициализации контроллера в фоновом режиме"""
    
    # Сигналы для обновления прогресса
    progress_updated = pyqtSignal(int, str)  # value, stage_text
    initialization_complete = pyqtSignal(object)  # controller_instance
    initialization_failed = pyqtSignal(str)  # error_message
    
    def __init__(self, config_data):
        super().__init__()
        self.config_data = config_data
        self.controller_instance = None
        self.logger = get_module_logger("controller_init_thread")
        
    def run(self):
        """Выполнить инициализацию контроллера с обновлением прогресса"""
        try:
            self.progress_updated.emit(5, "Creating controller...")
            
            # Создание контроллера
            self.logger.info("Creating controller instance")
            self.controller_instance = controller.Controller()
            
            # Вызываем init() контроллера
            self.controller_instance.init(self.config_data)
            
            # Отправляем сигнал об успешном завершении
            self.initialization_complete.emit(self.controller_instance)
            
        except Exception as e:
            error_msg = f"Initialization error: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            self.initialization_failed.emit(error_msg)
