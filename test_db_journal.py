#!/usr/bin/env python3
"""
Тестовый скрипт для проверки создания DatabaseJournalWindow.
"""

import sys
from pathlib import Path

# Добавляем путь к проекту
sys.path.append(str(Path(__file__).parent))

try:
    from PyQt6.QtWidgets import QApplication
    pyqt_version = 6
except ImportError:
    from PyQt5.QtWidgets import QApplication
    pyqt_version = 5

from visualization_modules.db_journal import DatabaseJournalWindow


def test_db_journal():
    """Тест создания DatabaseJournalWindow"""
    print("🚀 Тестирование создания DatabaseJournalWindow")
    
    # Создание приложения
    app = QApplication(sys.argv)
    
    # Тестовые параметры
    params = {
        'visualizer': {
            'objects_journal_enabled': True
        },
        'sources': [
            {
                'camera': 'test_camera',
                'source_id': 1,
                'source_name': 'Test Camera'
            }
        ]
    }
    
    # Минимальная конфигурация базы данных
    database_config = {
        'database': {
            'user_name': 'postgres',
            'database_name': 'evil_eye_db',
            'tables': {
                'objects': {
                    'record_id': 'SERIAL PRIMARY KEY',
                    'source_id': 'integer',
                    'time_stamp': 'timestamp'
                }
            }
        }
    }
    
    try:
        # Создание DatabaseJournalWindow
        db_journal = DatabaseJournalWindow(None, params, database_config, False)
        print("✅ DatabaseJournalWindow создан успешно")
        
        # Проверка компонентов
        print(f"  - db_controller: {db_journal.db_controller is not None}")
        print(f"  - cam_events_adapter: {db_journal.cam_events_adapter is not None}")
        print(f"  - perimeter_events_adapter: {db_journal.perimeter_events_adapter is not None}")
        print(f"  - zone_events_adapter: {db_journal.zone_events_adapter is not None}")
        print(f"  - tabs count: {db_journal.tabs.count()}")
        
        # Закрытие
        db_journal.close()
        print("✅ DatabaseJournalWindow закрыт успешно")
        
        return 0
        
    except Exception as e:
        print(f"❌ Ошибка в тесте: {e}")
        import traceback
        traceback.print_exc()
        return 1


def main():
    """Основная функция"""
    print("=" * 50)
    print("Тест DatabaseJournalWindow")
    print("=" * 50)
    
    try:
        ret = test_db_journal()
        print(f"\n🎯 Тест завершен с кодом: {ret}")
        return ret
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
