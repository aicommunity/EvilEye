#!/usr/bin/env python3
"""
Centralized logging configuration for EvilEye

Provides consistent logging throughout the application with automatic
creation of logs folder and configuration of various logging levels.
"""

import logging
import logging.handlers
import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime


class EvilEyeLoggingConfig:
    """Centralized logging configuration for EvilEye"""
    
    def __init__(self, 
                 log_level: str = "INFO",
                 log_to_console: bool = True,
                 log_to_file: bool = True,
                 log_dir: Optional[str] = None,
                 max_file_size: int = 10 * 1024 * 1024,  # 10MB
                 backup_count: int = 5):
        """
        Инициализация конфигурации логирования
        
        Args:
            log_level: Уровень логирования (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            log_to_console: Логировать в консоль
            log_to_file: Логировать в файлы
            log_dir: Папка для логов (по умолчанию logs/ в корне проекта)
            max_file_size: Максимальный размер файла лога в байтах
            backup_count: Количество резервных файлов логов
        """
        self.log_level = getattr(logging, log_level.upper(), logging.INFO)
        self.log_to_console = log_to_console
        self.log_to_file = log_to_file
        self.max_file_size = max_file_size
        self.backup_count = backup_count
        
        # Определяем папку для логов
        if log_dir is None:
            # Используем рабочую директорию запуска процесса
            self.log_dir = Path.cwd() / "logs"
        else:
            self.log_dir = Path(log_dir)
        
        # Создаем папку для логов если она не существует
        self._ensure_log_directory()
        
        # Настройка форматов
        self.console_format = "%(asctime)s - %(levelname)s - %(message)s"
        self.file_format = "%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s"
        
        # Пути к файлам логов
        self.main_log_file = self.log_dir / "evileye_main.log"
        self.debug_log_file = self.log_dir / "evileye_debug.log"
        self.error_log_file = self.log_dir / "evileye_errors.log"
        self.performance_log_file = self.log_dir / "evileye_performance.log"
    
    def _ensure_log_directory(self):
        """Creates logs folder if it doesn't exist"""
        try:
            self.log_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print(f"Error creating logs folder {self.log_dir}: {e}")
            # Fallback to temporary folder
            import tempfile
            self.log_dir = Path(tempfile.gettempdir()) / "evileye_logs"
            self.log_dir.mkdir(parents=True, exist_ok=True)
    
    def setup_logging(self, logger_name: str = "evileye") -> logging.Logger:
        """
        Настраивает логирование для указанного логгера
        
        Args:
            logger_name: Имя логгера
            
        Returns:
            Настроенный логгер
        """
        # Создаем логгер
        logger = logging.getLogger(logger_name)
        logger.setLevel(self.log_level)
        
        # Очищаем существующие обработчики
        logger.handlers.clear()
        
        # Настраиваем форматтеры
        console_formatter = logging.Formatter(self.console_format)
        file_formatter = logging.Formatter(self.file_format)
        
        # Обработчик для консоли
        if self.log_to_console:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(self.log_level)
            console_handler.setFormatter(console_formatter)
            logger.addHandler(console_handler)
        
        # Обработчики для файлов
        if self.log_to_file:
            # Основной лог (INFO и выше)
            main_handler = logging.handlers.RotatingFileHandler(
                self.main_log_file,
                maxBytes=self.max_file_size,
                backupCount=self.backup_count,
                encoding='utf-8'
            )
            main_handler.setLevel(logging.INFO)
            main_handler.setFormatter(file_formatter)
            logger.addHandler(main_handler)
            
            # Отладочный лог (DEBUG и выше)
            debug_handler = logging.handlers.RotatingFileHandler(
                self.debug_log_file,
                maxBytes=self.max_file_size,
                backupCount=self.backup_count,
                encoding='utf-8'
            )
            debug_handler.setLevel(logging.DEBUG)
            debug_handler.setFormatter(file_formatter)
            logger.addHandler(debug_handler)
            
            # Лог ошибок (ERROR и выше)
            error_handler = logging.handlers.RotatingFileHandler(
                self.error_log_file,
                maxBytes=self.max_file_size,
                backupCount=self.backup_count,
                encoding='utf-8'
            )
            error_handler.setLevel(logging.ERROR)
            error_handler.setFormatter(file_formatter)
            logger.addHandler(error_handler)
        
        # Предотвращаем дублирование логов
        logger.propagate = False
        
        return logger
    
    def get_performance_logger(self) -> logging.Logger:
        """Возвращает специальный логгер для метрик производительности"""
        perf_logger = logging.getLogger("evileye.performance")
        perf_logger.setLevel(logging.INFO)
        
        # Очищаем существующие обработчики
        perf_logger.handlers.clear()
        
        if self.log_to_file:
            perf_handler = logging.handlers.RotatingFileHandler(
                self.performance_log_file,
                maxBytes=self.max_file_size,
                backupCount=self.backup_count,
                encoding='utf-8'
            )
            perf_handler.setLevel(logging.INFO)
            perf_formatter = logging.Formatter(
                "%(asctime)s - %(message)s"
            )
            perf_handler.setFormatter(perf_formatter)
            perf_logger.addHandler(perf_handler)
        
        perf_logger.propagate = False
        return perf_logger
    
    def get_log_info(self) -> Dict[str, Any]:
        """Возвращает информацию о настройках логирования"""
        return {
            "log_level": logging.getLevelName(self.log_level),
            "log_dir": str(self.log_dir),
            "log_to_console": self.log_to_console,
            "log_to_file": self.log_to_file,
            "max_file_size": self.max_file_size,
            "backup_count": self.backup_count,
            "log_files": {
                "main": str(self.main_log_file),
                "debug": str(self.debug_log_file),
                "error": str(self.error_log_file),
                "performance": str(self.performance_log_file)
            }
        }


def setup_evileye_logging(log_level: str = "INFO", 
                         log_to_console: bool = True,
                         log_to_file: bool = True,
                         log_dir: Optional[str] = None) -> logging.Logger:
    """
    Удобная функция для быстрой настройки логирования EvilEye
    
    Args:
        log_level: Уровень логирования
        log_to_console: Логировать в консоль
        log_to_file: Логировать в файлы
        log_dir: Папка для логов
        
    Returns:
        Настроенный логгер
    """
    config = EvilEyeLoggingConfig(
        log_level=log_level,
        log_to_console=log_to_console,
        log_to_file=log_to_file,
        log_dir=log_dir
    )
    
    return config.setup_logging()


def get_logger(name: str = "evileye") -> logging.Logger:
    """
    Получить логгер для указанного модуля
    
    Args:
        name: Имя модуля (например, "evileye.controller")
        
    Returns:
        Логгер для указанного модуля
    """
    return logging.getLogger(name)


def log_system_info(logger: logging.Logger):
    """Логирует информацию о системе"""
    import platform
    import psutil
    
    logger.info("=== EvilEye System Information ===")
    logger.info(f"Python version: {sys.version}")
    logger.info(f"Platform: {platform.platform()}")
    logger.info(f"CPU count: {psutil.cpu_count()}")
    logger.info(f"Memory: {psutil.virtual_memory().total / (1024**3):.1f} GB")
    logger.info(f"Working directory: {os.getcwd()}")
    logger.info("=" * 40)
