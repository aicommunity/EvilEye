"""
Save Confirmation Dialog for EvilEye GUI

Диалог подтверждения сохранения изменений при закрытии окна.
"""

from enum import Enum
from typing import Optional

try:
    from PyQt6.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
        QMessageBox, QTextEdit, QCheckBox
    )
    from PyQt6.QtCore import Qt, pyqtSignal, pyqtSlot
    from PyQt6.QtGui import QIcon, QPixmap
    pyqt_version = 6
except ImportError:
    from PyQt5.QtWidgets import (
        QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, 
        QMessageBox, QTextEdit, QCheckBox
    )
    from PyQt5.QtCore import Qt, pyqtSignal, pyqtSlot
    from PyQt5.QtGui import QIcon, QPixmap
    pyqt_version = 5

from ...core.logger import get_module_logger


class SaveAction(Enum):
    """Действия для диалога сохранения"""
    SAVE = "save"
    DISCARD = "discard"
    CANCEL = "cancel"


class SaveConfirmationDialog(QDialog):
    """
    Диалог подтверждения сохранения изменений.
    
    Показывается при попытке закрыть окно с несохраненными изменениями.
    Предлагает пользователю сохранить изменения, отменить их или отменить закрытие.
    """
    
    # Сигнал с результатом диалога
    action_selected = pyqtSignal(SaveAction)
    
    def __init__(self, window_title: str, config_file: Optional[str] = None, 
                 parent=None):
        """
        Инициализация диалога.
        
        Args:
            window_title: Заголовок окна с несохраненными изменениями
            config_file: Путь к файлу конфигурации (если применимо)
            parent: Родительский виджет
        """
        super().__init__(parent)
        
        self.logger = get_module_logger("save_confirmation_dialog")
        self.window_title = window_title
        self.config_file = config_file
        self.selected_action = SaveAction.CANCEL
        
        self._init_ui()
        self._connect_signals()
        
        self.logger.debug(f"SaveConfirmationDialog created for window: {window_title}")
    
    def _init_ui(self) -> None:
        """Инициализация пользовательского интерфейса"""
        self.setWindowTitle("Несохраненные изменения")
        self.setModal(True)
        self.setFixedSize(450, 200)
        
        # Основной layout
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # Иконка и основной текст
        icon_layout = QHBoxLayout()
        
        # Иконка предупреждения
        warning_icon = QLabel()
        warning_pixmap = self.style().standardIcon(
            self.style().StandardPixmap.SP_MessageBoxWarning
        ).pixmap(32, 32)
        warning_icon.setPixmap(warning_pixmap)
        icon_layout.addWidget(warning_icon)
        
        # Основной текст
        main_text = QLabel()
        main_text.setText(f"В окне '{self.window_title}' есть несохраненные изменения.")
        main_text.setWordWrap(True)
        main_text.setStyleSheet("font-weight: bold; font-size: 12px;")
        icon_layout.addWidget(main_text)
        icon_layout.addStretch()
        
        main_layout.addLayout(icon_layout)
        
        # Дополнительная информация
        info_text = QLabel()
        if self.config_file:
            info_text.setText(f"Файл конфигурации: {self.config_file}")
        else:
            info_text.setText("Хотите сохранить изменения перед закрытием?")
        info_text.setWordWrap(True)
        info_text.setStyleSheet("color: #666; font-size: 11px;")
        main_layout.addWidget(info_text)
        
        # Чекбокс "Больше не спрашивать" (опционально)
        self.remember_checkbox = QCheckBox("Больше не спрашивать для этого окна")
        self.remember_checkbox.setStyleSheet("font-size: 10px; color: #666;")
        main_layout.addWidget(self.remember_checkbox)
        
        # Кнопки
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        # Кнопка "Сохранить"
        self.save_button = QPushButton("Сохранить")
        self.save_button.setDefault(True)
        self.save_button.setStyleSheet("""
            QPushButton {
                background-color: #0078d4;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #106ebe;
            }
            QPushButton:pressed {
                background-color: #005a9e;
            }
        """)
        button_layout.addWidget(self.save_button)
        
        # Кнопка "Не сохранять"
        self.discard_button = QPushButton("Не сохранять")
        self.discard_button.setStyleSheet("""
            QPushButton {
                background-color: #d13438;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #b52d31;
            }
            QPushButton:pressed {
                background-color: #9a2529;
            }
        """)
        button_layout.addWidget(self.discard_button)
        
        # Кнопка "Отмена"
        self.cancel_button = QPushButton("Отмена")
        self.cancel_button.setStyleSheet("""
            QPushButton {
                background-color: #f3f2f1;
                color: #323130;
                border: 1px solid #8a8886;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #edebe9;
            }
            QPushButton:pressed {
                background-color: #e1dfdd;
            }
        """)
        button_layout.addWidget(self.cancel_button)
        
        main_layout.addLayout(button_layout)
    
    def _connect_signals(self) -> None:
        """Подключение сигналов кнопок"""
        self.save_button.clicked.connect(self._on_save_clicked)
        self.discard_button.clicked.connect(self._on_discard_clicked)
        self.cancel_button.clicked.connect(self._on_cancel_clicked)
    
    @pyqtSlot()
    def _on_save_clicked(self) -> None:
        """Обработка нажатия кнопки 'Сохранить'"""
        self.selected_action = SaveAction.SAVE
        self.action_selected.emit(SaveAction.SAVE)
        self.accept()
    
    @pyqtSlot()
    def _on_discard_clicked(self) -> None:
        """Обработка нажатия кнопки 'Не сохранять'"""
        self.selected_action = SaveAction.DISCARD
        self.action_selected.emit(SaveAction.DISCARD)
        self.accept()
    
    @pyqtSlot()
    def _on_cancel_clicked(self) -> None:
        """Обработка нажатия кнопки 'Отмена'"""
        self.selected_action = SaveAction.CANCEL
        self.action_selected.emit(SaveAction.CANCEL)
        self.reject()
    
    def get_selected_action(self) -> SaveAction:
        """
        Получить выбранное действие.
        
        Returns:
            Выбранное действие
        """
        return self.selected_action
    
    def should_remember_choice(self) -> bool:
        """
        Проверить, выбрал ли пользователь "Больше не спрашивать".
        
        Returns:
            True если пользователь выбрал не спрашивать в будущем
        """
        return self.remember_checkbox.isChecked()
    
    @staticmethod
    def show_dialog(window_title: str, config_file: Optional[str] = None, 
                   parent=None) -> tuple[SaveAction, bool]:
        """
        Статический метод для показа диалога.
        
        Args:
            window_title: Заголовок окна с несохраненными изменениями
            config_file: Путь к файлу конфигурации (если применимо)
            parent: Родительский виджет
            
        Returns:
            Кортеж (выбранное_действие, запомнить_выбор)
        """
        dialog = SaveConfirmationDialog(window_title, config_file, parent)
        result = dialog.exec()
        
        if result == QDialog.DialogCode.Accepted:
            return dialog.get_selected_action(), dialog.should_remember_choice()
        else:
            return SaveAction.CANCEL, False


class SaveAsDialog(QDialog):
    """
    Диалог "Сохранить как" для сохранения конфигурации под новым именем.
    """
    
    # Сигнал с результатом диалога
    file_selected = pyqtSignal(str)  # file_path
    
    def __init__(self, current_file: Optional[str] = None, parent=None):
        """
        Инициализация диалога.
        
        Args:
            current_file: Текущий файл конфигурации
            parent: Родительский виджет
        """
        super().__init__(parent)
        
        self.logger = get_module_logger("save_as_dialog")
        self.current_file = current_file
        self.selected_file = None
        
        self._init_ui()
        self._connect_signals()
        
        self.logger.debug("SaveAsDialog created")
    
    def _init_ui(self) -> None:
        """Инициализация пользовательского интерфейса"""
        self.setWindowTitle("Сохранить как")
        self.setModal(True)
        self.setFixedSize(500, 150)
        
        # Основной layout
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # Заголовок
        title_label = QLabel("Выберите место для сохранения конфигурации:")
        title_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        main_layout.addWidget(title_label)
        
        # Поле для ввода пути к файлу
        file_layout = QHBoxLayout()
        
        self.file_path_edit = QTextEdit()
        self.file_path_edit.setMaximumHeight(30)
        self.file_path_edit.setPlaceholderText("Введите путь к файлу или нажмите 'Обзор...'")
        
        if self.current_file:
            # Предлагаем имя на основе текущего файла
            from pathlib import Path
            current_path = Path(self.current_file)
            suggested_name = current_path.stem + "_copy" + current_path.suffix
            self.file_path_edit.setPlainText(str(current_path.parent / suggested_name))
        
        file_layout.addWidget(self.file_path_edit)
        
        # Кнопка "Обзор"
        self.browse_button = QPushButton("Обзор...")
        self.browse_button.setStyleSheet("""
            QPushButton {
                background-color: #0078d4;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #106ebe;
            }
        """)
        file_layout.addWidget(self.browse_button)
        
        main_layout.addLayout(file_layout)
        
        # Кнопки
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        # Кнопка "Сохранить"
        self.save_button = QPushButton("Сохранить")
        self.save_button.setDefault(True)
        self.save_button.setStyleSheet("""
            QPushButton {
                background-color: #0078d4;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #106ebe;
            }
        """)
        button_layout.addWidget(self.save_button)
        
        # Кнопка "Отмена"
        self.cancel_button = QPushButton("Отмена")
        self.cancel_button.setStyleSheet("""
            QPushButton {
                background-color: #f3f2f1;
                color: #323130;
                border: 1px solid #8a8886;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #edebe9;
            }
        """)
        button_layout.addWidget(self.cancel_button)
        
        main_layout.addLayout(button_layout)
    
    def _connect_signals(self) -> None:
        """Подключение сигналов"""
        self.browse_button.clicked.connect(self._on_browse_clicked)
        self.save_button.clicked.connect(self._on_save_clicked)
        self.cancel_button.clicked.connect(self._on_cancel_clicked)
    
    @pyqtSlot()
    def _on_browse_clicked(self) -> None:
        """Обработка нажатия кнопки 'Обзор'"""
        if pyqt_version == 6:
            from PyQt6.QtWidgets import QFileDialog
        else:
            from PyQt5.QtWidgets import QFileDialog
        
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить конфигурацию как",
            self.file_path_edit.toPlainText() or "configs/",
            "JSON Files (*.json);;All Files (*)"
        )
        
        if file_path:
            self.file_path_edit.setPlainText(file_path)
    
    @pyqtSlot()
    def _on_save_clicked(self) -> None:
        """Обработка нажатия кнопки 'Сохранить'"""
        file_path = self.file_path_edit.toPlainText().strip()
        
        if not file_path:
            QMessageBox.warning(self, "Ошибка", "Пожалуйста, выберите файл для сохранения.")
            return
        
        # Проверяем расширение файла
        if not file_path.endswith('.json'):
            file_path += '.json'
            self.file_path_edit.setPlainText(file_path)
        
        self.selected_file = file_path
        self.file_selected.emit(file_path)
        self.accept()
    
    @pyqtSlot()
    def _on_cancel_clicked(self) -> None:
        """Обработка нажатия кнопки 'Отмена'"""
        self.reject()
    
    def get_selected_file(self) -> Optional[str]:
        """
        Получить выбранный файл.
        
        Returns:
            Путь к выбранному файлу или None
        """
        return self.selected_file
    
    @staticmethod
    def show_dialog(current_file: Optional[str] = None, parent=None) -> Optional[str]:
        """
        Статический метод для показа диалога.
        
        Args:
            current_file: Текущий файл конфигурации
            parent: Родительский виджет
            
        Returns:
            Путь к выбранному файлу или None если отменено
        """
        dialog = SaveAsDialog(current_file, parent)
        result = dialog.exec()
        
        if result == QDialog.DialogCode.Accepted:
            return dialog.get_selected_file()
        else:
            return None
