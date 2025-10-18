"""
Window Manager for EvilEye GUI

Централизованное управление всеми окнами GUI приложения.
Обеспечивает регистрацию, отслеживание и координацию взаимодействия между окнами.
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, asdict
from enum import Enum

try:
    from PyQt6.QtCore import QObject, pyqtSignal, QTimer
    from PyQt6.QtWidgets import QWidget, QMainWindow
    pyqt_version = 6
except ImportError:
    from PyQt5.QtCore import QObject, pyqtSignal, QTimer
    from PyQt5.QtWidgets import QWidget, QMainWindow
    pyqt_version = 5

from ..core.logger import get_module_logger


class WindowState(Enum):
    """Состояния окна"""
    CLOSED = "closed"
    OPEN = "open"
    MINIMIZED = "minimized"
    HIDDEN = "hidden"


@dataclass
class WindowInfo:
    """Информация об окне"""
    window_id: str
    window_type: str
    window_instance: Optional[QWidget]
    state: WindowState
    geometry: Optional[Dict[str, int]] = None
    has_unsaved_changes: bool = False
    config_file: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class WindowManager(QObject):
    """
    Менеджер окон для централизованного управления GUI окнами.
    
    Функциональность:
    - Регистрация и отслеживание всех открытых окон
    - Централизованное управление жизненным циклом окон
    - Координация взаимодействия между окнами
    - Сохранение/восстановление состояния окон
    """
    
    # Сигналы для уведомления о событиях
    window_opened = pyqtSignal(str, str)  # window_id, window_type
    window_closed = pyqtSignal(str, str)  # window_id, window_type
    window_state_changed = pyqtSignal(str, WindowState)  # window_id, new_state
    config_changed = pyqtSignal(str)  # config_file_path
    pipeline_started = pyqtSignal()
    pipeline_stopped = pyqtSignal()
    zone_added = pyqtSignal(int, str)  # source_id, zone_type
    zone_removed = pyqtSignal(int, str)  # source_id, zone_type
    database_connected = pyqtSignal()
    database_disconnected = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = get_module_logger("window_manager")
        
        # Реестр окон: window_id -> WindowInfo
        self._windows: Dict[str, WindowInfo] = {}
        
        # Обработчики событий: event_type -> List[callable]
        self._event_handlers: Dict[str, List[Callable]] = {}
        
        # Настройки для сохранения состояния
        self._state_file = Path("gui_state.json")
        self._auto_save_timer = QTimer()
        self._auto_save_timer.timeout.connect(self._save_state)
        self._auto_save_timer.start(30000)  # Сохранять каждые 30 секунд
        
        self.logger.info("WindowManager initialized")
    
    def register_window(self, window_id: str, window_type: str, 
                       window_instance: QWidget, config_file: Optional[str] = None,
                       metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Регистрация нового окна в менеджере.
        
        Args:
            window_id: Уникальный идентификатор окна
            window_type: Тип окна (main, configurer, journal, zone, etc.)
            window_instance: Экземпляр окна
            config_file: Путь к файлу конфигурации (если применимо)
            metadata: Дополнительные метаданные
            
        Returns:
            True если окно успешно зарегистрировано
        """
        if window_id in self._windows:
            self.logger.warning(f"Window {window_id} already registered")
            return False
        
        # Сохраняем геометрию окна
        geometry = None
        if hasattr(window_instance, 'geometry'):
            geom = window_instance.geometry()
            geometry = {
                'x': geom.x(),
                'y': geom.y(),
                'width': geom.width(),
                'height': geom.height()
            }
        
        window_info = WindowInfo(
            window_id=window_id,
            window_type=window_type,
            window_instance=window_instance,
            state=WindowState.OPEN,
            geometry=geometry,
            config_file=config_file,
            metadata=metadata or {}
        )
        
        self._windows[window_id] = window_info
        
        # Подключаем обработчики событий окна
        self._connect_window_signals(window_instance, window_id)
        
        self.logger.info(f"Window registered: {window_id} ({window_type})")
        self.window_opened.emit(window_id, window_type)
        
        return True
    
    def unregister_window(self, window_id: str) -> bool:
        """
        Отмена регистрации окна.
        
        Args:
            window_id: Идентификатор окна
            
        Returns:
            True если окно успешно удалено
        """
        if window_id not in self._windows:
            self.logger.warning(f"Window {window_id} not found")
            return False
        
        window_info = self._windows[window_id]
        window_type = window_info.window_type
        
        # Отключаем обработчики событий
        if window_info.window_instance:
            self._disconnect_window_signals(window_info.window_instance)
        
        del self._windows[window_id]
        
        self.logger.info(f"Window unregistered: {window_id} ({window_type})")
        self.window_closed.emit(window_id, window_type)
        
        return True
    
    def get_window(self, window_id: str) -> Optional[WindowInfo]:
        """Получить информацию об окне по ID"""
        return self._windows.get(window_id)
    
    def get_windows_by_type(self, window_type: str) -> List[WindowInfo]:
        """Получить все окна определенного типа"""
        return [info for info in self._windows.values() 
                if info.window_type == window_type]
    
    def get_all_windows(self) -> Dict[str, WindowInfo]:
        """Получить все зарегистрированные окна"""
        return self._windows.copy()
    
    def set_window_state(self, window_id: str, state: WindowState) -> bool:
        """
        Изменить состояние окна.
        
        Args:
            window_id: Идентификатор окна
            state: Новое состояние
            
        Returns:
            True если состояние успешно изменено
        """
        if window_id not in self._windows:
            return False
        
        old_state = self._windows[window_id].state
        self._windows[window_id].state = state
        
        if old_state != state:
            self.logger.debug(f"Window {window_id} state changed: {old_state} -> {state}")
            self.window_state_changed.emit(window_id, state)
        
        return True
    
    def set_unsaved_changes(self, window_id: str, has_changes: bool) -> bool:
        """
        Установить флаг несохраненных изменений для окна.
        
        Args:
            window_id: Идентификатор окна
            has_changes: Есть ли несохраненные изменения
            
        Returns:
            True если флаг успешно установлен
        """
        if window_id not in self._windows:
            return False
        
        self._windows[window_id].has_unsaved_changes = has_changes
        
        # Обновляем заголовок окна
        window_instance = self._windows[window_id]
        if window_instance and hasattr(window_instance, 'setWindowTitle'):
            try:
                title = window_instance.windowTitle()
                if has_changes and not title.endswith('*'):
                    window_instance.setWindowTitle(title + ' *')
                elif not has_changes and title.endswith('*'):
                    window_instance.setWindowTitle(title[:-2])
            except RuntimeError:
                # Окно было удалено, игнорируем
                pass
        
        self.logger.debug(f"Window {window_id} unsaved changes: {has_changes}")
        return True
    
    def has_unsaved_changes(self, window_id: str) -> bool:
        """Проверить, есть ли несохраненные изменения в окне"""
        if window_id not in self._windows:
            return False
        return self._windows[window_id].has_unsaved_changes
    
    def get_windows_with_unsaved_changes(self) -> List[str]:
        """Получить список окон с несохраненными изменениями"""
        return [window_id for window_id, info in self._windows.items() 
                if info.has_unsaved_changes]
    
    def close_window(self, window_id: str, force: bool = False) -> bool:
        """
        Закрыть окно.
        
        Args:
            window_id: Идентификатор окна
            force: Принудительное закрытие без проверки изменений
            
        Returns:
            True если окно успешно закрыто
        """
        if window_id not in self._windows:
            return False
        
        window_info = self._windows[window_id]
        
        # Проверяем несохраненные изменения
        if not force and window_info.has_unsaved_changes:
            self.logger.warning(f"Cannot close window {window_id}: has unsaved changes")
            return False
        
        # Закрываем окно
        if window_info.window_instance:
            window_info.window_instance.close()
        
        return True
    
    def close_all_windows(self, force: bool = False) -> List[str]:
        """
        Закрыть все окна.
        
        Args:
            force: Принудительное закрытие без проверки изменений
            
        Returns:
            Список ID окон, которые не удалось закрыть
        """
        failed_closes = []
        
        for window_id in list(self._windows.keys()):
            if not self.close_window(window_id, force):
                failed_closes.append(window_id)
        
        return failed_closes
    
    def show_window(self, window_id: str) -> bool:
        """Показать окно"""
        if window_id not in self._windows:
            return False
        
        window_info = self._windows[window_id]
        if window_info.window_instance:
            window_info.window_instance.show()
            window_info.window_instance.raise_()
            window_info.window_instance.activateWindow()
            self.set_window_state(window_id, WindowState.OPEN)
            return True
        
        return False
    
    def hide_window(self, window_id: str) -> bool:
        """Скрыть окно"""
        if window_id not in self._windows:
            return False
        
        window_info = self._windows[window_id]
        if window_info.window_instance:
            window_info.window_instance.hide()
            self.set_window_state(window_id, WindowState.HIDDEN)
            return True
        
        return False
    
    def minimize_window(self, window_id: str) -> bool:
        """Свернуть окно"""
        if window_id not in self._windows:
            return False
        
        window_info = self._windows[window_id]
        if window_info.window_instance and hasattr(window_info.window_instance, 'showMinimized'):
            window_info.window_instance.showMinimized()
            self.set_window_state(window_id, WindowState.MINIMIZED)
            return True
        
        return False
    
    def restore_window_geometry(self, window_id: str) -> bool:
        """
        Восстановить геометрию окна из сохраненного состояния.
        
        Args:
            window_id: Идентификатор окна
            
        Returns:
            True если геометрия успешно восстановлена
        """
        if window_id not in self._windows:
            return False
        
        window_info = self._windows[window_id]
        if not window_info.geometry or not window_info.window_instance:
            return False
        
        try:
            geom = window_info.geometry
            window_info.window_instance.setGeometry(
                geom['x'], geom['y'], 
                geom['width'], geom['height']
            )
            self.logger.debug(f"Restored geometry for window {window_id}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to restore geometry for window {window_id}: {e}")
            return False
    
    def save_window_geometry(self, window_id: str) -> bool:
        """
        Сохранить текущую геометрию окна.
        
        Args:
            window_id: Идентификатор окна
            
        Returns:
            True если геометрия успешно сохранена
        """
        if window_id not in self._windows:
            return False
        
        window_info = self._windows[window_id]
        if not window_info.window_instance or not hasattr(window_info.window_instance, 'geometry'):
            return False
        
        try:
            geom = window_info.window_instance.geometry()
            window_info.geometry = {
                'x': geom.x(),
                'y': geom.y(),
                'width': geom.width(),
                'height': geom.height()
            }
            self.logger.debug(f"Saved geometry for window {window_id}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to save geometry for window {window_id}: {e}")
            return False
    
    def register_event_handler(self, event_type: str, handler: Callable) -> None:
        """
        Зарегистрировать обработчик события.
        
        Args:
            event_type: Тип события
            handler: Функция-обработчик
        """
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []
        
        self._event_handlers[event_type].append(handler)
        self.logger.debug(f"Registered event handler for {event_type}")
    
    def unregister_event_handler(self, event_type: str, handler: Callable) -> None:
        """Отменить регистрацию обработчика события"""
        if event_type in self._event_handlers:
            try:
                self._event_handlers[event_type].remove(handler)
                self.logger.debug(f"Unregistered event handler for {event_type}")
            except ValueError:
                pass
    
    def emit_event(self, event_type: str, *args, **kwargs) -> None:
        """
        Отправить событие всем зарегистрированным обработчикам.
        
        Args:
            event_type: Тип события
            *args, **kwargs: Аргументы для обработчиков
        """
        if event_type in self._event_handlers:
            for handler in self._event_handlers[event_type]:
                try:
                    handler(*args, **kwargs)
                except Exception as e:
                    self.logger.error(f"Error in event handler for {event_type}: {e}")
    
    def _connect_window_signals(self, window_instance: QWidget, window_id: str) -> None:
        """Подключить сигналы окна к менеджеру"""
        if hasattr(window_instance, 'closeEvent'):
            # Сохраняем оригинальный closeEvent
            original_close_event = window_instance.closeEvent
            
            def wrapped_close_event(event):
                # Сохраняем геометрию перед закрытием
                self.save_window_geometry(window_id)
                # Вызываем оригинальный обработчик
                original_close_event(event)
                # Отменяем регистрацию окна
                self.unregister_window(window_id)
            
            window_instance.closeEvent = wrapped_close_event
        
        if hasattr(window_instance, 'resizeEvent'):
            original_resize_event = window_instance.resizeEvent
            
            def wrapped_resize_event(event):
                # Вызываем оригинальный обработчик
                original_resize_event(event)
                # Сохраняем новую геометрию
                self.save_window_geometry(window_id)
            
            window_instance.resizeEvent = wrapped_resize_event
    
    def _disconnect_window_signals(self, window_instance: QWidget) -> None:
        """Отключить сигналы окна от менеджера"""
        # Восстанавливаем оригинальные обработчики событий
        # (это упрощенная версия, в реальности может потребоваться более сложная логика)
        pass
    
    def _save_state(self) -> None:
        """Сохранить состояние всех окон в файл"""
        try:
            state_data = {}
            for window_id, window_info in self._windows.items():
                state_data[window_id] = {
                    'window_type': window_info.window_type,
                    'state': window_info.state.value,
                    'geometry': window_info.geometry,
                    'config_file': window_info.config_file,
                    'metadata': window_info.metadata
                }
            
            with open(self._state_file, 'w', encoding='utf-8') as f:
                json.dump(state_data, f, indent=2, ensure_ascii=False)
            
            self.logger.debug("Window state saved")
        except Exception as e:
            self.logger.error(f"Failed to save window state: {e}")
    
    def load_state(self) -> Dict[str, Any]:
        """
        Загрузить состояние окон из файла.
        
        Returns:
            Словарь с данными состояния
        """
        try:
            if not self._state_file.exists():
                return {}
            
            with open(self._state_file, 'r', encoding='utf-8') as f:
                state_data = json.load(f)
            
            self.logger.debug("Window state loaded")
            return state_data
        except Exception as e:
            self.logger.error(f"Failed to load window state: {e}")
            return {}
    
    def get_status_summary(self) -> Dict[str, Any]:
        """
        Получить сводку о состоянии всех окон.
        
        Returns:
            Словарь со статистикой
        """
        total_windows = len(self._windows)
        windows_by_type = {}
        windows_by_state = {}
        unsaved_count = 0
        
        for window_info in self._windows.values():
            # По типам
            window_type = window_info.window_type
            windows_by_type[window_type] = windows_by_type.get(window_type, 0) + 1
            
            # По состояниям
            state = window_info.state.value
            windows_by_state[state] = windows_by_state.get(state, 0) + 1
            
            # Несохраненные изменения
            if window_info.has_unsaved_changes:
                unsaved_count += 1
        
        return {
            'total_windows': total_windows,
            'windows_by_type': windows_by_type,
            'windows_by_state': windows_by_state,
            'unsaved_changes_count': unsaved_count,
            'windows_with_unsaved_changes': self.get_windows_with_unsaved_changes()
        }


# Глобальный экземпляр менеджера окон
_window_manager_instance: Optional[WindowManager] = None


def get_window_manager() -> WindowManager:
    """
    Получить глобальный экземпляр WindowManager.
    
    Returns:
        Экземпляр WindowManager
    """
    global _window_manager_instance
    if _window_manager_instance is None:
        _window_manager_instance = WindowManager()
    return _window_manager_instance


def set_window_manager(manager: WindowManager) -> None:
    """
    Установить глобальный экземпляр WindowManager.
    
    Args:
        manager: Экземпляр WindowManager
    """
    global _window_manager_instance
    _window_manager_instance = manager
