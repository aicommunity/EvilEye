"""
Base Window class for EvilEye GUI

Базовый класс для всех окон GUI приложения.
Обеспечивает общую функциональность и интеграцию с WindowManager.
"""

import json
from pathlib import Path
from typing import Optional, Dict, Any, Callable
from abc import ABC, abstractmethod

try:
    from PyQt6.QtWidgets import QWidget, QMainWindow, QMessageBox, QVBoxLayout
    from PyQt6.QtCore import pyqtSignal, pyqtSlot, Qt
    from PyQt6.QtGui import QCloseEvent
    pyqt_version = 6
except ImportError:
    from PyQt5.QtWidgets import QWidget, QMainWindow, QMessageBox, QVBoxLayout
    from PyQt5.QtCore import pyqtSignal, pyqtSlot, Qt
    from PyQt5.QtGui import QCloseEvent
    pyqt_version = 5

from ..core.logger import get_module_logger
from .window_manager import WindowManager, WindowState, get_window_manager


class BaseWindow(QWidget):
    """
    Базовый класс для всех окон EvilEye GUI.
    
    Предоставляет общую функциональность:
    - Интеграция с WindowManager
    - Обработка событий закрытия с проверкой несохраненных изменений
    - Сохранение/восстановление геометрии окна
    - Управление состоянием окна
    """
    
    # Сигналы для уведомления о событиях
    window_closing = pyqtSignal()
    window_closed = pyqtSignal()
    unsaved_changes_changed = pyqtSignal(bool)
    config_changed = pyqtSignal(str)  # config_file_path
    
    def __init__(self, window_id: str, window_type: str, 
                 config_file: Optional[str] = None,
                 parent: Optional[QWidget] = None):
        """
        Инициализация базового окна.
        
        Args:
            window_id: Уникальный идентификатор окна
            window_type: Тип окна (main, configurer, journal, zone, etc.)
            config_file: Путь к файлу конфигурации (если применимо)
            parent: Родительский виджет
        """
        super().__init__(parent)
        
        self.logger = get_module_logger(f"base_window.{window_type}")
        self.window_id = window_id
        self.window_type = window_type
        self.config_file = config_file
        self._has_unsaved_changes = False
        self._window_manager: Optional[WindowManager] = None
        
        # Инициализация базовых настроек
        self._init_base_settings()
        
        # Регистрация в WindowManager
        self._register_with_manager()
        
        self.logger.info(f"BaseWindow initialized: {window_id} ({window_type})")
    
    def _init_base_settings(self) -> None:
        """Инициализация базовых настроек окна"""
        # Устанавливаем базовые свойства окна
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        
        # Создаем основной layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Устанавливаем минимальный размер
        self.setMinimumSize(400, 300)
    
    def _register_with_manager(self) -> None:
        """Регистрация окна в WindowManager"""
        try:
            self._window_manager = get_window_manager()
            self._window_manager.register_window(
                window_id=self.window_id,
                window_type=self.window_type,
                window_instance=self,
                config_file=self.config_file
            )
            
            # Подключаем сигналы менеджера
            self._connect_manager_signals()
            
        except Exception as e:
            self.logger.error(f"Failed to register with WindowManager: {e}")
    
    def _connect_manager_signals(self) -> None:
        """Подключение сигналов WindowManager"""
        if not self._window_manager:
            return
        
        # Подключаем сигналы для синхронизации состояния
        self._window_manager.window_state_changed.connect(self._on_manager_state_changed)
        self._window_manager.config_changed.connect(self._on_config_changed)
    
    @pyqtSlot(str, WindowState)
    def _on_manager_state_changed(self, window_id: str, new_state: WindowState) -> None:
        """Обработка изменения состояния окна через менеджер"""
        if window_id == self.window_id:
            self.logger.debug(f"Window state changed to: {new_state}")
    
    @pyqtSlot(str)
    def _on_config_changed(self, config_file: str) -> None:
        """Обработка изменения конфигурации"""
        if config_file == self.config_file:
            self.logger.debug("Configuration changed, updating window")
            self.on_config_changed(config_file)
    
    def set_unsaved_changes(self, has_changes: bool) -> None:
        """
        Установить флаг несохраненных изменений.
        
        Args:
            has_changes: Есть ли несохраненные изменения
        """
        if self._has_unsaved_changes != has_changes:
            self._has_unsaved_changes = has_changes
            
            # Обновляем заголовок окна
            self._update_window_title()
            
            # Уведомляем менеджер
            if self._window_manager:
                self._window_manager.set_unsaved_changes(self.window_id, has_changes)
            
            # Отправляем сигнал
            self.unsaved_changes_changed.emit(has_changes)
            
            self.logger.debug(f"Unsaved changes flag set to: {has_changes}")
    
    def has_unsaved_changes(self) -> bool:
        """Проверить, есть ли несохраненные изменения"""
        return self._has_unsaved_changes
    
    def _update_window_title(self) -> None:
        """Обновить заголовок окна с учетом несохраненных изменений"""
        title = self.windowTitle()
        
        if self._has_unsaved_changes and not title.endswith('*'):
            self.setWindowTitle(title + ' *')
        elif not self._has_unsaved_changes and title.endswith('*'):
            self.setWindowTitle(title[:-2])
    
    def set_window_title(self, title: str) -> None:
        """
        Установить заголовок окна.
        
        Args:
            title: Новый заголовок
        """
        super().setWindowTitle(title)
        self._update_window_title()
    
    def save_config(self, file_path: Optional[str] = None) -> bool:
        """
        Сохранить конфигурацию окна.
        
        Args:
            file_path: Путь для сохранения (если None, используется текущий)
            
        Returns:
            True если сохранение прошло успешно
        """
        try:
            save_path = file_path or self.config_file
            if not save_path:
                self.logger.error("No config file path specified")
                return False
            
            # Получаем данные конфигурации от наследника
            config_data = self.get_config_data()
            if config_data is None:
                self.logger.error("Failed to get config data")
                return False
            
            # Сохраняем в файл
            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)
            
            # Обновляем путь к файлу конфигурации
            if file_path:
                self.config_file = file_path
                if self._window_manager:
                    window_info = self._window_manager.get_window(self.window_id)
                    if window_info:
                        window_info.config_file = file_path
            
            # Сбрасываем флаг несохраненных изменений
            self.set_unsaved_changes(False)
            
            self.logger.info(f"Configuration saved to: {save_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to save configuration: {e}")
            return False
    
    def load_config(self, file_path: str) -> bool:
        """
        Загрузить конфигурацию окна.
        
        Args:
            file_path: Путь к файлу конфигурации
            
        Returns:
            True если загрузка прошла успешно
        """
        try:
            if not Path(file_path).exists():
                self.logger.error(f"Config file not found: {file_path}")
                return False
            
            with open(file_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            # Применяем конфигурацию через наследника
            success = self.apply_config_data(config_data)
            
            if success:
                self.config_file = file_path
                self.set_unsaved_changes(False)
                self.logger.info(f"Configuration loaded from: {file_path}")
            else:
                self.logger.error("Failed to apply configuration data")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Failed to load configuration: {e}")
            return False
    
    def closeEvent(self, event: QCloseEvent) -> None:
        """
        Обработка события закрытия окна.
        
        Проверяет наличие несохраненных изменений и показывает диалог подтверждения.
        """
        self.logger.debug("Close event received")
        
        # Отправляем сигнал о закрытии
        self.window_closing.emit()
        
        # Проверяем несохраненные изменения
        if self._has_unsaved_changes:
            reply = self._show_save_confirmation_dialog()
            
            if reply == QMessageBox.StandardButton.Save:
                # Сохраняем и закрываем
                if self.save_config():
                    event.accept()
                else:
                    event.ignore()
                    return
            elif reply == QMessageBox.StandardButton.Discard:
                # Закрываем без сохранения
                event.accept()
            else:  # Cancel
                # Отменяем закрытие
                event.ignore()
                return
        else:
            # Нет несохраненных изменений, закрываем
            event.accept()
        
        # Отменяем регистрацию в менеджере
        if self._window_manager:
            self._window_manager.unregister_window(self.window_id)
        
        # Отправляем сигнал о закрытии
        self.window_closed.emit()
        
        self.logger.info(f"Window closed: {self.window_id}")
    
    def _show_save_confirmation_dialog(self) -> QMessageBox.StandardButton:
        """
        Показать диалог подтверждения сохранения.
        
        Returns:
            Результат диалога (Save, Discard, Cancel)
        """
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Несохраненные изменения")
        msg_box.setText(f"В окне '{self.windowTitle()}' есть несохраненные изменения.")
        msg_box.setInformativeText("Хотите сохранить изменения перед закрытием?")
        msg_box.setStandardButtons(
            QMessageBox.StandardButton.Save |
            QMessageBox.StandardButton.Discard |
            QMessageBox.StandardButton.Cancel
        )
        msg_box.setDefaultButton(QMessageBox.StandardButton.Save)
        msg_box.setIcon(QMessageBox.Icon.Question)
        
        return msg_box.exec()
    
    def show(self) -> None:
        """Показать окно"""
        super().show()
        if self._window_manager:
            self._window_manager.set_window_state(self.window_id, WindowState.OPEN)
    
    def hide(self) -> None:
        """Скрыть окно"""
        super().hide()
        if self._window_manager:
            self._window_manager.set_window_state(self.window_id, WindowState.HIDDEN)
    
    def showMinimized(self) -> None:
        """Свернуть окно"""
        super().showMinimized()
        if self._window_manager:
            self._window_manager.set_window_state(self.window_id, WindowState.MINIMIZED)
    
    def restore_geometry(self) -> bool:
        """Восстановить геометрию окна из сохраненного состояния"""
        if self._window_manager:
            return self._window_manager.restore_window_geometry(self.window_id)
        return False
    
    def save_geometry(self) -> bool:
        """Сохранить текущую геометрию окна"""
        if self._window_manager:
            return self._window_manager.save_window_geometry(self.window_id)
        return False
    
    # Абстрактные методы для переопределения в наследниках
    
    @abstractmethod
    def get_config_data(self) -> Optional[Dict[str, Any]]:
        """
        Получить данные конфигурации для сохранения.
        
        Returns:
            Словарь с данными конфигурации или None в случае ошибки
        """
        pass
    
    @abstractmethod
    def apply_config_data(self, config_data: Dict[str, Any]) -> bool:
        """
        Применить данные конфигурации.
        
        Args:
            config_data: Словарь с данными конфигурации
            
        Returns:
            True если конфигурация успешно применена
        """
        pass
    
    def on_config_changed(self, config_file: str) -> None:
        """
        Обработчик изменения конфигурации.
        
        Переопределяется в наследниках для реакции на изменения конфигурации.
        
        Args:
            config_file: Путь к измененному файлу конфигурации
        """
        pass
    
    def get_window_info(self) -> Dict[str, Any]:
        """
        Получить информацию об окне.
        
        Returns:
            Словарь с информацией об окне
        """
        return {
            'window_id': self.window_id,
            'window_type': self.window_type,
            'config_file': self.config_file,
            'has_unsaved_changes': self._has_unsaved_changes,
            'is_visible': self.isVisible(),
            'geometry': {
                'x': self.x(),
                'y': self.y(),
                'width': self.width(),
                'height': self.height()
            }
        }


class BaseMainWindow(QMainWindow):
    """
    Базовый класс для главных окон (QMainWindow).
    
    Расширяет функциональность BaseWindow для окон типа QMainWindow.
    """
    
    # Сигналы для уведомления о событиях
    window_closing = pyqtSignal()
    window_closed = pyqtSignal()
    unsaved_changes_changed = pyqtSignal(bool)
    config_changed = pyqtSignal(str)  # config_file_path
    
    def __init__(self, window_id: str, window_type: str, 
                 config_file: Optional[str] = None,
                 parent: Optional[QWidget] = None):
        """
        Инициализация базового главного окна.
        
        Args:
            window_id: Уникальный идентификатор окна
            window_type: Тип окна (main, configurer, journal, zone, etc.)
            config_file: Путь к файлу конфигурации (если применимо)
            parent: Родительский виджет
        """
        super().__init__(parent)
        
        self.logger = get_module_logger(f"base_main_window.{window_type}")
        self.window_id = window_id
        self.window_type = window_type
        self.config_file = config_file
        self._has_unsaved_changes = False
        self._window_manager: Optional[WindowManager] = None
        
        # Инициализация базовых настроек
        self._init_base_settings()
        
        # Регистрация в WindowManager
        self._register_with_manager()
        
        self.logger.info(f"BaseMainWindow initialized: {window_id} ({window_type})")
    
    def _init_base_settings(self) -> None:
        """Инициализация базовых настроек окна"""
        # Устанавливаем базовые свойства окна
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        
        # Устанавливаем минимальный размер
        self.setMinimumSize(800, 600)
    
    def _register_with_manager(self) -> None:
        """Регистрация окна в WindowManager"""
        try:
            self._window_manager = get_window_manager()
            self._window_manager.register_window(
                window_id=self.window_id,
                window_type=self.window_type,
                window_instance=self,
                config_file=self.config_file
            )
            
            # Подключаем сигналы менеджера
            self._connect_manager_signals()
            
        except Exception as e:
            self.logger.error(f"Failed to register with WindowManager: {e}")
    
    def _connect_manager_signals(self) -> None:
        """Подключение сигналов WindowManager"""
        if not self._window_manager:
            return
        
        # Подключаем сигналы для синхронизации состояния
        self._window_manager.window_state_changed.connect(self._on_manager_state_changed)
        self._window_manager.config_changed.connect(self._on_config_changed)
    
    @pyqtSlot(str, WindowState)
    def _on_manager_state_changed(self, window_id: str, new_state: WindowState) -> None:
        """Обработка изменения состояния окна через менеджер"""
        if window_id == self.window_id:
            self.logger.debug(f"Window state changed to: {new_state}")
    
    @pyqtSlot(str)
    def _on_config_changed(self, config_file: str) -> None:
        """Обработка изменения конфигурации"""
        if config_file == self.config_file:
            self.logger.debug("Configuration changed, updating window")
            self.on_config_changed(config_file)
    
    def set_unsaved_changes(self, has_changes: bool) -> None:
        """
        Установить флаг несохраненных изменений.
        
        Args:
            has_changes: Есть ли несохраненные изменения
        """
        if self._has_unsaved_changes != has_changes:
            self._has_unsaved_changes = has_changes
            
            # Обновляем заголовок окна
            self._update_window_title()
            
            # Уведомляем менеджер
            if self._window_manager:
                self._window_manager.set_unsaved_changes(self.window_id, has_changes)
            
            # Отправляем сигнал
            self.unsaved_changes_changed.emit(has_changes)
            
            self.logger.debug(f"Unsaved changes flag set to: {has_changes}")
    
    def has_unsaved_changes(self) -> bool:
        """Проверить, есть ли несохраненные изменения"""
        return self._has_unsaved_changes
    
    def _update_window_title(self) -> None:
        """Обновить заголовок окна с учетом несохраненных изменений"""
        title = self.windowTitle()
        
        if self._has_unsaved_changes and not title.endswith('*'):
            self.setWindowTitle(title + ' *')
        elif not self._has_unsaved_changes and title.endswith('*'):
            self.setWindowTitle(title[:-2])
    
    def set_window_title(self, title: str) -> None:
        """
        Установить заголовок окна.
        
        Args:
            title: Новый заголовок
        """
        super().setWindowTitle(title)
        self._update_window_title()
    
    def save_config(self, file_path: Optional[str] = None) -> bool:
        """
        Сохранить конфигурацию окна.
        
        Args:
            file_path: Путь для сохранения (если None, используется текущий)
            
        Returns:
            True если сохранение прошло успешно
        """
        try:
            save_path = file_path or self.config_file
            if not save_path:
                self.logger.error("No config file path specified")
                return False
            
            # Получаем данные конфигурации от наследника
            config_data = self.get_config_data()
            if config_data is None:
                self.logger.error("Failed to get config data")
                return False
            
            # Сохраняем в файл
            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)
            
            # Обновляем путь к файлу конфигурации
            if file_path:
                self.config_file = file_path
                if self._window_manager:
                    window_info = self._window_manager.get_window(self.window_id)
                    if window_info:
                        window_info.config_file = file_path
            
            # Сбрасываем флаг несохраненных изменений
            self.set_unsaved_changes(False)
            
            self.logger.info(f"Configuration saved to: {save_path}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to save configuration: {e}")
            return False
    
    def load_config(self, file_path: str) -> bool:
        """
        Загрузить конфигурацию окна.
        
        Args:
            file_path: Путь к файлу конфигурации
            
        Returns:
            True если загрузка прошла успешно
        """
        try:
            if not Path(file_path).exists():
                self.logger.error(f"Config file not found: {file_path}")
                return False
            
            with open(file_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            # Применяем конфигурацию через наследника
            success = self.apply_config_data(config_data)
            
            if success:
                self.config_file = file_path
                self.set_unsaved_changes(False)
                self.logger.info(f"Configuration loaded from: {file_path}")
            else:
                self.logger.error("Failed to apply configuration data")
            
            return success
            
        except Exception as e:
            self.logger.error(f"Failed to load configuration: {e}")
            return False
    
    def closeEvent(self, event: QCloseEvent) -> None:
        """
        Обработка события закрытия окна.
        
        Проверяет наличие несохраненных изменений и показывает диалог подтверждения.
        """
        self.logger.debug("Close event received")
        
        # Отправляем сигнал о закрытии
        self.window_closing.emit()
        
        # Проверяем несохраненные изменения
        if self._has_unsaved_changes:
            reply = self._show_save_confirmation_dialog()
            
            if reply == QMessageBox.StandardButton.Save:
                # Сохраняем и закрываем
                if self.save_config():
                    event.accept()
                else:
                    event.ignore()
                    return
            elif reply == QMessageBox.StandardButton.Discard:
                # Закрываем без сохранения
                event.accept()
            else:  # Cancel
                # Отменяем закрытие
                event.ignore()
                return
        else:
            # Нет несохраненных изменений, закрываем
            event.accept()
        
        # Отменяем регистрацию в менеджере
        if self._window_manager:
            self._window_manager.unregister_window(self.window_id)
        
        # Отправляем сигнал о закрытии
        self.window_closed.emit()
        
        self.logger.info(f"Window closed: {self.window_id}")
    
    def _show_save_confirmation_dialog(self) -> QMessageBox.StandardButton:
        """
        Показать диалог подтверждения сохранения.
        
        Returns:
            Результат диалога (Save, Discard, Cancel)
        """
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Несохраненные изменения")
        msg_box.setText(f"В окне '{self.windowTitle()}' есть несохраненные изменения.")
        msg_box.setInformativeText("Хотите сохранить изменения перед закрытием?")
        msg_box.setStandardButtons(
            QMessageBox.StandardButton.Save |
            QMessageBox.StandardButton.Discard |
            QMessageBox.StandardButton.Cancel
        )
        msg_box.setDefaultButton(QMessageBox.StandardButton.Save)
        msg_box.setIcon(QMessageBox.Icon.Question)
        
        return msg_box.exec()
    
    def show(self) -> None:
        """Показать окно"""
        super().show()
        if self._window_manager:
            self._window_manager.set_window_state(self.window_id, WindowState.OPEN)
    
    def hide(self) -> None:
        """Скрыть окно"""
        super().hide()
        if self._window_manager:
            self._window_manager.set_window_state(self.window_id, WindowState.HIDDEN)
    
    def showMinimized(self) -> None:
        """Свернуть окно"""
        super().showMinimized()
        if self._window_manager:
            self._window_manager.set_window_state(self.window_id, WindowState.MINIMIZED)
    
    def restore_geometry(self) -> bool:
        """Восстановить геометрию окна из сохраненного состояния"""
        if self._window_manager:
            return self._window_manager.restore_window_geometry(self.window_id)
        return False
    
    def save_geometry(self) -> bool:
        """Сохранить текущую геометрию окна"""
        if self._window_manager:
            return self._window_manager.save_window_geometry(self.window_id)
        return False
    
    # Абстрактные методы для переопределения в наследниках
    
    @abstractmethod
    def get_config_data(self) -> Optional[Dict[str, Any]]:
        """
        Получить данные конфигурации для сохранения.
        
        Returns:
            Словарь с данными конфигурации или None в случае ошибки
        """
        pass
    
    @abstractmethod
    def apply_config_data(self, config_data: Dict[str, Any]) -> bool:
        """
        Применить данные конфигурации.
        
        Args:
            config_data: Словарь с данными конфигурации
            
        Returns:
            True если конфигурация успешно применена
        """
        pass
    
    def on_config_changed(self, config_file: str) -> None:
        """
        Обработчик изменения конфигурации.
        
        Переопределяется в наследниках для реакции на изменения конфигурации.
        
        Args:
            config_file: Путь к измененному файлу конфигурации
        """
        pass
    
    def get_window_info(self) -> Dict[str, Any]:
        """
        Получить информацию об окне.
        
        Returns:
            Словарь с информацией об окне
        """
        return {
            'window_id': self.window_id,
            'window_type': self.window_type,
            'config_file': self.config_file,
            'has_unsaved_changes': self._has_unsaved_changes,
            'is_visible': self.isVisible(),
            'geometry': {
                'x': self.x(),
                'y': self.y(),
                'width': self.width(),
                'height': self.height()
            }
        }
