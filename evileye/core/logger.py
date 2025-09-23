#!/usr/bin/env python3
"""
Утилиты для логирования в EvilEye

Предоставляет удобные функции для логирования в различных модулях приложения.
"""

import logging
import functools
import time
from typing import Any, Callable, Optional
from contextlib import contextmanager


def get_module_logger(module_name: str) -> logging.Logger:
    """
    Получить логгер для указанного модуля
    
    Args:
        module_name: Имя модуля (например, __name__)
        
    Returns:
        Логгер для модуля
    """
    return logging.getLogger(f"evileye.{module_name.split('.')[-1]}")


def log_function_call(logger: Optional[logging.Logger] = None, 
                     level: int = logging.DEBUG,
                     log_args: bool = True,
                     log_result: bool = True):
    """
    Декоратор для логирования вызовов функций
    
    Args:
        logger: Логгер для использования (если None, будет создан автоматически)
        level: Уровень логирования
        log_args: Логировать аргументы функции
        log_result: Логировать результат функции
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if logger is None:
                func_logger = get_module_logger(func.__module__)
            else:
                func_logger = logger
            
            # Логируем начало выполнения
            if log_args:
                func_logger.log(level, f"Вызов {func.__name__} с аргументами: args={args}, kwargs={kwargs}")
            else:
                func_logger.log(level, f"Вызов {func.__name__}")
            
            try:
                result = func(*args, **kwargs)
                
                if log_result:
                    func_logger.log(level, f"Функция {func.__name__} завершена успешно, результат: {result}")
                else:
                    func_logger.log(level, f"Функция {func.__name__} завершена успешно")
                
                return result
            except Exception as e:
                func_logger.error(f"Error in function {func.__name__}: {e}")
                raise
        
        return wrapper
    return decorator


def log_execution_time(logger: Optional[logging.Logger] = None,
                      level: int = logging.INFO,
                      log_args: bool = False):
    """
    Декоратор для логирования времени выполнения функций
    
    Args:
        logger: Логгер для использования
        level: Уровень логирования
        log_args: Логировать аргументы функции
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if logger is None:
                func_logger = get_module_logger(func.__module__)
            else:
                func_logger = logger
            
            start_time = time.time()
            
            if log_args:
                func_logger.log(level, f"Начало выполнения {func.__name__} с аргументами: args={args}, kwargs={kwargs}")
            else:
                func_logger.log(level, f"Начало выполнения {func.__name__}")
            
            try:
                result = func(*args, **kwargs)
                execution_time = time.time() - start_time
                func_logger.log(level, f"Функция {func.__name__} выполнена за {execution_time:.4f} секунд")
                return result
            except Exception as e:
                execution_time = time.time() - start_time
                func_logger.error(f"Error in function {func.__name__} after {execution_time:.4f} seconds: {e}")
                raise
        
        return wrapper
    return decorator


@contextmanager
def log_context(logger: logging.Logger, 
               message: str, 
               level: int = logging.INFO,
               log_start: bool = True,
               log_end: bool = True):
    """
    Контекстный менеджер для логирования блоков кода
    
    Args:
        logger: Логгер для использования
        message: Сообщение для логирования
        level: Уровень логирования
        log_start: Логировать начало блока
        log_end: Логировать конец блока
    """
    if log_start:
        logger.log(level, f"Начало: {message}")
    
    start_time = time.time()
    
    try:
        yield
    except Exception as e:
        execution_time = time.time() - start_time
        logger.error(f"Error in block '{message}' after {execution_time:.4f} seconds: {e}")
        raise
    finally:
        if log_end:
            execution_time = time.time() - start_time
            logger.log(level, f"Завершение: {message} (время выполнения: {execution_time:.4f} секунд)")


def log_performance_metric(logger: logging.Logger,
                          metric_name: str,
                          value: float,
                          unit: str = "",
                          level: int = logging.INFO):
    """
    Логирует метрику производительности
    
    Args:
        logger: Логгер для использования
        metric_name: Название метрики
        value: Значение метрики
        unit: Единица измерения
        level: Уровень логирования
    """
    unit_str = f" {unit}" if unit else ""
    logger.log(level, f"PERFORMANCE: {metric_name} = {value}{unit_str}")


def log_detection_result(logger: logging.Logger,
                        frame_id: int,
                        source_id: str,
                        detections_count: int,
                        processing_time: float):
    """
    Логирует результат детекции объектов
    
    Args:
        logger: Логгер для использования
        frame_id: ID кадра
        source_id: ID источника
        detections_count: Количество обнаруженных объектов
        processing_time: Время обработки в секундах
    """
    logger.info(f"Detection completed - Frame: {frame_id}, Source: {source_id}, "
                f"Objects: {detections_count}, Time: {processing_time:.4f}s")


def log_tracking_result(logger: logging.Logger,
                       frame_id: int,
                       source_id: str,
                       active_tracks: int,
                       lost_tracks: int,
                       processing_time: float):
    """
    Логирует результат трекинга объектов
    
    Args:
        logger: Логгер для использования
        frame_id: ID кадра
        source_id: ID источника
        active_tracks: Количество активных треков
        lost_tracks: Количество потерянных треков
        processing_time: Время обработки в секундах
    """
    logger.info(f"Tracking completed - Frame: {frame_id}, Source: {source_id}, "
                f"Active tracks: {active_tracks}, Lost: {lost_tracks}, "
                f"Time: {processing_time:.4f}s")


def log_pipeline_step(logger: logging.Logger,
                      step_name: str,
                      input_count: int,
                      output_count: int,
                      processing_time: float,
                      dropped_count: int = 0):
    """
    Логирует выполнение шага пайплайна
    
    Args:
        logger: Логгер для использования
        step_name: Название шага
        input_count: Количество входных элементов
        output_count: Количество выходных элементов
        processing_time: Время обработки в секундах
        dropped_count: Количество отброшенных элементов
    """
    dropped_info = f", Dropped: {dropped_count}" if dropped_count > 0 else ""
    logger.debug(f"Pipeline step '{step_name}': "
                f"Input: {input_count}, Output: {output_count}{dropped_info}, "
                f"Time: {processing_time:.4f}s")


def log_error_with_context(logger: logging.Logger,
                          error: Exception,
                          context: str = "",
                          level: int = logging.ERROR):
    """
    Логирует ошибку с контекстом
    
    Args:
        logger: Логгер для использования
        error: Исключение
        context: Контекст ошибки
        level: Уровень логирования
    """
    context_str = f" в контексте: {context}" if context else ""
    logger.log(level, f"Ошибка{context_str}: {type(error).__name__}: {error}")


def log_system_startup(logger: logging.Logger, config_info: dict):
    """
    Логирует информацию о запуске системы
    
    Args:
        logger: Логгер для использования
        config_info: Информация о конфигурации
    """
    logger.info("=== Starting EvilEye ===")
    logger.info(f"Configuration: {config_info}")
    logger.info("=" * 30)


def log_system_shutdown(logger: logging.Logger, reason: str = "Нормальное завершение"):
    """
    Логирует информацию о завершении системы
    
    Args:
        logger: Логгер для использования
        reason: Причина завершения
    """
    logger.info("=== EvilEye Shutdown ===")
    logger.info(f"Reason: {reason}")
    logger.info("=" * 30)
