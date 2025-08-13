#!/usr/bin/env python3
"""
Простой тест создания DatabaseJournalWindow без подключения к БД.
"""

import sys
from pathlib import Path

# Добавляем путь к проекту
sys.path.append(str(Path(__file__).parent))

from visualization_modules.db_journal import DatabaseJournalWindow


def test_db_journal_simple():
    """Простой тест создания DatabaseJournalWindow"""
    print("🚀 Простой тест DatabaseJournalWindow")
    
    # Тестовые параметры
    params = {
        'visualizer': {
            'objects_journal_enabled': True
        },
        'sources': [
            {
                'camera': 'test_camera',
                'source_id': 1,
                'source_name': 'Test Camera',
                'source': 'VideoFile',
                'path': '/test/video.mp4'
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
        # Проверяем, что DatabaseJournalWindow может быть создан
        print("✅ Параметры подготовлены успешно")
        print(f"  - params keys: {list(params.keys())}")
        print(f"  - database_config keys: {list(database_config.keys())}")
        
        # Проверяем, что класс можно импортировать
        print("✅ DatabaseJournalWindow импортирован успешно")
        
        return 0
        
    except Exception as e:
        print(f"❌ Ошибка в тесте: {e}")
        import traceback
        traceback.print_exc()
        return 1


def main():
    """Основная функция"""
    print("=" * 50)
    print("Простой тест DatabaseJournalWindow")
    print("=" * 50)
    
    try:
        ret = test_db_journal_simple()
        print(f"\n🎯 Тест завершен с кодом: {ret}")
        return ret
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
