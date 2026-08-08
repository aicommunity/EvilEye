"""Pure-Python config validation (no Qt dependency). Ported from Configurer validators."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

KNOWN_SECTIONS = (
    "sources",
    "detectors",
    "trackers",
    "events_detectors",
    "objects_handler",
    "database",
    "visualizer",
    "pipeline",
    "server",
)

_URL_RE = re.compile(
    r"^(https?|rtsp|rtsps|file)://.+$",
    re.IGNORECASE,
)
_HTTP_RE = re.compile(
    r"^https?://"
    r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|"
    r"localhost|"
    r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"
    r"(?::\d+)?"
    r"(?:/?|[/?]\S+)$",
    re.IGNORECASE,
)


class ValidationResult:
    def __init__(self, is_valid: bool, error_message: str = "", warning_message: str = ""):
        self.is_valid = is_valid
        self.error_message = error_message
        self.warning_message = warning_message

    def __bool__(self) -> bool:
        return self.is_valid


class PathValidator:
    def __init__(self, field_name: str = "", must_exist: bool = False, file_types: list[str] | None = None):
        self.field_name = field_name
        self.must_exist = must_exist
        self.file_types = file_types or []

    def validate(self, value: Any) -> ValidationResult:
        if not value or not isinstance(value, str):
            return ValidationResult(False, f"{self.field_name}: path must be a non-empty string")
        path = Path(value)
        if self.must_exist and not path.exists():
            return ValidationResult(False, f"{self.field_name}: path does not exist: {value}")
        if self.file_types and path.suffix and not any(str(path).lower().endswith(ext.lower()) for ext in self.file_types):
            return ValidationResult(
                False,
                f"{self.field_name}: unsupported file type, expected {', '.join(self.file_types)}",
            )
        return ValidationResult(True)


class NumericValidator:
    def __init__(
        self,
        field_name: str = "",
        min_value: float | None = None,
        max_value: float | None = None,
        integer: bool = False,
    ):
        self.field_name = field_name
        self.min_value = min_value
        self.max_value = max_value
        self.integer = integer

    def validate(self, value: Any) -> ValidationResult:
        try:
            num = int(value) if self.integer else float(value)
        except (TypeError, ValueError):
            return ValidationResult(False, f"{self.field_name}: must be {'int' if self.integer else 'number'}")
        if self.min_value is not None and num < self.min_value:
            return ValidationResult(False, f"{self.field_name}: must be >= {self.min_value}")
        if self.max_value is not None and num > self.max_value:
            return ValidationResult(False, f"{self.field_name}: must be <= {self.max_value}")
        return ValidationResult(True)


class NetworkValidator:
    def __init__(self, field_name: str = "", allow_rtsp: bool = True):
        self.field_name = field_name
        self.allow_rtsp = allow_rtsp

    def validate(self, value: Any) -> ValidationResult:
        if not value or not isinstance(value, str):
            return ValidationResult(False, f"{self.field_name}: URL must be a non-empty string")
        if self.allow_rtsp and _URL_RE.match(value):
            return ValidationResult(True)
        if _HTTP_RE.match(value):
            return ValidationResult(True)
        # Local file path fallback
        if Path(value).suffix:
            return ValidationResult(True, warning_message=f"{self.field_name}: treated as local path")
        return ValidationResult(False, f"{self.field_name}: invalid URL format")


class ConfigValidator:
    """Compose field validators for a nested dict (Qt ConfigValidator parity without Qt)."""

    def __init__(self, field_name: str = ""):
        self.field_name = field_name
        self.validators: dict[str, Any] = {}

    def add_validator(self, key: str, validator: Any) -> None:
        self.validators[key] = validator

    def validate(self, value: Any) -> ValidationResult:
        if not isinstance(value, dict):
            return ValidationResult(False, f"{self.field_name}: configuration must be an object")
        errors: list[str] = []
        for key, validator in self.validators.items():
            if key not in value:
                continue
            result = validator.validate(value[key])
            if not result:
                errors.append(result.error_message)
        if errors:
            return ValidationResult(False, "; ".join(errors))
        return ValidationResult(True)


def _as_list(section: Any) -> list[Any]:
    if section is None:
        return []
    if isinstance(section, list):
        return section
    if isinstance(section, dict):
        if "items" in section and isinstance(section["items"], list):
            return section["items"]
        return [section]
    return []


def validate_config(body: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(body, dict):
        return {"ok": False, "errors": ["Config root must be an object"], "warnings": []}

    sources = body.get("sources")
    if sources is None:
        warnings.append("Missing sources section")
    elif not isinstance(sources, (list, dict)):
        errors.append("sources must be list or object")
    else:
        net = NetworkValidator("uri", allow_rtsp=True)
        for i, src in enumerate(_as_list(sources)):
            if not isinstance(src, dict):
                errors.append(f"sources[{i}] must be object")
                continue
            uri = src.get("uri") or src.get("url") or src.get("source")
            if uri is not None and isinstance(uri, str) and uri:
                result = net.validate(uri)
                if not result:
                    errors.append(f"sources[{i}]: {result.error_message}")
                elif result.warning_message:
                    warnings.append(f"sources[{i}]: {result.warning_message}")
            fps = src.get("fps")
            if fps is not None:
                result = NumericValidator(f"sources[{i}].fps", min_value=0, max_value=240).validate(fps)
                if not result:
                    errors.append(result.error_message)
            sid = src.get("source_id")
            if sid is not None:
                result = NumericValidator(f"sources[{i}].source_id", min_value=0, integer=True).validate(sid)
                if not result:
                    errors.append(result.error_message)

    detectors = body.get("detectors")
    if detectors is not None and not isinstance(detectors, list):
        errors.append("detectors must be a list")
    if isinstance(detectors, list):
        model_path = PathValidator("model", must_exist=False, file_types=[".pt", ".onnx", ".engine", ".xml"])
        for i, det in enumerate(detectors):
            if not isinstance(det, dict):
                errors.append(f"detectors[{i}] must be object")
                continue
            if "model" not in det:
                warnings.append(f"detectors[{i}] missing model")
            else:
                model = det.get("model")
                if isinstance(model, str) and model:
                    result = model_path.validate(model)
                    if not result:
                        # treat as warning when file may be relative/runtime-resolved
                        warnings.append(result.error_message)
            conf = det.get("conf", det.get("confidence"))
            if conf is not None:
                result = NumericValidator(f"detectors[{i}].conf", min_value=0.0, max_value=1.0).validate(conf)
                if not result:
                    errors.append(result.error_message)
            roi = det.get("roi")
            if roi is not None and not isinstance(roi, list):
                errors.append(f"detectors[{i}].roi must be a list")
            sids = det.get("source_ids")
            if sids is not None and not isinstance(sids, list):
                errors.append(f"detectors[{i}].source_ids must be a list")

    trackers = body.get("trackers")
    if trackers is not None and not isinstance(trackers, (list, dict)):
        errors.append("trackers must be list or object")
    elif isinstance(trackers, list):
        for i, tr in enumerate(trackers):
            if not isinstance(tr, dict):
                errors.append(f"trackers[{i}] must be object")
                continue
            max_age = tr.get("max_age")
            if max_age is not None:
                result = NumericValidator(f"trackers[{i}].max_age", min_value=1, integer=True).validate(max_age)
                if not result:
                    errors.append(result.error_message)

    events = body.get("events_detectors") or body.get("events")
    if events is not None and not isinstance(events, (list, dict)):
        errors.append("events_detectors must be list or object")
    elif isinstance(events, list):
        for i, ev in enumerate(events):
            if not isinstance(ev, dict):
                errors.append(f"events_detectors[{i}] must be object")
                continue
            zones = ev.get("zones")
            if zones is not None and not isinstance(zones, list):
                errors.append(f"events_detectors[{i}].zones must be a list")

    database = body.get("database")
    if database is not None:
        if not isinstance(database, dict):
            errors.append("database must be an object")
        else:
            port = database.get("port")
            if port is not None:
                result = NumericValidator("database.port", min_value=1, max_value=65535, integer=True).validate(port)
                if not result:
                    errors.append(result.error_message)
            host = database.get("host")
            if host is not None and not isinstance(host, str):
                errors.append("database.host must be string")

    visualizer = body.get("visualizer")
    if visualizer is not None and not isinstance(visualizer, dict):
        errors.append("visualizer must be an object")
    elif isinstance(visualizer, dict):
        fps = visualizer.get("fps") or visualizer.get("display_fps")
        if fps is not None:
            result = NumericValidator("visualizer.fps", min_value=0, max_value=120).validate(fps)
            if not result:
                errors.append(result.error_message)

    handler = body.get("objects_handler")
    if handler is not None and not isinstance(handler, (dict, list)):
        errors.append("objects_handler must be object or list")

    return {"ok": len(errors) == 0, "errors": errors, "warnings": warnings}


def list_sections(body: dict[str, Any]) -> list[str]:
    found = [k for k in KNOWN_SECTIONS if k in body]
    for key in body.keys():
        if key not in found and isinstance(body.get(key), (dict, list)):
            found.append(key)
    return found


# Studio tabs: preferred path first, then fallbacks for legacy flat configs.
STUDIO_TAB_SPECS: list[tuple[str, list[str]]] = [
    ("sources", ["pipeline.sources", "sources"]),
    ("record", ["record"]),
    ("preprocess", ["pipeline.preprocess", "preprocess"]),
    ("detectors", ["pipeline.detectors", "detectors"]),
    ("trackers", ["pipeline.trackers", "trackers"]),
    ("mc_trackers", ["pipeline.mc_trackers", "mc_trackers"]),
    ("events_detectors", ["events_detectors", "events"]),
    ("events_processor", ["events_processor"]),
    ("objects_handler", ["objects_handler"]),
    ("visualizer", ["visualizer"]),
    ("controller", ["controller"]),
    ("server", ["server"]),
    ("database", ["database"]),
    ("database_adapters", ["database_adapters"]),
    ("storage_monitor", ["storage_monitor"]),
]


def split_path(path: str) -> list[str]:
    if not path or not isinstance(path, str):
        raise ValueError("path must be a non-empty string")
    if ".." in path or "/" in path or "\\" in path:
        raise ValueError(f"invalid path: {path}")
    parts = path.split(".")
    if not parts or any(not p for p in parts):
        raise ValueError(f"invalid path: {path}")
    for part in parts:
        if not all(c.isalnum() or c == "_" for c in part):
            raise ValueError(f"invalid path segment: {part}")
    return parts


def get_by_path(body: dict[str, Any], path: str) -> Any:
    cur: Any = body
    for part in split_path(path):
        if not isinstance(cur, dict) or part not in cur:
            raise KeyError(path)
        cur = cur[part]
    return cur


def path_exists(body: dict[str, Any], path: str) -> bool:
    try:
        get_by_path(body, path)
        return True
    except (KeyError, ValueError):
        return False


def set_by_path(body: dict[str, Any], path: str, value: Any) -> None:
    parts = split_path(path)
    cur: Any = body
    for part in parts[:-1]:
        nxt = cur.get(part) if isinstance(cur, dict) else None
        if not isinstance(nxt, dict):
            nxt = {}
            if not isinstance(cur, dict):
                raise ValueError(f"cannot set path under non-object: {path}")
            cur[part] = nxt
        cur = nxt
    if not isinstance(cur, dict):
        raise ValueError(f"cannot set path under non-object: {path}")
    cur[parts[-1]] = value


def resolve_section_path(body: dict[str, Any], candidates: list[str]) -> str | None:
    for candidate in candidates:
        if path_exists(body, candidate):
            return candidate
    return None


def list_studio_tabs(body: dict[str, Any]) -> list[dict[str, str]]:
    """Ordered studio tabs that exist in the config body."""
    tabs: list[dict[str, str]] = []
    claimed_top: set[str] = set()
    claimed_paths: set[str] = set()
    for tab_id, candidates in STUDIO_TAB_SPECS:
        resolved = resolve_section_path(body, candidates)
        if resolved is None:
            continue
        tabs.append({"id": tab_id, "path": resolved, "label_key": f"studio.tab.{tab_id}"})
        claimed_paths.add(resolved)
        claimed_top.add(resolved.split(".", 1)[0])
        claimed_top.add(tab_id)

    for key, value in body.items():
        if key in claimed_top or key in claimed_paths:
            continue
        if not isinstance(value, (dict, list)):
            continue
        # Skip opaque pipeline bag once children are exposed as tabs
        if key == "pipeline":
            continue
        tabs.append({"id": key, "path": key, "label_key": f"studio.tab.{key}"})
    return tabs
