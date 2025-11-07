"""
Общие pytest fixtures для всех тестов.
"""

import pytest
import sys
from pathlib import Path

# Добавляем корень проекта в путь
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

@pytest.fixture(scope="session")
def project_root_path():
    """Возвращает путь к корню проекта."""
    return Path(__file__).parent.parent

@pytest.fixture(scope="session")
def test_data_dir(project_root_path):
    """Возвращает путь к директории с тестовыми данными."""
    return project_root_path / "videos"

@pytest.fixture(scope="session")
def sample_configs_dir(project_root_path):
    """Возвращает путь к директории с примерами конфигураций."""
    return project_root_path / "evileye" / "samples_configs"

@pytest.fixture(scope="session")
def evil_eye_data_dir(project_root_path):
    """Возвращает путь к директории EvilEyeData."""
    return project_root_path / "EvilEyeData"

@pytest.fixture(autouse=True)
def setup_logging():
    """Настраивает логирование для тестов."""
    try:
        from evileye.core.logging_config import setup_evileye_logging
        setup_evileye_logging(log_level="INFO", log_to_console=False, log_to_file=False)
    except Exception:
        pass  # Логирование не критично для тестов

@pytest.fixture
def mock_db_controller():
    """Fixture для мокового DB контроллера."""
    from unittest.mock import Mock
    mock = Mock()
    mock.get_params.return_value = {
        'image_dir': 'EvilEyeData',
        'preview_width': 300,
        'preview_height': 150
    }
    mock.get_cameras_params.return_value = [
        {
            'source_ids': [0],
            'source_names': ['Cam1'],
            'camera': 'test_camera'
        }
    ]
    mock.get_project_id.return_value = 1
    mock.get_job_id.return_value = 1
    return mock

@pytest.fixture
def mock_db_adapter():
    """Fixture для мокового DB адаптера."""
    from unittest.mock import Mock
    mock = Mock()
    mock.insert = Mock()
    mock.update = Mock()
    return mock

@pytest.fixture(scope="function")
def qapp():
    """Fixture для QApplication."""
    try:
        try:
            from PyQt6.QtWidgets import QApplication
        except ImportError:
            from PyQt5.QtWidgets import QApplication
        
        app = QApplication.instance()
        if app is None:
            import sys
            app = QApplication(sys.argv if hasattr(sys, 'argv') else [])
        yield app
        # Очищаем все виджеты после теста
        for widget in app.allWidgets():
            if widget.isWindow():
                widget.close()
        app.processEvents()
    except Exception:
        pass  # Если PyQt не доступен, пропускаем

@pytest.fixture
def auto_close_windows(qapp):
    """Fixture для автоматического закрытия всех окон после теста."""
    try:
        try:
            from PyQt6.QtCore import QTimer
            from PyQt6.QtWidgets import QApplication
        except ImportError:
            from PyQt5.QtCore import QTimer
            from PyQt5.QtWidgets import QApplication
        
        # Закрываем все окна через короткую задержку
        def close_all_windows():
            app = QApplication.instance()
            if app:
                for widget in app.allWidgets():
                    if widget.isWindow() and widget.isVisible():
                        widget.close()
        
        # Устанавливаем таймер для автоматического закрытия через 100ms
        QTimer.singleShot(100, close_all_windows)
        
        yield
        
        # Закрываем все окна после теста
        close_all_windows()
        # Обрабатываем события для закрытия окон
        app = QApplication.instance()
        if app:
            app.processEvents()
    except Exception:
        pass  # Если PyQt не доступен, пропускаем

