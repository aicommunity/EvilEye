"""Сервис управления конфигурацией."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

from evileye.core.logger import get_module_logger
from evileye.utils.json_io import load_json, save_json_atomic


class ConfigurationService:
    """Сервис для управления конфигурацией системы."""

    def __init__(self):
        """Инициализация сервиса."""
        self.logger = get_module_logger("config_service")
        self._loaded_config: Optional[Dict[str, Any]] = None
        self._credentials_loaded: bool = False

    def load_config(self, file_path: str) -> Dict[str, Any]:
        """Загрузить конфигурацию из файла.

        Args:
            file_path: Путь к файлу конфигурации

        Returns:
            Загруженная конфигурация

        Raises:
            FileNotFoundError: Если файл не найден
            json.JSONDecodeError: Если файл содержит невалидный JSON
        """
        try:
            config = load_json(file_path)
            self._loaded_config = config
            self.logger.info(f"Configuration loaded from: {file_path}")
            return config
        except FileNotFoundError:
            self.logger.error(f"Configuration file not found: {file_path}")
            raise
        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON in configuration file: {e}")
            raise

    def save_config(self, config: Dict[str, Any], file_path: str) -> bool:
        """Сохранить конфигурацию в файл атомарно.

        Args:
            config: Конфигурация для сохранения
            file_path: Путь к файлу для сохранения

        Returns:
            True если сохранение успешно, False иначе
        """
        try:
            if not file_path:
                self.logger.error("No config file path specified for saving")
                return False
            ok = save_json_atomic(file_path, config)
            if ok:
                self.logger.info(f"Configuration saved to: {file_path}")
            return ok
        except Exception as e:
            self.logger.error(f"Failed to save configuration: {e}")
            return False

    def reconcile_credentials_fields(
            self,
            params: Dict[str, Any],
            loaded_config: Optional[Dict[str, Any]] = None,
            credentials_loaded: bool = False,
    ) -> None:
        """Удалить поля учетных данных из params, если их не было в исходной конфигурации.

        Args:
            params: Параметры для очистки
            loaded_config: Исходная загруженная конфигурация
            credentials_loaded: Были ли загружены учетные данные отдельно
        """
        try:
            config = loaded_config or self._loaded_config or {}
            pipeline = params.get('pipeline', {}) if isinstance(params, dict) else {}
            sources = pipeline.get('sources', []) if isinstance(pipeline, dict) else []
            if not isinstance(sources, list) or not sources:
                return

            try:
                orig_pipeline = config.get('pipeline', {})
                orig_sources = orig_pipeline.get('sources', []) if isinstance(orig_pipeline, dict) else []
            except Exception:
                orig_sources = []

            CRED_KEYS = {
                'user_name', 'username', 'password', 'pwd', 'login', 'token',
                'rtsp_user', 'rtsp_password', 'auth', 'api_key',
                'camera_login', 'camera_password'
            }

            def _strip_userinfo_from_url(url: str) -> str:
                try:
                    from urllib.parse import urlsplit, urlunsplit
                    parts = urlsplit(url)
                    netloc = parts.netloc
                    if '@' in netloc:
                        hostport = netloc.split('@', 1)[1]
                        new_parts = (parts.scheme, hostport, parts.path, parts.query, parts.fragment)
                        return urlunsplit(new_parts)
                    return url
                except Exception:
                    return url

            def _has_userinfo(url: str) -> bool:
                try:
                    from urllib.parse import urlsplit
                    parts = urlsplit(url)
                    return '@' in parts.netloc
                except Exception:
                    return '@' in (url or '')

            for idx, src in enumerate(sources):
                if not isinstance(src, dict):
                    continue
                orig_src = orig_sources[idx] if idx < len(orig_sources) and isinstance(orig_sources[idx], dict) else {}
                orig_cred_keys = {k for k in (orig_src.keys() if isinstance(orig_src, dict) else []) if k in CRED_KEYS}
                keys_to_remove = set()
                for k in list(src.keys()):
                    if k in CRED_KEYS and k not in orig_cred_keys:
                        keys_to_remove.add(k)
                for k in keys_to_remove:
                    try:
                        del src[k]
                    except Exception:
                        pass

                # Обработка учетных данных в URL камеры
                try:
                    cam_now = src.get('camera')
                    cam_orig = orig_src.get('camera') if isinstance(orig_src, dict) else None
                    if isinstance(cam_now, str):
                        if not isinstance(cam_orig, str) or not _has_userinfo(cam_orig):
                            src['camera'] = _strip_userinfo_from_url(cam_now)
                except Exception:
                    pass
        except Exception as e:
            self.logger.warning(f"Failed to reconcile credentials fields: {e}")

    def filter_model_class_mapping(
            self,
            params: Dict[str, Any],
            loaded_config: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Удалить model_class_mapping из params, если его не было в исходной конфигурации.

        Args:
            params: Параметры для фильтрации
            loaded_config: Исходная загруженная конфигурация
        """
        try:
            config = loaded_config or self._loaded_config or {}
            pipeline = params.get('pipeline', {}) if isinstance(params, dict) else {}
            detectors = pipeline.get('detectors', []) if isinstance(pipeline, dict) else []
            if not isinstance(detectors, list) or not detectors:
                return

            try:
                orig_pipeline = config.get('pipeline', {})
                orig_detectors = orig_pipeline.get('detectors', []) if isinstance(orig_pipeline, dict) else []
            except Exception:
                orig_detectors = []

            for idx, det in enumerate(detectors):
                if not isinstance(det, dict):
                    continue
                orig_det = orig_detectors[idx] if idx < len(orig_detectors) and isinstance(orig_detectors[idx],
                                                                                           dict) else {}
                if 'model_class_mapping' in det and ('model_class_mapping' not in orig_det):
                    try:
                        del det['model_class_mapping']
                    except Exception:
                        pass
        except Exception as e:
            self.logger.warning(f"Failed to filter model class mapping: {e}")

    def restrict_database_keys(
            self,
            params: Dict[str, Any],
            loaded_config: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Ограничить ключи секции database только теми, что были в исходной конфигурации.

        Args:
            params: Параметры для ограничения
            loaded_config: Исходная загруженная конфигурация
        """
        try:
            config = loaded_config or self._loaded_config or {}
            orig_db = config.get('database', {}) or {}
            if not isinstance(orig_db, dict):
                return
            current_db = params.get('database', {}) or {}
            if not isinstance(current_db, dict):
                params['database'] = {}
                return
            allowed_keys = set(orig_db.keys())
            params['database'] = {k: current_db[k] for k in current_db.keys() if k in allowed_keys}
        except Exception as e:
            self.logger.warning(f"Failed to restrict database keys: {e}")

    def get_loaded_config(self) -> Optional[Dict[str, Any]]:
        """Получить загруженную конфигурацию.

        Returns:
            Загруженная конфигурация или None
        """
        return self._loaded_config

    def set_loaded_config(self, config: Dict[str, Any]) -> None:
        """Установить загруженную конфигурацию.

        Args:
            config: Конфигурация для установки
        """
        self._loaded_config = config

    def ensure_api_preference(
            self,
            params: Dict[str, Any],
            loaded_config: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Restore apiPreference on sources from loaded config when present."""
        try:
            config = loaded_config or self._loaded_config or {}
            pipeline = params.get("pipeline", {}) if isinstance(params, dict) else {}
            sources = pipeline.get("sources", []) if isinstance(pipeline, dict) else []
            if not isinstance(sources, list) or not sources:
                return
            orig_pipeline = config.get("pipeline", {})
            orig_sources = (
                orig_pipeline.get("sources", [])
                if isinstance(orig_pipeline, dict)
                else []
            )
            for idx, src in enumerate(sources):
                if not isinstance(src, dict):
                    continue
                orig_src = (
                    orig_sources[idx]
                    if idx < len(orig_sources) and isinstance(orig_sources[idx], dict)
                    else {}
                )
                if isinstance(orig_src, dict) and "apiPreference" in orig_src:
                    src["apiPreference"] = orig_src.get("apiPreference")
        except Exception as e:
            self.logger.warning("Failed to ensure api preference: %s", e)

    def apply_save_sanitizers(
            self,
            params: Dict[str, Any],
            loaded_config: Optional[Dict[str, Any]] = None,
            credentials_loaded: bool = False,
    ) -> None:
        """Credentials, model_class_mapping, and database key sanitization before save."""
        config = loaded_config if loaded_config is not None else self._loaded_config
        self.reconcile_credentials_fields(params, config, credentials_loaded)
        self.filter_model_class_mapping(params, config)
        if isinstance(config, dict) and config:
            self.restrict_database_keys(params, config)

    def strip_root_pipeline_sections(self, params: Dict[str, Any]) -> None:
        """Remove pipeline sections accidentally promoted to config root."""
        pipe_keys = [
            "sources",
            "preprocessors",
            "detectors",
            "trackers",
            "mc_trackers",
            "attributes_roi",
            "attributes_classifier",
        ]
        for key in pipe_keys:
            if key in params:
                try:
                    del params[key]
                except Exception:
                    pass

    def propagate_record_config_to_sources(
            self,
            pipeline_params: Dict[str, Any],
            params: Dict[str, Any],
    ) -> None:
        """Merge global record config into each pipeline source."""
        try:
            record_cfg = (params or {}).get("record", {}) or {}
            if not isinstance(record_cfg, dict) or not record_cfg:
                return

            allow_custom_out_dir = bool(record_cfg.get("allow_custom_out_dir", False))
            db_image_dir = ((params or {}).get("database", {}) or {}).get("image_dir") or "EvilEyeData"
            image_dir_path = Path(db_image_dir)
            default_out_dir = (
                str(image_dir_path)
                if image_dir_path.is_absolute()
                else str(image_dir_path.resolve())
            )

            srcs = pipeline_params.get("sources", []) or []
            enabled_list = record_cfg.get("enabled_sources")
            for idx, source in enumerate(srcs):
                if not isinstance(source, dict):
                    continue
                per = dict(source.get("record", {})) if isinstance(source.get("record"), dict) else {}
                merged = {**record_cfg, **per}
                if allow_custom_out_dir:
                    if not merged.get("out_dir"):
                        merged["out_dir"] = default_out_dir
                else:
                    merged["out_dir"] = default_out_dir

                try:
                    sid = (source.get("source_ids") or [idx])[0]
                except Exception:
                    sid = idx
                sname = None
                try:
                    sname = (source.get("source_names") or [None])[0]
                except Exception:
                    sname = None

                if isinstance(enabled_list, dict) and len(enabled_list) > 0:
                    if str(sid) in enabled_list:
                        merged["enabled"] = bool(enabled_list[str(sid)])
                    elif sid in enabled_list:
                        merged["enabled"] = bool(enabled_list[sid])
                    elif sname and sname in enabled_list:
                        merged["enabled"] = bool(enabled_list[sname])
                    else:
                        merged["enabled"] = False
                elif isinstance(enabled_list, list) and len(enabled_list) > 0:
                    enabled = False
                    for item in enabled_list:
                        if isinstance(item, int) and item == sid:
                            enabled = True
                            break
                        if isinstance(item, str) and (
                            item == str(sid) or (sname and item == sname)
                        ):
                            enabled = True
                            break
                    merged["enabled"] = enabled
                else:
                    has_new_flags = ("continuous_recording_enabled" in merged) or (
                            "event_recording_enabled" in merged
                    )
                    if not has_new_flags:
                        if "enabled" in merged:
                            merged["continuous_recording_enabled"] = bool(
                                merged.get("enabled", False)
                            )
                            merged["event_recording_enabled"] = False
                        else:
                            merged["enabled"] = False
                            merged["continuous_recording_enabled"] = False
                            merged["event_recording_enabled"] = False
                    elif "enabled" not in merged:
                        merged["enabled"] = True

                source["record"] = merged
                try:
                    sid_log = sid
                    sname_log = sname
                    self.logger.info(
                        "Record config for source id=%s name=%s: enabled=%s continuous=%s out_dir=%s container=%s",
                        sid_log,
                        sname_log,
                        merged.get("enabled"),
                        merged.get("continuous_recording_enabled"),
                        merged.get("out_dir"),
                        merged.get("container"),
                    )
                    needs_out_dir = bool(merged.get("enabled")) and (
                        bool(merged.get("continuous_recording_enabled"))
                        or bool(merged.get("event_recording_enabled"))
                    )
                    if needs_out_dir:
                        from evileye.video_recorder.recording_params import RecordingParams

                        rp = RecordingParams.from_config({"record": merged})
                        ok, reason = rp.check_out_dir_writable()
                        if not ok:
                            merged["enabled"] = False
                            merged["continuous_recording_enabled"] = False
                            merged["event_recording_enabled"] = False
                            source["record"] = merged
                            self.logger.warning(
                                "Recording disabled for source id=%s name=%s: "
                                "out_dir not writable: %s (%s)",
                                sid_log,
                                sname_log,
                                merged.get("out_dir"),
                                reason,
                            )
                except Exception:
                    pass
        except Exception as e:
            self.logger.warning("Failed to propagate record config: %s", e)
