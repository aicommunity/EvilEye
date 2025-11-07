"""
Тесты для рефакторинга GUI EvilEye

Проверяют основную функциональность WindowManager, BaseWindow и диалогов.
"""

import pytest
import tempfile
import json
import os
from pathlib import Path
from unittest.mock import Mock, patch

try:
    from PyQt6.QtWidgets import QApplication, QWidget
    from PyQt6.QtCore import Qt
    pyqt_version = 6
except ImportError:
    from PyQt5.QtWidgets import QApplication, QWidget
    from PyQt5.QtCore import Qt
    pyqt_version = 5

from evileye.visualization_modules.window_manager import WindowManager, WindowState
from evileye.visualization_modules.base_window import BaseWindow
from evileye.visualization_modules.dialogs import SaveConfirmationDialog, SaveAsDialog


@pytest.fixture(scope="function")
def qapp():
    """Fixture для QApplication."""
    if not QApplication.instance():
        app = QApplication([])
    else:
        app = QApplication.instance()
    yield app


@pytest.fixture
def window_manager(qapp):
    """Fixture для WindowManager."""
    manager = WindowManager()
    yield manager
    # Очищаем все окна
    for window_id in list(manager._windows.keys()):
        manager.unregister_window(window_id)


@pytest.fixture
def test_widget(qapp):
    """Fixture для тестового виджета."""
    widget = QWidget()
    widget.setWindowTitle("Test Window")
    return widget


def test_register_window(window_manager, test_widget):
    """Тест регистрации окна"""
    # Регистрируем окно
    result = window_manager.register_window(
        window_id="test_window",
        window_type="test",
        window_instance=test_widget
    )
    
    assert result
    assert "test_window" in window_manager._windows
    
    # Проверяем информацию об окне
    window_info = window_manager.get_window("test_window")
    assert window_info is not None
    assert window_info.window_type == "test"
    assert window_info.state == WindowState.OPEN


def test_unregister_window(window_manager, test_widget):
    """Тест отмены регистрации окна"""
    # Регистрируем окно
    window_manager.register_window(
        window_id="test_window",
        window_type="test",
        window_instance=test_widget
    )
    
    # Отменяем регистрацию
    result = window_manager.unregister_window("test_window")
    assert result
    assert "test_window" not in window_manager._windows


def test_window_state_management(window_manager, test_widget):
    """Тест управления состоянием окна"""
    # Регистрируем окно
    window_manager.register_window(
        window_id="test_window",
        window_type="test",
        window_instance=test_widget
    )
    
    # Изменяем состояние
    window_manager.set_window_state("test_window", WindowState.MINIMIZED)
    window_info = window_manager.get_window("test_window")
    assert window_info.state == WindowState.MINIMIZED


def test_unsaved_changes_tracking(window_manager, test_widget):
    """Тест отслеживания несохраненных изменений"""
    # Регистрируем окно
    window_manager.register_window(
        window_id="test_window",
        window_type="test",
        window_instance=test_widget
    )
    
    # Устанавливаем флаг изменений
    window_manager.set_unsaved_changes("test_window", True)
    assert window_manager.has_unsaved_changes("test_window")
    
    # Получаем список окон с изменениями
    windows_with_changes = window_manager.get_windows_with_unsaved_changes()
    assert "test_window" in windows_with_changes


def test_get_windows_by_type(window_manager, qapp):
    """Тест получения окон по типу"""
    # Регистрируем несколько окон разных типов
    widget1 = QWidget()
    widget2 = QWidget()
    
    window_manager.register_window("window1", "type1", widget1)
    window_manager.register_window("window2", "type1", widget2)
    window_manager.register_window("window3", "type2", QWidget())
    
    # Получаем окна типа "type1"
    type1_windows = window_manager.get_windows_by_type("type1")
    assert len(type1_windows) == 2
    
    # Получаем окна типа "type2"
    type2_windows = window_manager.get_windows_by_type("type2")
    assert len(type2_windows) == 1


def test_status_summary(window_manager, qapp):
    """Тест получения сводки о состоянии"""
    # Регистрируем несколько окон
    window_manager.register_window("window1", "type1", QWidget())
    window_manager.register_window("window2", "type1", QWidget())
    window_manager.set_unsaved_changes("window1", True)
    
    # Получаем сводку
    status = window_manager.get_status_summary()
    
    assert status['total_windows'] == 2
    assert status['unsaved_changes_count'] == 1
    assert 'type1' in status['windows_by_type']
    assert status['windows_by_type']['type1'] == 2


def test_base_window_creation(qapp):
    """Тест создания BaseWindow"""
    # Создаем тестовый класс, наследующий BaseWindow
    class TestWindow(BaseWindow):
        def get_config_data(self):
            return {"test": "data"}
        
        def apply_config_data(self, config_data):
            return True
    
    window = TestWindow(
        window_id="test_window",
        window_type="test",
        config_file="test.json"
    )
    
    assert window.window_id == "test_window"
    assert window.window_type == "test"
    assert window.config_file == "test.json"


def test_unsaved_changes_tracking_base_window(qapp):
    """Тест отслеживания несохраненных изменений в BaseWindow"""
    class TestWindow(BaseWindow):
        def get_config_data(self):
            return {"test": "data"}
        
        def apply_config_data(self, config_data):
            return True
        
        def on_config_changed(self, config_file):
            pass
    
    window = TestWindow("test_window", "test")
    
    try:
        # Проверяем начальное состояние
        assert not window.has_unsaved_changes()
        
        # Устанавливаем изменения
        window.set_unsaved_changes(True)
        assert window.has_unsaved_changes()
        
        # Проверяем, что заголовок обновился
        assert window.windowTitle().endswith('*')
    finally:
        # Очищаем окно
        window.close()


def test_config_save_load(qapp):
    """Тест сохранения и загрузки конфигурации"""
    class TestWindow(BaseWindow):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.data = {"initial": "value"}
        
        def get_config_data(self):
            return self.data
        
        def apply_config_data(self, config_data):
            self.data = config_data
            return True
    
    # Создаем временный файл
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        temp_file = f.name
    
    try:
        window = TestWindow("test_window", "test", temp_file)
        
        # Изменяем данные
        window.data = {"modified": "value"}
        
        # Сохраняем
        result = window.save_config()
        assert result
        
        # Проверяем, что файл создан
        assert os.path.exists(temp_file)
        
        # Загружаем в новое окно
        new_window = TestWindow("test_window2", "test", temp_file)
        result = new_window.load_config(temp_file)
        assert result
        assert new_window.data == {"modified": "value"}
        
    finally:
        # Удаляем временный файл
        if os.path.exists(temp_file):
            os.unlink(temp_file)


def test_save_confirmation_dialog(qapp):
    """Тест диалога подтверждения сохранения"""
    dialog = SaveConfirmationDialog("Test Window", "test.json")
    
    # Проверяем, что диалог создался
    assert dialog is not None
    assert dialog.window_title == "Test Window"
    assert dialog.config_file == "test.json"
    
    # Проверяем начальное состояние
    assert dialog.get_selected_action().value == "cancel"


def test_save_as_dialog(qapp):
    """Тест диалога 'Сохранить как'"""
    dialog = SaveAsDialog("test.json")
    
    # Проверяем, что диалог создался
    assert dialog is not None
    assert dialog.current_file == "test.json"


def test_window_manager_integration(qapp):
    """Тест интеграции WindowManager с BaseWindow"""
    class TestWindow(BaseWindow):
        def get_config_data(self):
            return {"test": "data"}
        
        def apply_config_data(self, config_data):
            return True
    
    # Создаем окно
    window = TestWindow("test_window", "test")
    
    # Проверяем, что окно зарегистрировалось в WindowManager
    manager = window._window_manager
    assert manager is not None
    
    window_info = manager.get_window("test_window")
    assert window_info is not None
    assert window_info.window_type == "test"


def test_global_window_manager(qapp):
    """Тест глобального WindowManager"""
    from evileye.visualization_modules.window_manager import get_window_manager
    
    # Получаем глобальный менеджер
    global_manager = get_window_manager()
    assert isinstance(global_manager, WindowManager)
    
    # Проверяем, что это singleton
    new_manager = get_window_manager()
    assert global_manager == new_manager
