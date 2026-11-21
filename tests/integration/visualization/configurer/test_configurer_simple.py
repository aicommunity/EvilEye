#!/usr/bin/env python3
"""
Простой тест ConfigurerMainWindow

Проверяет, что ConfigurerMainWindow может быть создан с минимальной конфигурацией.
"""

import tempfile
import json
import os
import sys
import gc
import subprocess

# Qt widgets need the offscreen backend on headless CI and remote hosts.
if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Qt widgets need the offscreen backend on headless CI and remote hosts.
if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path

try:
    from PyQt6.QtWidgets import QApplication, QMessageBox
    from PyQt6.QtCore import Qt, QCoreApplication, QEvent
    pyqt_version = 6
except ImportError:
    from PyQt5.QtWidgets import QApplication, QMessageBox
    from PyQt5.QtCore import Qt, QCoreApplication, QEvent
    pyqt_version = 5

from evileye.visualization_modules.configurer.configurer_window import ConfigurerMainWindow
from unittest.mock import patch, Mock


def _run_configurer_smoke(app):
    """Простой тест ConfigurerMainWindow"""
    print("🧪 Тестирование ConfigurerMainWindow...")
    
    # QApplication is created by the standalone smoke process.
    
    # Создаем временный файл конфигурации
    temp_config = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
    test_config = {
        "sources": [
            {
                "source": "VideoCapture",
                "camera": "0",
                "apiPreference": "CAP_ANY",
                "split": False,
                "num_split": 0,
                "src_coords": [0],
                "source_ids": [0],
                "source_names": ["Cam1"]
            }
        ],
        "detectors": [
            {
                "source_ids": [0],
                "model": "models/yolov8n.pt",
                "show": False,
                "inference_size": 640,
                "device": None,
                "conf": 0.4,
                "save": False,
                "stride_type": "frames",
                "vid_stride": 1,
                "classes": [0, 1, 2, 3, 4, 5, 6, 7],
                "num_detection_threads": 3,
                "roi": [[]]
            }
        ],
        "handlers": [
            {
                "type": "Writer"
            }
        ],
        "objects_handler": {
            "type": "Writer"
        },
        "visualizers": [
            {
                "type": "VisualizerOpencv"
            }
        ],
        "database": {
            "type": "DatabaseSqlite",
            "db_path": "evil_eye_db.db"
        },
        "trackers": [
            {
                "source_ids": [0],
                "fps": 5,
                "botsort_cfg": {
                    "appearance_thresh": 0.25,
                    "gmc_method": "sparseOptFlow",
                    "match_thresh": 0.8,
                    "new_track_thresh": 0.6,
                    "proximity_thresh": 0.5,
                    "track_buffer": 30,
                    "track_high_thresh": 0.5,
                    "track_low_thresh": 0.1,
                    "tracker_type": "botsort"
                }
            }
        ],
        "mc_trackers": [
            {
                "type": "ObjectMultiCameraTracking"
            }
        ],
        "events": [
            {
                "type": "EventsProcessor"
            }
        ],
        "events_detectors": {
            "ZoneEventsDetector": {
                "sources": []
            }
        },
        "visualizer": {
            "num_height": 1,
            "num_width": 1,
            "event_signal_enabled": False,
            "event_signal_color": [255, 0, 0]
        },
        "pipeline": {
            "sources": [
                {
                    "source_ids": ["Cam1"]
                }
            ]
        }
    }
    
    json.dump(test_config, temp_config, indent=4)
    temp_config.close()
    configurer = None
    
    try:
        print(f"📁 Создан временный файл: {temp_config.name}")
        
        # Создаем ConfigurerMainWindow
        print("🔧 Создание ConfigurerMainWindow...")
        
        # Получаем относительный путь
        from evileye.utils.utils import get_project_root
        project_root = get_project_root()
        relative_path = os.path.relpath(temp_config.name, project_root)
        print(f"📂 Относительный путь: {relative_path}")
        
        # Мокируем QMessageBox, чтобы диалоги ошибок не появлялись
        # Определяем возвращаемое значение для question в зависимости от версии PyQt
        if pyqt_version == 6:
            question_return_value = QMessageBox.StandardButton.Discard
        else:
            question_return_value = QMessageBox.Discard
        
        with (
            patch.object(ConfigurerMainWindow, "_connect_to_db"),
            patch("evileye.visualization_modules.configurer.configurer_window.QMessageBox") as mock_msgbox,
        ):
            # Мокируем методы QMessageBox
            mock_msgbox.critical = Mock()
            mock_msgbox.warning = Mock()
            mock_msgbox.information = Mock()
            mock_msgbox.question = Mock(return_value=question_return_value)
            
            # Мокируем стандартные кнопки
            mock_msgbox.StandardButton = QMessageBox.StandardButton
            
            configurer = ConfigurerMainWindow(
                config_file_name=relative_path,
                win_width=1280,
                win_height=720
            )
        
        print("✅ ConfigurerMainWindow создан успешно")
        
        # Проверяем, что окно создано
        if configurer:
            print("✅ Окно ConfigurerMainWindow существует")
            
            # Закрываем окно и обрабатываем ожидающие Qt-события.
            configurer.close()
            app.processEvents()
            assert not configurer._change_tracking_connections
            print("✅ Окно ConfigurerMainWindow закрыто")
        else:
            print("❌ Окно ConfigurerMainWindow не создано")
            raise AssertionError("Окно ConfigurerMainWindow не создано")
        
        print("🎉 Тест прошел успешно!")
        # Test functions should return None, not values
        
    except Exception as e:
        print(f"❌ Ошибка во время тестирования: {e}")
        import traceback
        traceback.print_exc()
        raise  # Re-raise exception for pytest to catch
    
    finally:
        # Destroy the native widget tree while QApplication and Qt modules are alive.
        if configurer is not None:
            configurer.close()
            configurer.deleteLater()
            deferred_delete = (
                QEvent.Type.DeferredDelete if pyqt_version == 6 else QEvent.DeferredDelete
            )
            QCoreApplication.sendPostedEvents(None, deferred_delete)
            app.processEvents()
            del configurer
            gc.collect()

        # Очищаем временный файл
        try:
            os.unlink(temp_config.name)
        except:
            pass


def test_configurer_simple():
    env = os.environ.copy()
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve())],
        cwd=Path(__file__).resolve().parents[4],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, (
        f"Configurer GUI smoke process exited with {result.returncode}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


if __name__ == "__main__":
    app = QApplication.instance() or QApplication([])
    _run_configurer_smoke(app)
    sys.exit(0)
