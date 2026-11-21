"""Shared pipeline configuration validation and safe persistence."""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

BACKUP_LIMIT = 10
_SENSITIVE_KEYS = {
    "password",
    "passwd",
    "secret",
    "admin_password",
    "token",
    "access_token",
    "auth_token",
    "client_secret",
    "credential",
    "credentials",
    "username",
    "api_key",
    "private_key",
}
_URI_CREDENTIALS = re.compile(r"(?i)^([a-z][a-z0-9+.-]*://)([^/@]+)@")

SURVEILLANCE_GROUPS = {
    "sources": ("Источники", "source", "VideoCaptureOpencv"),
    "preprocessors": ("Предобработка", "processor_item", "PreprocessingPipeline"),
    "detectors": ("Детекторы объектов", "processor_item", "ObjectDetectorYolo"),
    "trackers": ("Трекеры", "processor_item", "ObjectTrackingBotsort"),
    "mc_trackers": ("Межкамерные трекеры", "batch_processor", "ObjectMultiCameraTracking"),
    "attributes_roi": ("Подготовка ROI", "processor_item", "RoiFeeder"),
    "attributes_classifier": ("Классификаторы атрибутов", "processor_item", "AttributeClassifier"),
    "events_detectors": ("Детекторы событий и тревог", "event_detector", None),
}


def schema_mapping(schema: Any) -> dict[str, Any] | None:
    if isinstance(schema, Mapping):
        return expand_json_schema(schema)
    getter = getattr(schema, "model_json_schema", None)
    if callable(getter):
        return expand_json_schema(getter())
    getter = getattr(schema, "schema", None)
    if callable(getter):
        return expand_json_schema(getter())
    return None


def expand_json_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    root = dict(schema)

    def expand(value: Any, seen: set[str] | None = None) -> Any:
        if not isinstance(value, Mapping):
            return value
        current = dict(value)
        ref = current.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/"):
            target: Any = root
            for part in ref[2:].split("/"):
                target = target.get(part) if isinstance(target, Mapping) else None
            seen = set(seen or ())
            if ref in seen or not isinstance(target, Mapping):
                return {"type": "object", "additionalProperties": True}
            seen.add(ref)
            merged = dict(expand(target, seen))
            merged.update({key: item for key, item in current.items() if key != "$ref"})
            current = merged
        choices = current.get("anyOf") or current.get("oneOf") or current.get("allOf")
        if isinstance(choices, list):
            expanded = [expand(item, seen) for item in choices]
            if current.get("allOf") is not None:
                merged: dict[str, Any] = {}
                for item in expanded:
                    if isinstance(item, Mapping):
                        merged.update(item)
                current = {**merged, **{key: item for key, item in current.items() if key != "allOf"}}
            else:
                non_null = [item for item in expanded if isinstance(item, Mapping) and item.get("type") != "null"]
                if len(non_null) == 1:
                    current = {**non_null[0], **{key: item for key, item in current.items() if key not in {"anyOf", "oneOf"}}}
        if current.get("type") == "array" and isinstance(current.get("items"), Mapping):
            current["items"] = expand(current["items"], seen)
        if isinstance(current.get("properties"), Mapping):
            current["properties"] = {key: expand(child, seen) for key, child in current["properties"].items()}
        return current

    return expand(root)


def pipeline_and_root(config: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    nested = config.get("pipeline")
    return (nested, config) if isinstance(nested, dict) else (config, config)


def builtin_pipeline_kind(pipeline_id: str) -> str | None:
    from evileye.core.plugins import plugin_registry

    registered = plugin_registry.get_pipeline(pipeline_id)
    if registered is not None and registered.plugin_id == "evileye":
        return registered.spec.pipeline_id
    return None


def group_storage(pipeline: dict[str, Any], group: str) -> tuple[list[Any], int, str | None]:
    original = pipeline.get(group) if isinstance(pipeline.get(group), list) else []
    modules = pipeline.get("modules") if isinstance(pipeline.get("modules"), dict) else {}
    extension = modules.get(group) if isinstance(modules.get(group), dict) else None
    if not extension:
        return list(original), len(original), None
    added = extension.get("items") if isinstance(extension.get("items"), list) else []
    mode = str(extension.get("mode") or "extend").lower()
    if mode == "replace":
        return list(added), 0, "replace"
    return [*original, *added], len(original), "extend"


def known_module_id(item: Any, fallback: str) -> str:
    if isinstance(item, Mapping):
        return str(item.get("module_id") or item.get("type") or fallback)
    return fallback


def validate_configuration(config: dict[str, Any]) -> list[str]:
    """Validate config against the plugin registry without constructing runtime objects."""
    from evileye.core.builtin_inventory import register_builtins
    from evileye.core.builtin_module_schemas import COMMON
    from evileye.core.plugins import (
        MODULE_RUNTIME_FIELDS,
        PluginError,
        _validate_json_schema,
        plugin_registry,
    )

    register_builtins()
    pipeline, root = pipeline_and_root(config)
    pipeline_id = str(pipeline.get("pipeline_class") or "PipelineSurveillance")
    builtin_kind = builtin_pipeline_kind(pipeline_id)
    diagnostics: list[str] = []
    try:
        plugin_registry.validate_pipeline_config(pipeline_id, pipeline)
    except Exception as exc:
        diagnostics.append(str(exc))

    def validate_item(module_id: str, item: Any, location: str) -> None:
        if not isinstance(item, Mapping):
            diagnostics.append(f"{location} must be an object")
            return
        registered = plugin_registry.get_module(module_id)
        if registered is None:
            diagnostics.append(f"{location}: unknown module '{module_id}' (preserved for manual configuration)")
            return
        try:
            mode = item.get("execution_mode")
            if mode is not None and mode not in registered.spec.execution_modes:
                raise PluginError(
                    f"Invalid configuration for module '{registered.qualified_id}': execution_mode must be one of {', '.join(registered.spec.execution_modes)}"
                )
            controls = {key: value for key, value in item.items() if key in MODULE_RUNTIME_FIELDS and key in COMMON}
            _validate_json_schema(controls, {"type": "object", "properties": COMMON})
            payload = item.get("config")
            if payload is None:
                payload = {key: value for key, value in item.items() if key not in MODULE_RUNTIME_FIELDS}
            plugin_registry.validate_module_config(registered.qualified_id, payload)
        except (PluginError, ValueError) as exc:
            diagnostics.append(str(exc))

    if builtin_kind == "PipelineDeclarative":
        stages = pipeline.get("stages")
        if not stages:
            from evileye.core.pipeline_topology import declarative_stage_configs
            stages = declarative_stage_configs(pipeline)
        if isinstance(stages, list):
            names: set[str] = set()
            for stage_index, stage in enumerate(stages):
                if not isinstance(stage, Mapping):
                    diagnostics.append(f"pipeline.stages[{stage_index}] must be an object")
                    continue
                name = str(stage.get("name") or f"stage_{stage_index}")
                if name in names:
                    diagnostics.append(f"Duplicate pipeline stage name '{name}'")
                names.add(name)
                fallback = {"source": "VideoCaptureOpencv", "frame": "PreprocessingPipeline", "step": "ObjectDetectorYolo"}.get(str(stage.get("kind") or "step"), "ObjectDetectorYolo")
                items = stage.get("items")
                if isinstance(items, list):
                    for index, item in enumerate(items):
                        validate_item(known_module_id(item, fallback), item, f"pipeline.stages[{stage_index}].items[{index}]")
            if pipeline.get("final_results") and pipeline["final_results"] not in names:
                diagnostics.append(f"pipeline.final_results references an unknown stage '{pipeline['final_results']}'")

    groups = list(SURVEILLANCE_GROUPS) if builtin_kind == "PipelineSurveillance" else ["sources", "events_detectors"] if builtin_kind == "PipelineCapture" else ["events_detectors"]
    if builtin_kind == "PipelineSurveillance":
        extensions = pipeline.get("modules")
        if isinstance(extensions, Mapping):
            for group, extension in extensions.items():
                if group not in SURVEILLANCE_GROUPS or group == "events_detectors":
                    diagnostics.append(f"Unsupported pipeline.modules group '{group}'")
                    continue
                if not isinstance(extension, Mapping):
                    diagnostics.append(f"pipeline.modules.{group} must be an object")
                    continue
                if extension.get("mode") not in {"replace", "extend"}:
                    diagnostics.append(f"pipeline.modules.{group}.mode must be 'replace' or 'extend'")
                if not isinstance(extension.get("items", []), list):
                    diagnostics.append(f"pipeline.modules.{group}.items must be an array")
    for group in groups:
        if group == "events_detectors":
            items = root.get(group)
            if items is not None and not isinstance(items, Mapping):
                diagnostics.append("events_detectors must be an object")
            items = items if isinstance(items, Mapping) else {}
            enabled = items.get("enabled")
            if "enabled" in items and (not isinstance(enabled, list) or any(not isinstance(name, str) or not name.strip() for name in enabled)):
                diagnostics.append("events_detectors.enabled must be an array of non-empty module ids")
            elif isinstance(enabled, list):
                for name in enabled:
                    module_config = items.get(name, {})
                    registered = plugin_registry.get_module(known_module_id(module_config, name))
                    if registered is None or registered.spec.kind != "event_detector":
                        diagnostics.append(f"events_detectors.enabled: unknown event detector '{name}'")
            for alias, item in items.items():
                if alias != "enabled":
                    validate_item(known_module_id(item, str(alias)), item, f"events_detectors.{alias}")
        else:
            items, _count, _mode = group_storage(pipeline, group)
            for index, item in enumerate(items):
                validate_item(known_module_id(item, SURVEILLANCE_GROUPS[group][2] or ""), item, f"{group}[{index}]")
    return diagnostics


def write_config_with_backup(
    path: Path,
    content: str,
    *,
    backup_limit: int = BACKUP_LIMIT,
    create_only: bool = False,
) -> Path | None:
    """Atomically replace a config, saving and rotating its prior contents."""
    path = Path(path)
    if create_only and path.exists():
        raise FileExistsError(f"Config already exists: {path.name}")
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    if create_only:
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.link(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
        return None
    backup_path = None
    if path.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        backup_path = path.with_name(f"{path.name}.bak.{stamp}")
        backup_fd, backup_tmp = tempfile.mkstemp(prefix=f".{backup_path.name}.", suffix=".tmp", dir=str(path.parent))
        os.close(backup_fd)
        try:
            shutil.copy2(path, backup_tmp)
            os.replace(backup_tmp, backup_path)
        except Exception:
            try:
                os.unlink(backup_tmp)
            except OSError:
                pass
            raise
        backups = sorted(path.parent.glob(f"{path.name}.bak.*"), key=lambda item: (item.stat().st_mtime_ns, item.name), reverse=True)
        for stale in backups[max(0, int(backup_limit)):]:
            stale.unlink()
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if path.exists():
            os.chmod(temp_name, path.stat().st_mode)
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise
    return backup_path


def _is_sensitive_key(key: Any) -> bool:
    normalized = str(key).lower()
    return normalized in _SENSITIVE_KEYS or any(
        marker in normalized for marker in ("password", "passwd", "secret", "token", "credential", "api_key", "private_key")
    )


def _list_item_identity(value: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    identity_keys = (
        "id",
        "module_id",
        "type",
        "name",
        "source_name",
        "source_names",
        "source_id",
        "camera_id",
        "camera_name",
    )
    return tuple(
        (key, json.dumps(value[key], sort_keys=True, ensure_ascii=False))
        for key in identity_keys
        if key in value and isinstance(value[key], (str, int, float, bool, list, tuple))
    )


def _matching_existing_list_item(
    incoming: Mapping[str, Any],
    existing: list[Any],
    used: set[int],
    index: int,
) -> dict[str, Any] | None:
    identity = _list_item_identity(incoming)
    if identity:
        matches = [
            candidate_index
            for candidate_index, candidate in enumerate(existing)
            if candidate_index not in used
            and isinstance(candidate, Mapping)
            and _list_item_identity(candidate) == identity
        ]
        if len(matches) == 1:
            used.add(matches[0])
            return dict(existing[matches[0]])
    if index < len(existing) and index not in used and isinstance(existing[index], dict):
        used.add(index)
        return existing[index]
    return None


def mask_config_secrets(value: Any, *, key: str = "") -> Any:
    """Hide credential fields and URI user info before config reaches a UI."""
    if isinstance(value, dict):
        return {name: mask_config_secrets(item, key=name) for name, item in value.items()}
    if isinstance(value, list):
        return [mask_config_secrets(item) for item in value]
    if _is_sensitive_key(key) and value not in (None, ""):
        return "***"
    if isinstance(value, str):
        return _URI_CREDENTIALS.sub(
            lambda match: f"{match.group(1)}***:***@" if ":" in match.group(2) else f"{match.group(1)}***@",
            value,
        )
    return value


def merge_preserving_secrets(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """Retain existing credentials when a UI sends masked values back."""
    result = dict(incoming)
    for key, value in incoming.items():
        if _is_sensitive_key(key):
            if value in (None, "", "***") and key in existing:
                result[key] = existing[key]
        elif isinstance(value, str) and "***@" in value and key in existing and isinstance(existing[key], str):
            if _URI_CREDENTIALS.sub("", value) == _URI_CREDENTIALS.sub("", existing[key]):
                result[key] = existing[key]
        elif isinstance(value, dict) and isinstance(existing.get(key), dict):
            result[key] = merge_preserving_secrets(existing[key], value)
        elif isinstance(value, list) and isinstance(existing.get(key), list):
            used: set[int] = set()
            merged_items = []
            for index, item in enumerate(value):
                if isinstance(item, dict):
                    prior = _matching_existing_list_item(item, existing[key], used, index)
                    merged_items.append(merge_preserving_secrets(prior, item) if prior is not None else item)
                else:
                    merged_items.append(item)
            result[key] = merged_items
    return result


def save_config_document(name: str, config: dict[str, Any], *, root: Path, create_only: bool = False) -> dict[str, Any]:
    """Validate then atomically save a named config under the site's configs directory."""
    import re

    from evileye.core.paths import configs_dir, site_root

    site = site_root(root).resolve()
    normalized = str(name or "").strip()
    if not normalized.endswith(".json"):
        normalized += ".json"
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*\.json", normalized) or ".." in normalized:
        raise ValueError("Config name must be a simple JSON filename")
    directory = configs_dir(site).resolve()
    try:
        directory.relative_to(site)
    except ValueError as exc:
        raise ValueError("Config directory may not point outside the site root") from exc
    if directory == site:
        raise ValueError("Config directory may not resolve to the site root")
    path = (directory / normalized).resolve()
    try:
        path.relative_to(directory)
    except ValueError as exc:
        raise ValueError("Config path escapes the site's configs directory") from exc
    if not isinstance(config, dict):
        raise ValueError("Config root must be an object")
    if path.exists() and not create_only:
        try:
            previous = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Existing config cannot be read: {exc}") from exc
        if isinstance(previous, dict):
            config = merge_preserving_secrets(previous, config)
    diagnostics = validate_configuration(config)
    errors = [item for item in diagnostics if "(preserved for manual configuration)" not in item]
    if errors:
        raise ValueError("; ".join(errors))
    existed = path.exists()
    if create_only and existed:
        raise FileExistsError(f"Config already exists: {normalized}")
    content = json.dumps(config, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    backup = write_config_with_backup(path, content, create_only=create_only)
    return {"name": normalized, "status": "updated" if existed else "created", "backup": str(backup) if backup else None}
