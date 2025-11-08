"""
Общие pytest fixtures для всех тестов.
"""

import pytest
import sys
import atexit
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
        try:
            widgets_to_close = []
            for widget in app.allWidgets():
                try:
                    if widget and widget.isWindow():
                        widgets_to_close.append(widget)
                except (RuntimeError, AttributeError):
                    pass
                except Exception:
                    pass
            
            # Закрываем все окна
            for widget in widgets_to_close:
                try:
                    if widget:
                        widget.close()
                except (RuntimeError, AttributeError):
                    pass
                except Exception:
                    pass
            
            # Не завершаем приложение здесь, так как оно может использоваться другими тестами
            # Завершение будет выполнено финализатором на уровне сессии
        except (RuntimeError, AttributeError):
            # QApplication уже уничтожен
            pass
        except Exception:
            pass
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
        # Не вызываем processEvents здесь, чтобы избежать segfault
    except Exception:
        pass  # Если PyQt не доступен, пропускаем

def _cleanup_qapplication_at_exit():
    """Функция для безопасного завершения QApplication при выходе из процесса."""
    try:
        try:
            from PyQt6.QtWidgets import QApplication
        except ImportError:
            from PyQt5.QtWidgets import QApplication
        
        app = QApplication.instance()
        if app is not None:
            # Закрываем все виджеты перед завершением
            try:
                for widget in app.allWidgets():
                    try:
                        if widget and widget.isWindow():
                            widget.close()
                    except (RuntimeError, AttributeError):
                        pass
                    except Exception:
                        pass
            except (RuntimeError, AttributeError):
                pass
            except Exception:
                pass
            
            # Просто завершаем приложение без вызова методов, которые могут вызвать segfault
            # Не вызываем app.quit() здесь, так как это может вызвать segfault
            # Вместо этого просто позволяем процессу завершиться естественным образом
            try:
                # Только если приложение еще активно
                if hasattr(app, 'quit'):
                    # Не вызываем quit(), так как это может вызвать segfault
                    pass
            except Exception:
                pass
    except Exception:
        pass  # Если PyQt не доступен, пропускаем

# Регистрируем функцию очистки при выходе из процесса
atexit.register(_cleanup_qapplication_at_exit)

@pytest.fixture(scope="session", autouse=True)
def cleanup_qapplication():
    """Финализатор на уровне сессии для безопасного завершения QApplication после всех тестов."""
    yield
    # Безопасно завершаем QApplication после всех тестов
    _cleanup_qapplication_at_exit()

def pytest_sessionfinish(session, exitstatus):
    """Хук pytest для завершения сессии тестов."""
    # Безопасно завершаем QApplication после завершения всех тестов
    _cleanup_qapplication_at_exit()

