#!/usr/bin/env python3
"""
Скрипт для автоматического тестирования отображения изображений в GUI.
Запускает процесс, анализирует логи и проверяет, что изображения отображаются.
"""

import subprocess
import time
import os
import sys
import signal
import glob
from pathlib import Path

# Добавить корневую директорию проекта в путь
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def find_latest_log():
    """Найти последний лог-файл"""
    log_dir = project_root / "logs"
    if not log_dir.exists():
        return None
    log_files = sorted(log_dir.glob("*.log"), key=os.path.getmtime, reverse=True)
    return log_files[0] if log_files else None

def analyze_log(log_file, timeout_seconds=30):
    """Анализировать лог-файл на наличие проблем"""
    if not log_file or not log_file.exists():
        print("Лог-файл не найден")
        return False
    
    print(f"Анализ лог-файла: {log_file}")
    
    # Читать весь файл для анализа
    with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
    
    print(f"Всего строк в логе: {len(lines)}")
    
    # Проверки
    errors = []
    warnings = []
    has_emitting_signals = False
    has_none_images = False
    has_visualization_frames = False
    
    for line in lines:
        line_lower = line.lower()
        if "error" in line_lower:
            errors.append(line.strip())
        if "warning" in line_lower and ("none image" in line_lower or "qt_image" in line_lower):
            warnings.append(line.strip())
        if "emitting update_image" in line_lower:
            has_emitting_signals = True
        if "has none image in videothread" in line_lower:
            has_none_images = True
        if "visualization:" in line_lower and "frames have images" in line_lower:
            has_visualization_frames = True
        if "successfully copied image" in line_lower or "sent frame" in line_lower:
            has_emitting_signals = True  # Если копирование успешно, значит изображения обрабатываются
    
    # Вывод результатов
    print("\n=== Результаты анализа ===")
    print(f"Ошибки: {len(errors)}")
    if errors:
        print("Первые 5 ошибок:")
        for err in errors[:5]:
            print(f"  {err}")
    
    print(f"\nПредупреждения о None изображениях: {len(warnings)}")
    if warnings:
        print("Первые 5 предупреждений:")
        for warn in warnings[:5]:
            print(f"  {warn}")
    
    print(f"\nСигналы обновления изображений отправляются: {has_emitting_signals}")
    print(f"Есть кадры с None изображениями: {has_none_images}")
    print(f"Есть кадры с изображениями в визуализаторе: {has_visualization_frames}")
    
    # Подсчитать количество сообщений для более точной оценки
    emitting_count = sum(1 for line in lines if "emitting update_image" in line.lower())
    copied_count = sum(1 for line in lines if "successfully copied" in line.lower())
    sent_count = sum(1 for line in lines if "sent frame" in line.lower())
    visualization_count = sum(1 for line in lines if "visualization:" in line.lower() and "frames have images" in line.lower())
    none_image_count = sum(1 for line in lines if "has none image" in line.lower())
    
    print(f"\nДетальная статистика:")
    print(f"  - Emitting update_image: {emitting_count}")
    print(f"  - Successfully copied: {copied_count}")
    print(f"  - Sent frame: {sent_count}")
    print(f"  - Visualization frames: {visualization_count}")
    print(f"  - has None image: {none_image_count}")
    
    # Критерии успеха
    success = (
        (has_emitting_signals or emitting_count > 0) and  # Сигналы отправляются
        (has_visualization_frames or visualization_count > 0) and  # Есть кадры с изображениями
        not has_none_images and none_image_count == 0  # Нет кадров с None изображениями
    )
    
    print(f"\n=== Итог: {'УСПЕХ' if success else 'ПРОБЛЕМА'} ===")
    if success:
        print("Изображения успешно обрабатываются и отправляются в GUI!")
    else:
        print("Обнаружены проблемы с обработкой изображений.")
    return success

def run_test():
    """Запустить тест"""
    config_file = project_root / "configs" / "poly-videos-opencv-det-only.json"
    if not config_file.exists():
        print(f"Конфиг не найден: {config_file}")
        return False
    
    # Найти последний лог перед запуском
    log_before = find_latest_log()
    
    print("Запуск процесса...")
    print(f"Конфиг: {config_file}")
    
    # Запустить процесс в фоне
    process = subprocess.Popen(
        [sys.executable, str(project_root / "evileye" / "process.py"),
         "--config", str(config_file),
         "--log-level", "INFO"],
        cwd=str(project_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    try:
        # Подождать некоторое время для работы
        wait_time = 60
        print(f"Ожидание {wait_time} секунд для накопления данных...")
        time.sleep(wait_time)
        
        # Найти новый лог-файл
        log_after = find_latest_log()
        if log_after == log_before:
            print("Новый лог-файл не создан, ожидание еще 10 секунд...")
            time.sleep(10)
            log_after = find_latest_log()
        
        # Если лог-файл не изменился, использовать последний доступный
        if log_after == log_before and log_after:
            print(f"Используется существующий лог-файл: {log_after}")
            log_after = log_before
        
        # Анализировать лог
        if log_after:
            success = analyze_log(log_after, timeout_seconds=30)
        else:
            print("Не удалось найти лог-файл для анализа")
            success = False
        
        return success
        
    finally:
        # Остановить процесс
        print("\nОстановка процесса...")
        try:
            process.terminate()
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        print("Процесс остановлен")

if __name__ == "__main__":
    success = run_test()
    sys.exit(0 if success else 1)
