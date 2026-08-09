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

_IMAGE_DIR_KEYS = ("image_dir", "images_dir")
_DEFAULT_IMAGE_DIR = "EvilEyeData"


def _path_is_writable_dir(path: Path) -> tuple[bool, str]:
    """Best-effort check that ``path`` can be created and written to."""
    try:
        path.mkdir(parents=True, exist_ok=True)
        if not path.is_dir():
            return False, f"not a directory: {path}"
        if not os.access(path, os.W_OK):
            return False, f"not writable: {path}"
        return True, ""
    except Exception as exc:
        return False, str(exc)


def resolve_writable_image_dir(
        preferred: Optional[str] = None,
        *,
        fallback: str = _DEFAULT_IMAGE_DIR,
        env_var: str = "EVILEYE_DATA_DIR",
) -> str:
    """Pick a writable image/data directory for JSON adapters and event media.

    Preference order: explicit ``preferred``, ``EVILEYE_DATA_DIR``, then ``fallback``
    (local ``EvilEyeData``). Unwritable preferred paths fall back with a single warning.
    """
    candidates: list[str] = []
    if preferred not in (None, ""):
        candidates.append(str(preferred))
    env_dir = os.environ.get(env_var)
    if env_dir not in (None, "") and env_dir not in candidates:
        candidates.append(str(env_dir))
    if fallback not in candidates:
        candidates.append(fallback)

    last_reason = ""
    for idx, raw in enumerate(candidates):
        path = Path(raw)
        if not path.is_absolute():
            path = path.resolve()
        ok, reason = _path_is_writable_dir(path)
        if ok:
            chosen = str(path)
            if idx > 0 and preferred not in (None, ""):
                logger.warning(
                    "image_dir %r is not writable (%s); falling back to %s",
                    preferred,
                    last_reason or reason,
                    chosen,
                )
            return chosen
        last_reason = reason

    # Last resort: return resolved fallback even if check failed (caller may still fail loudly).
    fallback_path = Path(fallback)
    if not fallback_path.is_absolute():
        fallback_path = fallback_path.resolve()
    logger.warning(
        "No writable image_dir found (last error: %s); using %s",
        last_reason,
        fallback_path,
    )
    return str(fallback_path)


def _normalize_image_dir_keys(db_section: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize legacy `images_dir` vs `image_dir` naming.

    We keep both keys in the resulting dict for backward compatibility with older code/configs,
    but treat `image_dir` as canonical.
    """
    if not isinstance(db_section, dict):
        return {}

    image_dir = db_section.get("image_dir")
    images_dir = db_section.get("images_dir")

    # Prefer explicit canonical key; otherwise fall back to legacy key.
    chosen = image_dir if image_dir not in (None, "") else images_dir
    if chosen not in (None, ""):
        db_section["image_dir"] = chosen
        db_section["images_dir"] = chosen
    return db_section


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

    # image_dir naming compatibility
    if "image_dir" not in db_section and "images_dir" not in db_section:
        db_section.setdefault("image_dir", "EvilEyeData")
        db_section.setdefault("images_dir", "EvilEyeData")
    _normalize_image_dir_keys(db_section)

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
            if any(k in params_db for k in _IMAGE_DIR_KEYS):
                chosen = params_db.get("image_dir") or params_db.get("images_dir")
                if chosen not in (None, ""):
                    db_section["image_dir"] = chosen
                    db_section["images_dir"] = chosen
            if "preview_width" in params_db:
                db_section["preview_width"] = params_db["preview_width"]
            if "preview_height" in params_db:
                db_section["preview_height"] = params_db["preview_height"]

    _normalize_image_dir_keys(db_section)

    logger.debug(f"Computed database_config with database keys: {list(db_section.keys())}")
    return database_config


def ensure_database_config_complete(database_config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Убедиться, что database_config содержит все необходимые ключи,
    при этом не перетирая уже заданные пользователем значения.
    
    Args:
        database_config: Существующая конфигурация БД (может быть неполной)
    
    Returns:
        Полная конфигурация БД с гарантированными ключами 'database' и 'database_adapters'
    """
    if not database_config:
        database_config = {}

    # Загружаем базовую конфигурацию из файла для ДОПОЛНЕНИЯ
    file_config = load_database_config_from_file()

    # Набор ключей, по которым можно распознать "плоскую" секцию database
    db_flat_keys = {
        "user_name",
        "password",
        "database_name",
        "host_name",
        "port",
        "admin_user_name",
        "admin_password",
        "image_dir",
        "images_dir",
        "preview_width",
        "preview_height",
        "tables",
    }

    # 1. Обеспечиваем наличие секции 'database'
    if "database" not in database_config:
        # Возможен сценарий, когда нам передали уже «плоскую» секцию database
        # (c ключами host_name/port и т.п.), но без обёртки 'database'
        if any(k in database_config for k in db_flat_keys):
            # Выделяем часть, похожую на секцию database, и оборачиваем её
            db_section = {k: v for k, v in database_config.items() if k in db_flat_keys}
            other_keys = {k: v for k, v in database_config.items() if k not in db_flat_keys}
            database_config = {
                **other_keys,
                "database": db_section,
            }
            logger.info(
                "Interpreting provided config as flattened 'database' section; "
                "wrapping it into full database_config structure"
            )
        elif file_config and "database" in file_config:
            # Если плоской секции нет, используем дефолты из файла
            database_config["database"] = file_config["database"].copy()
            logger.info("Loaded 'database' section from database_config.json file")
        else:
            database_config["database"] = {}
            logger.warning("'database' section not found, using empty dict")

    # 2. Обеспечиваем наличие секции 'database_adapters'
    if "database_adapters" not in database_config:
        if file_config and "database_adapters" in file_config:
            database_config["database_adapters"] = file_config["database_adapters"].copy()
            logger.info("Loaded 'database_adapters' section from database_config.json file")
        else:
            database_config["database_adapters"] = {}
            logger.warning("'database_adapters' section not found, using empty dict")

    # 3. Дополняем недостающие ключи внутри 'database' из файла,
    # НЕ перезаписывая уже заданные значения (host, port и т.п.)
    if file_config and "database" in file_config:
        db_section = database_config.get("database") or {}
        file_db_section = file_config.get("database") or {}
        for key, value in file_db_section.items():
            db_section.setdefault(key, value)
        database_config["database"] = db_section

    # Final normalization for image_dir/images_dir compatibility
    database_config["database"] = _normalize_image_dir_keys(database_config.get("database") or {})

    return database_config
