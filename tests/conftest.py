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

@pytest.fixture(scope="session")
def ensure_test_videos(project_root_path):
    """Автоматически загружает тестовые видео из deploy-samples если их нет."""
    videos_dir = project_root_path / "videos"
    videos_dir.mkdir(exist_ok=True)
    
    # Проверить наличие ключевых файлов
    required_videos = ["planes_sample.mp4", "sample_split.mp4", "6p-c0.avi", "6p-c1.avi"]
    missing = [v for v in required_videos if not (videos_dir / v).exists()]
    
    # Если есть отсутствующие файлы, попытаться загрузить
    if missing:
        try:
            from evileye.utils.download_samples import download_sample_videos
            # Загрузить видео если их нет
            results = download_sample_videos(str(videos_dir), force=False, parallel=False)
            
            # Проверить результат загрузки
            for video_name in missing:
                if video_name in results:
                    status = results[video_name].get("status", "failed")
                    if status not in ("downloaded", "exists"):
                        # Если загрузка не удалась, проверить наличие файла
                        if not (videos_dir / video_name).exists():
                            # Пропустить тест если критичный файл отсутствует
                            if video_name == "planes_sample.mp4":
                                pytest.skip(f"Required test video not available: {video_name}. "
                                           f"Run 'evileye deploy-samples' to download it.")
        except Exception as e:
            # Если не удалось загрузить, но planes_sample.mp4 есть - продолжить
            if not (videos_dir / "planes_sample.mp4").exists():
                pytest.skip(f"Could not ensure test videos are available: {e}. "
                           f"Run 'evileye deploy-samples' to download them.")
    
    return videos_dir

@pytest.fixture(autouse=True)
def setup_logging():
    """Настраивает логирование для тестов."""
    try:
        import logging
        from evileye.core.logging_config import setup_evileye_logging
        setup_evileye_logging(log_level="INFO", log_to_console=False, log_to_file=False)
        # Устанавливаем уровень ERROR для controller логгера, чтобы скрыть warning сообщения
        controller_logger = logging.getLogger("evileye.controller")
        controller_logger.setLevel(logging.ERROR)
    except Exception:
        pass  # Логирование не критично для тестов

@pytest.fixture(autouse=True)
def setup_controller_timeout(monkeypatch):
    """Устанавливает короткий таймаут для model_loading_timeout_sec в тестах."""
    # Monkeypatch для установки короткого таймаута через параметры controller
    # Это предотвращает задержку завершения pytest из-за фонового потока periodic_check
    # Фоновый поток periodic_check работает до model_loading_timeout_sec секунд,
    # поэтому устанавливаем короткий таймаут (1 секунда) для быстрого завершения
    try:
        from evileye.controller import controller
        
        original_init = controller.Controller.init
        
        def patched_init(self, params):
            # Устанавливаем короткий таймаут для тестов
            if not isinstance(params, dict):
                params = {}
            if 'controller' not in params:
                params['controller'] = {}
            # Устанавливаем короткий таймаут (1 секунда) вместо 60 секунд по умолчанию
            params['controller']['model_loading_timeout_sec'] = 1
            return original_init(self, params)
        
        monkeypatch.setattr(controller.Controller, 'init', patched_init)
    except Exception:
        pass  # Если Controller не доступен, пропускаем
    yield
    # Cleanup выполняется автоматически через monkeypatch

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

_qapplication_instance = None


def _get_qapplication_instance():
    """Keep one Python wrapper alive for the native QApplication lifetime."""
    global _qapplication_instance
    try:
        from PyQt6.QtWidgets import QApplication
    except ImportError:
        from PyQt5.QtWidgets import QApplication
    if _qapplication_instance is None:
        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv if hasattr(sys, "argv") else [])
        _qapplication_instance = app
    return _qapplication_instance


@pytest.fixture(scope="session")
def qapp_local():
    """Legacy alias for the session-scoped QApplication fixture."""
    try:
        app = _get_qapplication_instance()
    except Exception:
        app = None
    yield app


@pytest.fixture(scope="session")
def qapp():
    """Provide one stable QApplication wrapper for the entire pytest session."""
    try:
        app = _get_qapplication_instance()
    except Exception:
        app = None
    yield app


@pytest.fixture(scope="session", autouse=True)
def _shutdown_background_services():
    """
    Best-effort cleanup to avoid interpreter/Qt shutdown segfaults.

    Some integration tests start background threads (DB writer, labeling manager, recorders).
    We stop what we can at the end of the test session.
    """
    yield
    # Stop UI streaming/render workers before Qt objects and native libraries tear down.
    for module_name, class_name in (
        ("evileye.controller.services.preview_render_service", "PreviewRenderService"),
        ("evileye.controller.services.streaming_service", "StreamingService"),
    ):
        try:
            service_class = getattr(__import__(module_name, fromlist=[class_name]), class_name)
            service_class.shutdown_all()
        except Exception:
            pass
    # Stop labeling manager threads
    try:
        from evileye.objects_handler.labeling_manager import LabelingManager

        try:
            LabelingManager.shutdown_all()
        except Exception:
            pass
    except Exception:
        pass
    try:
        from evileye.visualization_modules.journal_init_thread import JournalInitThread

        JournalInitThread.shutdown_all(timeout_ms=7000)
    except Exception:
        pass


@pytest.fixture(scope="session", autouse=True)
def _disable_qt_multimedia_for_tests():
    # QtMultimedia is a frequent source of segfaults in headless environments.
    import os

    os.environ.setdefault("EVILEYE_DISABLE_QT_MULTIMEDIA", "1")
    yield


@pytest.fixture(autouse=True)
def _cleanup_after_each_test():
    """
    Function-scope cleanup: stop background workers between tests.
    Prevents long-lived native threads from accumulating and crashing the run.
    """
    yield
    # Drain services that own daemon workers before native Qt teardown.
    try:
        from evileye.controller.services.preview_render_service import PreviewRenderService
        PreviewRenderService.shutdown_all()
    except Exception:
        pass
    try:
        from evileye.controller.services.streaming_service import StreamingService
        StreamingService.shutdown_all()
    except Exception:
        pass
    try:
        from evileye.objects_handler.labeling_manager import LabelingManager

        LabelingManager.shutdown_all()
    except Exception:
        pass
    try:
        from evileye.database_controller.database_controller_base import DatabaseControllerBase

        DatabaseControllerBase.shutdown_all()
    except Exception:
        pass
    try:
        from evileye.object_detector.detection_thread_base import DetectionThreadBase

        DetectionThreadBase.shutdown_all()
    except Exception:
        pass
    try:
        from evileye.core.mp_control import MpControl

        MpControl.shutdown_all()
    except Exception:
        pass
    try:
        from evileye.server import ServerProcessManager

        ServerProcessManager.shutdown_all()
    except Exception:
        pass
    try:
        from evileye.video_recorder.continuous_recorder_gst import GstContinuousRecorder

        GstContinuousRecorder.shutdown_all()
    except Exception:
        pass
    # Join journal workers before releasing their QThread wrappers.
    try:
        from evileye.visualization_modules.journal_init_thread import JournalInitThread

        JournalInitThread.shutdown_all(timeout_ms=7000)
    except Exception:
        pass


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

def pytest_sessionfinish(session, exitstatus):
    """Session cleanup. Opt-in force exit preserves real exitstatus (avoids native segfault on shutdown)."""
    import os

    # Opt-in only: default must leave pytest's real exit code intact (audit A05).
    # EVILEYE_PYTEST_NO_FORCE_EXIT remains a no-op alias for older docs/scripts.
    if os.environ.get("EVILEYE_PYTEST_FORCE_EXIT", "").strip().lower() in {"1", "true", "yes", "on"}:
        os._exit(int(exitstatus))

