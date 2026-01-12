from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Optional

from evileye.core.logger import get_module_logger
from evileye.video_recorder.recording_params import RecordingParams
from evileye.video_recorder.utils import iter_segments, validate_video_file


class VideoValidator:
    """
    Периодическая проверка целостности видеофайлов в фоновом потоке.
    
    Проверяет все видеофайлы в директории записи с заданным интервалом
    и удаляет битые файлы.
    """
    
    def __init__(self, params: RecordingParams, check_interval_seconds: float = 300.0, 
                 min_file_age_seconds: float = 120.0):
        """
        Инициализация валидатора.
        
        Args:
            params: Параметры записи
            check_interval_seconds: Интервал между проверками в секундах (по умолчанию 5 минут)
            min_file_age_seconds: Минимальный возраст файла для проверки (по умолчанию 2 минуты)
        """
        self.logger = get_module_logger("video_validator")
        self.params = params
        self.check_interval_seconds = check_interval_seconds
        self.min_file_age_seconds = min_file_age_seconds
        
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._is_running = False
    
    def start(self) -> None:
        """Запустить валидатор в отдельном потоке."""
        if self._is_running:
            self.logger.warning("VideoValidator is already running")
            return
        
        if not self.params.validate_video_integrity:
            self.logger.debug("Video validation is disabled in params, skipping validator start")
            return
        
        self._stop_event.clear()
        self._is_running = True
        self._thread = threading.Thread(target=self._validation_loop, daemon=True, name="VideoValidator")
        self._thread.start()
        self.logger.info(f"VideoValidator started (check_interval={self.check_interval_seconds}s, "
                        f"min_file_age={self.min_file_age_seconds}s)")
    
    def stop(self) -> None:
        """Остановить валидатор."""
        if not self._is_running:
            return
        
        self._stop_event.set()
        self._is_running = False
        
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
            if self._thread.is_alive():
                self.logger.warning("VideoValidator thread did not stop in time")
        
        self.logger.info("VideoValidator stopped")
    
    def _validation_loop(self) -> None:
        """Основной цикл проверки файлов."""
        while not self._stop_event.is_set():
            try:
                self._validate_all_files()
            except Exception as e:
                self.logger.error(f"Error in validation loop: {e}", exc_info=True)
            
            # Ждать до следующей проверки или остановки
            if self._stop_event.wait(timeout=self.check_interval_seconds):
                break
    
    def _validate_all_files(self) -> None:
        """Проверить все видеофайлы в директории записи."""
        try:
            base = Path(self.params.out_dir)
            if not base.exists():
                return
            
            validate_integrity = getattr(self.params, 'validate_video_integrity', True)
            validation_timeout = getattr(self.params, 'video_validation_timeout', 2.0)
            
            corrupted_count = 0
            checked_count = 0
            current_time = time.time()
            
            # Рекурсивно сканировать все поддиректории
            for date_dir in base.iterdir():
                if self._stop_event.is_set():
                    break
                
                if not date_dir.is_dir():
                    continue
                
                for camera_dir in date_dir.iterdir():
                    if self._stop_event.is_set():
                        break
                    
                    if not camera_dir.is_dir():
                        continue
                    
                    # Проверить все видеофайлы в директории камеры
                    for p, mtime in iter_segments(camera_dir, [self.params.container, 'mp4', 'mkv']):
                        if self._stop_event.is_set():
                            break
                        
                        # Пропустить файлы с паттерном %05d (уже обрабатываются в других местах)
                        if '%' in p.name:
                            continue
                        
                        # Проверить возраст файла
                        file_age = current_time - mtime
                        if file_age < self.min_file_age_seconds:
                            continue
                        
                        checked_count += 1
                        
                        # Проверить файл на целостность (размер уже проверен в других местах)
                        if validate_integrity:
                            if not validate_video_file(p, validation_timeout):
                                # Файл поврежден, удалить его
                                try:
                                    p.unlink(missing_ok=True)
                                    corrupted_count += 1
                                    self.logger.info(f"VideoValidator: deleted corrupted file: {p}")
                                except Exception as e:
                                    self.logger.warning(f"VideoValidator: failed to delete corrupted file {p}: {e}")
            
            if checked_count > 0:
                self.logger.debug(f"VideoValidator: checked {checked_count} files, "
                                f"deleted {corrupted_count} corrupted files")
        
        except Exception as e:
            self.logger.error(f"Error validating files: {e}", exc_info=True)
    
    def is_running(self) -> bool:
        """Проверить, запущен ли валидатор."""
        return self._is_running
