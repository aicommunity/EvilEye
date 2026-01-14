"""
Окно с прогресс-баром для отображения процесса инициализации приложения
"""

try:
    from PyQt6.QtWidgets import (
        QWidget, QLabel, QVBoxLayout, QProgressBar, QDialog
    )
    from PyQt6.QtCore import Qt, pyqtSignal
    from PyQt6.QtGui import QFont
    pyqt_version = 6
except ImportError:
    from PyQt5.QtWidgets import (
        QWidget, QLabel, QVBoxLayout, QProgressBar, QDialog
    )
    from PyQt5.QtCore import Qt, pyqtSignal
    from PyQt5.QtGui import QFont
    pyqt_version = 5

from ..core.logger import get_module_logger


class StartupProgressWindow(QDialog):
    """Окно с прогресс-баром для отображения процесса запуска приложения"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = get_module_logger("startup_progress")
        self.setup_ui()
        
    def setup_ui(self):
        """Настройка интерфейса окна"""
        self.setWindowTitle("Starting EvilEye")
        self.setFixedSize(500, 150)
        # Делаем окно немодальным, чтобы не блокировать GUI
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.MSWindowsFixedSizeDialogHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setModal(False)  # Явно делаем немодальным
        
        # Главный layout
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # Заголовок
        title_label = QLabel("Initializing application...")
        title_font = QFont()
        title_font.setPointSize(12)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title_label)
        
        # Текущий этап
        self.stage_label = QLabel("Preparing...")
        self.stage_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.stage_label)
        
        # Прогресс-бар
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        main_layout.addWidget(self.progress_bar)
        
        # Центрирование окна на экране
        self.center_on_screen()
        
    def center_on_screen(self):
        """Центрировать окно на экране"""
        try:
            from PyQt6.QtWidgets import QApplication
        except ImportError:
            from PyQt5.QtWidgets import QApplication
            
        app = QApplication.instance()
        if app:
            screen = app.primaryScreen()
            if screen:
                screen_geometry = screen.geometry()
                window_geometry = self.frameGeometry()
                center_point = screen_geometry.center()
                window_geometry.moveCenter(center_point)
                self.move(window_geometry.topLeft())
    
    def update_progress(self, value: int, stage_text: str = None):
        """
        Обновить прогресс-бар и текст этапа
        
        Args:
            value: Значение прогресса (0-100)
            stage_text: Текст текущего этапа (опционально)
        """
        self.progress_bar.setValue(value)
        if stage_text:
            self.stage_label.setText(stage_text)
        self.logger.debug(f"Progress updated: {value}% - {stage_text}")
        
    def set_stage(self, stage_text: str):
        """
        Установить текст текущего этапа
        
        Args:
            stage_text: Текст этапа
        """
        self.stage_label.setText(stage_text)
        self.logger.debug(f"Stage set: {stage_text}")
