#!/usr/bin/env python3
"""
Простой тест ConfigurerMainWindow

Проверяет, что ConfigurerMainWindow может быть создан с минимальной конфигурацией.
"""

import tempfile
import json
import os
import time
from pathlib import Path

try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import Qt, QTimer
    pyqt_version = 6
except ImportError:
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import Qt, QTimer
    pyqt_version = 5

from evileye.visualization_modules.configurer.configurer_window import ConfigurerMainWindow


def test_configurer_simple():
    """Простой тест ConfigurerMainWindow"""
    print("🧪 Тестирование ConfigurerMainWindow...")
    
    # Создаем QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    
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
        "events_detectors": [
            {
                "type": "ZoneEventsDetector",
                "sources": []
            }
        ],
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
    
    try:
        print(f"📁 Создан временный файл: {temp_config.name}")
        
        # Создаем ConfigurerMainWindow
        print("🔧 Создание ConfigurerMainWindow...")
        
        # Получаем относительный путь
        from evileye.utils.utils import get_project_root
        project_root = get_project_root()
        relative_path = os.path.relpath(temp_config.name, project_root)
        print(f"📂 Относительный путь: {relative_path}")
        
        configurer = ConfigurerMainWindow(
            config_file_name=relative_path,
            win_width=1280,
            win_height=720
        )
        
        print("✅ ConfigurerMainWindow создан успешно")
        
        # Проверяем, что окно создано
        if configurer:
            print("✅ Окно ConfigurerMainWindow существует")
            
            # Автоматически закрываем окно через 100ms
            def close_window():
                try:
                    configurer.close()
                    app.quit()
                except Exception:
                    pass
            
            QTimer.singleShot(100, close_window)
            # Даем время на закрытие окна
            time.sleep(0.2)
            
            # Явно закрываем окно на случай, если таймер не сработал
            try:
                configurer.close()
                app.quit()
            except Exception:
                pass
            print("✅ Окно ConfigurerMainWindow закрыто")
        else:
            print("❌ Окно ConfigurerMainWindow не создано")
            return False
        
        print("🎉 Тест прошел успешно!")
        return True
        
    except Exception as e:
        print(f"❌ Ошибка во время тестирования: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    finally:
        # Очищаем временный файл
        try:
            os.unlink(temp_config.name)
        except:
            pass


if __name__ == "__main__":
    success = test_configurer_simple()
    sys.exit(0 if success else 1)
