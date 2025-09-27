#!/usr/bin/env python3
"""
Пример использования GStreamerVideoCapture для захвата видео.
"""

import sys
import os
import time
import cv2

# Добавляем путь к модулю evileye
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from evileye.capture import VideoCaptureGStreamer, CaptureDeviceType


def test_ip_camera():
    """Тест с IP камерой (RTSP)"""
    print("Тестирование IP камеры...")
    
    capture = VideoCaptureGStreamer()
    
    # Настройка параметров для IP камеры
    params = {
        'source': 'IpCamera',
        'camera': 'rtsp://192.168.1.100:554/stream1',  # Замените на ваш RTSP URL
        'username': 'admin',  # Замените на ваши данные
        'password': 'password',
        'desired_fps': 30,
        'source_ids': [0],
        'source_names': ['ip_camera']
    }
    
    try:
        capture.set_params(params)
        capture.init()
        
        print(f"Источник открыт: {capture.is_opened()}")
        print(f"Информация о источнике: {capture.get_source_info()}")
        
        # Запуск захвата
        capture.start()
        
        # Получение кадров в течение 10 секунд
        start_time = time.time()
        frame_count = 0
        
        while time.time() - start_time < 10:
            frames = capture.get()
            if frames:
                frame_count += len(frames)
                for frame in frames:
                    print(f"Получен кадр {frame.frame.frame_id} от источника {frame.source_name}")
                    
                    # Показать кадр (опционально)
                    cv2.imshow('GStreamer Capture', frame.frame.image)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break
            
            time.sleep(0.033)  # ~30 FPS
        
        print(f"Получено кадров: {frame_count}")
        
    except Exception as e:
        print(f"Ошибка при тестировании IP камеры: {e}")
    finally:
        capture.stop()
        capture.release()
        cv2.destroyAllWindows()


def test_video_file():
    """Тест с видео файлом"""
    print("Тестирование видео файла...")
    
    capture = VideoCaptureGStreamer()
    
    # Настройка параметров для видео файла
    params = {
        'source': 'VideoFile',
        'camera': '/path/to/your/video.mp4',  # Замените на путь к вашему видео
        'desired_fps': 25,
        'source_ids': [0],
        'source_names': ['video_file']
    }
    
    try:
        capture.set_params(params)
        capture.init()
        
        print(f"Источник открыт: {capture.is_opened()}")
        print(f"Информация о источнике: {capture.get_source_info()}")
        
        # Запуск захвата
        capture.start()
        
        # Получение кадров
        frame_count = 0
        while True:
            frames = capture.get()
            if frames:
                frame_count += len(frames)
                for frame in frames:
                    print(f"Получен кадр {frame.frame.frame_id}")
                    
                    # Показать кадр
                    cv2.imshow('GStreamer Video File', frame.frame.image)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break
            else:
                # Если кадров нет, возможно видео закончилось
                time.sleep(0.1)
                if capture.is_finished():
                    break
            
            time.sleep(0.04)  # 25 FPS
        
        print(f"Получено кадров: {frame_count}")
        
    except Exception as e:
        print(f"Ошибка при тестировании видео файла: {e}")
    finally:
        capture.stop()
        capture.release()
        cv2.destroyAllWindows()


def test_usb_camera():
    """Тест с USB камерой"""
    print("Тестирование USB камеры...")
    
    capture = VideoCaptureGStreamer()
    
    # Настройка параметров для USB камеры
    params = {
        'source': 'Device',
        'camera': '0',  # ID устройства (/dev/video0)
        'desired_fps': 30,
        'source_ids': [0],
        'source_names': ['usb_camera']
    }
    
    try:
        capture.set_params(params)
        capture.init()
        
        print(f"Источник открыт: {capture.is_opened()}")
        print(f"Информация о источнике: {capture.get_source_info()}")
        
        # Запуск захвата
        capture.start()
        
        # Получение кадров в течение 10 секунд
        start_time = time.time()
        frame_count = 0
        
        while time.time() - start_time < 10:
            frames = capture.get()
            if frames:
                frame_count += len(frames)
                for frame in frames:
                    print(f"Получен кадр {frame.frame.frame_id}")
                    
                    # Показать кадр
                    cv2.imshow('GStreamer USB Camera', frame.frame.image)
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        break
            
            time.sleep(0.033)  # ~30 FPS
        
        print(f"Получено кадров: {frame_count}")
        
    except Exception as e:
        print(f"Ошибка при тестировании USB камеры: {e}")
    finally:
        capture.stop()
        capture.release()
        cv2.destroyAllWindows()


def main():
    """Главная функция для запуска тестов"""
    print("GStreamer Video Capture - Примеры использования")
    print("=" * 50)
    
    # Выберите тест для запуска
    print("Доступные тесты:")
    print("1. IP камера (RTSP)")
    print("2. Видео файл")
    print("3. USB камера")
    
    choice = input("Выберите тест (1-3): ").strip()
    
    if choice == '1':
        test_ip_camera()
    elif choice == '2':
        test_video_file()
    elif choice == '3':
        test_usb_camera()
    else:
        print("Неверный выбор. Запуск теста USB камеры по умолчанию...")
        test_usb_camera()


if __name__ == "__main__":
    main()
