"""
Утилиты для работы с конфигурацией базы данных.

Предоставляет функции для загрузки и вычисления database_config
с учетом всех источников данных (database_config.json, credentials, params).
"""
import os
import json
from pathlib import Path
from typing import Dict, Optional, Any
from ..core.logger import get_module_logger

logger = get_module_logger("database_config_utils")


def get_database_config_path() -> Path:
    """Получить путь к файлу database_config.json"""
    return Path(__file__).parent.parent / "database_config.json"


def load_database_config_from_file() -> Optional[Dict[str, Any]]:
    """
    Загрузить базовую конфигурацию БД из файла database_config.json.
    
    Returns:
        Словарь с конфигурацией БД или None, если файл не найден
    """
    config_path = get_database_config_path()
    try:
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            logger.debug(f"Loaded database_config from {config_path}")
            return config
        else:
            logger.warning(f"database_config.json not found at {config_path}")
            return None
    except Exception as e:
        logger.error(f"Failed to load database_config.json: {e}")
        return None


def compute_database_config(
    use_database: bool = True,
    credentials: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Вычислить полную конфигурацию БД с учетом всех источников.
    
    Логика вычисления:
    1. Загружается базовая конфигурация из database_config.json
    2. Заполняются значения по умолчанию из credentials
    3. Переопределяются значения из params['database'] (если есть)
    
    Args:
        use_database: Включена ли БД (если False, возвращает пустой config)
        credentials: Словарь с credentials (опционально)
        params: Словарь с параметрами конфигурации (опционально)
    
    Returns:
        Полная конфигурация БД в формате:
        {
            "database": {...},
            "database_adapters": {...}
        }
    """
    if not use_database:
        logger.debug("Database disabled, returning empty config")
        return {"database": {}, "database_adapters": {}}
    
    # Загружаем базовую конфигурацию из файла
    database_config = load_database_config_from_file()
    if database_config is None:
        # Если файл не найден, создаем минимальную структуру
        database_config = {"database": {}, "database_adapters": {}}
    
    # Убеждаемся, что есть ключи database и database_adapters
    if "database" not in database_config:
        database_config["database"] = {}
    if "database_adapters" not in database_config:
        database_config["database_adapters"] = {}
    
    # Получаем credentials с значениями по умолчанию
    database_creds = {}
    if credentials:
        database_creds = credentials.get("database", {}) or {}
    
    # Устанавливаем значения по умолчанию для credentials
    database_creds.setdefault("user_name", "postgres")
    database_creds.setdefault("password", "")
    database_creds.setdefault("database_name", "evil_eye_db")
    database_creds.setdefault("host_name", "localhost")
    database_creds.setdefault("port", 5432)
    database_creds.setdefault("admin_user_name", "postgres")
    database_creds.setdefault("admin_password", "")
    
    # Объединяем значения: сначала из файла, потом из credentials
    db_section = database_config["database"]
    db_section.setdefault("user_name", database_creds["user_name"])
    db_section.setdefault("password", database_creds["password"])
    db_section.setdefault("database_name", database_creds["database_name"])
    db_section.setdefault("host_name", database_creds["host_name"])
    db_section.setdefault("port", database_creds["port"])
    db_section.setdefault("admin_user_name", database_creds["admin_user_name"])
    db_section.setdefault("admin_password", database_creds["admin_password"])
    
    # Переопределяем значения из params['database'], если есть
    if params and "database" in params:
        params_db = params["database"]
        if isinstance(params_db, dict):
            # Обновляем только те ключи, которые есть в params
            if "database_name" in params_db:
                db_section["database_name"] = params_db["database_name"]
            if "host_name" in params_db:
                db_section["host_name"] = params_db["host_name"]
            if "port" in params_db:
                db_section["port"] = params_db["port"]
            if "image_dir" in params_db:
                db_section["image_dir"] = params_db["image_dir"]
            if "preview_width" in params_db:
                db_section["preview_width"] = params_db["preview_width"]
            if "preview_height" in params_db:
                db_section["preview_height"] = params_db["preview_height"]
    
    logger.debug(f"Computed database_config with database keys: {list(db_section.keys())}")
    return database_config


def ensure_database_config_complete(database_config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Убедиться, что database_config содержит все необходимые ключи.
    Загружает недостающие ключи из файла, если они отсутствуют.
    
    Args:
        database_config: Существующая конфигурация БД (может быть неполной)
    
    Returns:
        Полная конфигурация БД с гарантированными ключами 'database' и 'database_adapters'
    """
    if not database_config:
        database_config = {}
    
    # Загружаем базовую конфигурацию из файла для дополнения
    file_config = load_database_config_from_file()
    
    # Убеждаемся, что есть ключ 'database'
    if "database" not in database_config:
        if file_config and "database" in file_config:
            database_config["database"] = file_config["database"].copy()
            logger.info("Loaded 'database' section from database_config.json file")
        else:
            database_config["database"] = {}
            logger.warning("'database' section not found, using empty dict")
    
    # Убеждаемся, что есть ключ 'database_adapters'
    if "database_adapters" not in database_config:
        if file_config and "database_adapters" in file_config:
            database_config["database_adapters"] = file_config["database_adapters"].copy()
            logger.info("Loaded 'database_adapters' section from database_config.json file")
        else:
            database_config["database_adapters"] = {}
            logger.warning("'database_adapters' section not found, using empty dict")
    
    return database_config
