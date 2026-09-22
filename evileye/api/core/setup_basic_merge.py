"""Non-destructive merge of Basic setup projection into EvilEye JSON configs."""

from __future__ import annotations

import copy
from typing import Any, Optional

from evileye.events_detectors.schedule_alarm_logic import (
    DETECTOR_CONFIG_KEY,
    SourceSchedule,
    parse_detector_params,
    resolve_detector_section,
    schedule_to_json,
    normalize_schedule_dict,
)


SOURCE_TYPE_MAP = {
    "IpCamera": "IpCamera",
    "ip_camera": "IpCamera",
    "VideoFile": "VideoFile",
    "video_file": "VideoFile",
    "Device": "Device",
    "device": "Device",
}


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def resolve_usable_data_dir(config: dict[str, Any]) -> str:
    """Best-effort data directory from image_dir, record.out_dir, or source out_dir."""
    database = _as_dict(config.get("database"))
    image_dir = str(database.get("image_dir") or "").strip()
    if image_dir:
        return image_dir
    record = _as_dict(config.get("record"))
    out_dir = str(record.get("out_dir") or "").strip()
    if out_dir:
        return out_dir
    pipeline = _as_dict(config.get("pipeline"))
    for raw in _as_list(pipeline.get("sources")):
        row = _as_dict(raw)
        src_out = str(row.get("out_dir") or "").strip()
        if src_out:
            return src_out
    return ""


def source_recording_flag(
    record: dict[str, Any],
    source_id: int,
    source_name: str | None = None,
) -> bool:
    """
    Whether a source should record, matching controller ConfigService semantics.

    - Master ``record.enabled`` must be true.
    - ``enabled_sources`` as dict: per-id bool flags (missing id → false if dict non-empty).
    - ``enabled_sources`` as non-empty list: allow-list of ids/names.
    - Empty list / missing: all sources follow the master switch.
    """
    if not bool(record.get("enabled", False)):
        return False
    enabled_sources = record.get("enabled_sources")
    if isinstance(enabled_sources, dict):
        if not enabled_sources:
            return True
        if str(source_id) in enabled_sources:
            return bool(enabled_sources[str(source_id)])
        if source_id in enabled_sources:
            return bool(enabled_sources[source_id])
        return False
    if isinstance(enabled_sources, list) and len(enabled_sources) > 0:
        if source_id in enabled_sources or str(source_id) in enabled_sources:
            return True
        if source_name and source_name in enabled_sources:
            return True
        return False
    return True


def _enumerate_logical_cameras(pipeline: dict[str, Any]) -> list[tuple[int, str]]:
    """All logical source_ids after capture split (one entry per detector/tracker camera)."""
    out: list[tuple[int, str]] = []
    for idx, raw in enumerate(_as_list(pipeline.get("sources"))):
        row = _as_dict(raw)
        ids = _row_source_ids(row, idx)
        names = _row_source_names(row, ids)
        for i, sid in enumerate(ids):
            name = names[i] if i < len(names) else f"Cam{sid + 1}"
            out.append((sid, name))
    return out


def _row_source_ids(row: dict[str, Any], fallback_idx: int) -> list[int]:
    ids = row.get("source_ids")
    out: list[int] = []
    if isinstance(ids, list) and ids:
        for x in ids:
            try:
                out.append(int(x))
            except Exception:
                continue
    if not out:
        out = [fallback_idx]
    return out


def _row_source_names(row: dict[str, Any], ids: list[int]) -> list[str]:
    names = row.get("source_names")
    if isinstance(names, list) and names:
        return [str(n) for n in names]
    name = row.get("source_name") or row.get("name")
    if name:
        return [str(name)]
    return [f"Cam{ids[0] + 1}"]


def recording_effectively_enabled(config: dict[str, Any]) -> bool:
    """True if at least one pipeline source would record under current record settings."""
    record = _as_dict(config.get("record"))
    if not bool(record.get("enabled", False)):
        return False
    pipeline = _as_dict(config.get("pipeline"))
    sources = _as_list(pipeline.get("sources"))
    if not sources:
        return True
    for idx, raw in enumerate(sources):
        row = _as_dict(raw)
        ids = _row_source_ids(row, idx)
        names = _row_source_names(row, ids)
        for i, sid in enumerate(ids):
            name = names[i] if i < len(names) else None
            if source_recording_flag(record, sid, name):
                return True
    return False


def config_needs_setup(config: dict[str, Any]) -> bool:
    """True only for empty/scaffold configs (no sources and no usable data path)."""
    pipeline = _as_dict(config.get("pipeline"))
    sources = _as_list(pipeline.get("sources"))
    has_sources = len(sources) > 0
    usable = bool(resolve_usable_data_dir(config))
    return (not usable) and (not has_sources)


def _source_key(row: dict[str, Any]) -> tuple[Any, ...]:
    ids = row.get("source_ids")
    if isinstance(ids, list) and ids:
        return ("id", ids[0])
    names = row.get("source_names")
    if isinstance(names, list) and names:
        return ("name", str(names[0]))
    name = row.get("source_name") or row.get("name")
    if name:
        return ("name", str(name))
    return ("addr", str(row.get("camera") or row.get("address") or ""))


def _schedules_equivalent(a: SourceSchedule, b: SourceSchedule) -> bool:
    return (
        a.enabled == b.enabled
        and a.weekdays == b.weekdays
        and a.periods == b.periods
        and a.class_ids == b.class_ids
    )


def _read_alarm_schedule_from_config(
    config: dict[str, Any],
) -> tuple[dict[str, Any], dict[int, dict[str, Any]], dict[int, bool]]:
    section = resolve_detector_section(config.get("events_detectors") or {})
    cfg = parse_detector_params(section)
    global_sched = schedule_to_json(cfg.default_schedule)
    per_source: dict[int, dict[str, Any]] = {}
    alarm_enabled: dict[int, bool] = {}

    pipeline = _as_dict(config.get("pipeline"))
    source_ids: list[int] = []
    for idx, raw in enumerate(_as_list(pipeline.get("sources"))):
        row = _as_dict(raw)
        source_ids.extend(_row_source_ids(row, idx))

    for sid in source_ids:
        override = cfg.sources.get(sid)
        if override is None:
            alarm_enabled[sid] = bool(cfg.default_schedule.enabled)
            continue
        if not override.enabled:
            alarm_enabled[sid] = False
            continue
        alarm_enabled[sid] = True
        if not _schedules_equivalent(override, cfg.default_schedule):
            per_source[sid] = schedule_to_json(override)

    for sid, override in cfg.sources.items():
        if sid in alarm_enabled:
            continue
        if override.enabled:
            alarm_enabled[sid] = True
            if not _schedules_equivalent(override, cfg.default_schedule):
                per_source[sid] = schedule_to_json(override)
        else:
            alarm_enabled[sid] = False

    return global_sched, per_source, alarm_enabled


def _write_alarm_schedule_to_config(config: dict[str, Any], basic: dict[str, Any]) -> None:
    events = config.setdefault("events_detectors", {})
    if not isinstance(events, dict):
        config["events_detectors"] = {}
        events = config["events_detectors"]
    section = events.setdefault(DETECTOR_CONFIG_KEY, {})
    if not isinstance(section, dict):
        section = {}
        events[DETECTOR_CONFIG_KEY] = section

    global_raw = basic.get("alarm_schedule")
    global_enabled = bool(global_raw.get("enabled")) if isinstance(global_raw, dict) else False

    if isinstance(global_raw, dict):
        section["default_schedule"] = schedule_to_json(
            normalize_schedule_dict(global_raw, default_enabled=global_enabled)
        )
        try:
            section["camera_cooldown_sec"] = max(0, int(global_raw.get("camera_cooldown_sec") or 0))
        except (TypeError, ValueError):
            section["camera_cooldown_sec"] = 0

    sources_map: dict[str, dict[str, Any]] = {}
    cameras = _as_list(basic.get("alarm_cameras"))
    if cameras:
        for cam in cameras:
            if not isinstance(cam, dict):
                continue
            sid = int(cam.get("id", 0))
            custom = cam.get("alarm_schedule")
            if isinstance(custom, dict) and custom:
                sources_map[str(sid)] = schedule_to_json(
                    normalize_schedule_dict(custom, default_enabled=bool(custom.get("enabled", False)))
                )
                continue
            enabled = cam.get("alarm_enabled")
            if enabled is None:
                enabled = global_enabled
            if not bool(enabled):
                sources_map[str(sid)] = {
                    "enabled": False,
                    "weekdays": [],
                    "periods": [],
                    "class_ids": [],
                }
    else:
        for src in _as_list(basic.get("sources")):
            if not isinstance(src, dict):
                continue
            sid = int(src.get("id", 0))
            custom = src.get("alarm_schedule")
            if isinstance(custom, dict) and custom:
                sources_map[str(sid)] = schedule_to_json(
                    normalize_schedule_dict(custom, default_enabled=bool(custom.get("enabled", False)))
                )
                continue
            enabled = src.get("alarm_enabled")
            if enabled is None:
                enabled = global_enabled
            if not bool(enabled):
                sources_map[str(sid)] = {
                    "enabled": False,
                    "weekdays": [],
                    "periods": [],
                    "class_ids": [],
                }
    section["sources"] = sources_map


def project_basic_from_config(
    config: dict[str, Any],
    credentials: dict[str, Any] | None = None,
    *,
    config_name: str = "system.json",
) -> dict[str, Any]:
    creds = credentials if isinstance(credentials, dict) else {}
    pipeline = _as_dict(config.get("pipeline"))
    controller = _as_dict(config.get("controller"))
    database = _as_dict(config.get("database"))
    record = _as_dict(config.get("record"))
    db_creds = _as_dict(creds.get("database"))
    source_creds = _as_dict(creds.get("sources"))

    use_db = bool(controller.get("use_database", False))
    detectors = _as_list(pipeline.get("detectors"))
    trackers = _as_list(pipeline.get("trackers"))
    analytics = bool(detectors or trackers)

    global_sched, per_source, alarm_enabled_map = _read_alarm_schedule_from_config(config)

    alarm_cameras_out: list[dict[str, Any]] = []
    for sid, name in _enumerate_logical_cameras(pipeline):
        alarm_cameras_out.append(
            {
                "id": sid,
                "name": name,
                "alarm_enabled": alarm_enabled_map.get(sid, bool(global_sched.get("enabled"))),
                "alarm_schedule": per_source.get(sid),
            }
        )

    sources_out: list[dict[str, Any]] = []
    for idx, raw in enumerate(_as_list(pipeline.get("sources"))):
        row = _as_dict(raw)
        ids = _row_source_ids(row, idx)
        names = _row_source_names(row, ids)
        sid = ids[0]
        name = names[0]
        extra_names = names[1:] if len(names) > 1 else []
        src_type = str(row.get("source") or row.get("type") or "IpCamera")
        address = str(row.get("camera") or row.get("uri") or row.get("address") or "")
        cred = _as_dict(source_creds.get(address))
        # Card record flag is ON if any logical id in the row would record.
        rec_flag = any(
            source_recording_flag(record, ids[i], names[i] if i < len(names) else None) for i in range(len(ids))
        )
        sources_out.append(
            {
                "id": sid,
                "name": name,
                "extra_names": extra_names,
                "type": SOURCE_TYPE_MAP.get(src_type, src_type),
                "address": address,
                "username": str(cred.get("username") or ""),
                "password_set": bool(cred.get("password") or cred.get("password_hash")),
                "record": rec_flag,
                "logical_ids": ids,
            }
        )

    return {
        "config_name": config_name,
        "data_dir": resolve_usable_data_dir(config),
        "storage_mode": "database" if use_db else "json",
        "database": {
            "host_name": str(database.get("host_name") or db_creds.get("host_name") or "localhost"),
            "port": int(database.get("port") or db_creds.get("port") or 5432),
            "database_name": str(
                database.get("database_name") or db_creds.get("database_name") or "evil_eye_db"
            ),
            "user_name": str(
                database.get("user_name")
                or db_creds.get("user_name")
                or db_creds.get("admin_user_name")
                or "postgres"
            ),
            "password_set": bool(
                db_creds.get("password")
                or db_creds.get("admin_password")
                or database.get("password")
                or database.get("admin_password")
            ),
        },
        "sources": sources_out,
        "analytics_enabled": analytics,
        "recording_enabled": recording_effectively_enabled(config),
        "alarm_schedule": global_sched,
        "alarm_cameras": alarm_cameras_out,
    }


def _default_detector(source_id: int) -> dict[str, Any]:
    return {"source_ids": [source_id]}


def _default_tracker(source_id: int) -> dict[str, Any]:
    return {"source_ids": [source_id]}


def _covered_source_ids(entries: list[Any]) -> set[int]:
    covered: set[int] = set()
    for raw in entries:
        ids = _as_dict(raw).get("source_ids") or []
        for x in ids:
            try:
                covered.add(int(x))
            except Exception:
                pass
    return covered


def _all_logical_ids(sources: list[dict[str, Any]]) -> set[int]:
    out: set[int] = set()
    for idx, s in enumerate(sources):
        for sid in _row_source_ids(s, idx):
            out.add(sid)
    return out


def _build_source_row(basic_src: dict[str, Any], existing: Optional[dict[str, Any]], index: int) -> dict[str, Any]:
    """Merge basic card onto existing source row without wiping unmanaged fields / split ids."""
    row = copy.deepcopy(existing) if isinstance(existing, dict) else {}
    sid = int(basic_src.get("id", index))
    name = str(basic_src.get("name") or f"Cam{sid + 1}")
    src_type = SOURCE_TYPE_MAP.get(str(basic_src.get("type") or "IpCamera"), "IpCamera")
    address = basic_src.get("address")
    if address is None or address == "":
        address = 0 if src_type == "Device" else ""
    row["source"] = src_type
    row["camera"] = address

    existing_ids = row.get("source_ids") if isinstance(row.get("source_ids"), list) else None
    existing_names = row.get("source_names") if isinstance(row.get("source_names"), list) else None
    is_split = bool(row.get("split")) or (isinstance(existing_ids, list) and len(existing_ids) > 1)

    if is_split and isinstance(existing_ids, list) and existing_ids:
        ids = list(existing_ids)
        try:
            ids[0] = sid
        except Exception:
            ids = [sid] + list(existing_ids[1:])
        row["source_ids"] = ids
        if isinstance(existing_names, list) and existing_names:
            names = list(existing_names)
            names[0] = name
            # Keep tail names aligned with ids length
            while len(names) < len(ids):
                names.append(f"Cam{ids[len(names)] + 1}")
            row["source_names"] = names[: len(ids)]
        else:
            row["source_names"] = [name] + [f"Cam{i + 1}" for i in ids[1:]]
    else:
        row["source_ids"] = [sid]
        row["source_names"] = [name]

    row.setdefault("execution_mode", "thread")
    return row


def apply_basic_setup(
    existing_config: dict[str, Any] | None,
    basic: dict[str, Any],
    credentials: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    Merge basic setup into config + credentials.

    Only allowlisted fields are mutated; unmanaged sections/keys are preserved.
    """
    config = copy.deepcopy(existing_config) if isinstance(existing_config, dict) else {}
    creds = copy.deepcopy(credentials) if isinstance(credentials, dict) else {}

    pipeline = _as_dict(config.get("pipeline"))
    controller = _as_dict(config.get("controller"))
    database = _as_dict(config.get("database"))
    record = _as_dict(config.get("record"))
    storage_monitor = _as_dict(config.get("storage_monitor")) if "storage_monitor" in config else {}

    old_image_dir = str(database.get("image_dir") or "")
    data_dir = str(basic.get("data_dir") or "").strip()
    if data_dir:
        database["image_dir"] = data_dir
        out_dir = record.get("out_dir")
        if not out_dir or str(out_dir) == old_image_dir:
            record["out_dir"] = data_dir
        if storage_monitor:
            sm_path = storage_monitor.get("path")
            if not sm_path or str(sm_path) == old_image_dir:
                storage_monitor["path"] = data_dir

    storage_mode = str(basic.get("storage_mode") or "json").lower()
    use_database = storage_mode == "database"
    controller["use_database"] = use_database

    db_basic = _as_dict(basic.get("database"))
    db_creds = _as_dict(creds.get("database"))
    if use_database:
        for key in ("host_name", "database_name", "user_name"):
            if db_basic.get(key) not in (None, ""):
                database[key] = db_basic[key]
                db_creds[key] = db_basic[key]
        if db_basic.get("port") not in (None, ""):
            database["port"] = int(db_basic["port"])
            db_creds["port"] = int(db_basic["port"])
        password = db_basic.get("password")
        if isinstance(password, str) and password:
            db_creds["password"] = password
            db_creds.setdefault("admin_password", password)
            if not db_creds.get("admin_user_name"):
                db_creds["admin_user_name"] = db_creds.get("user_name") or "postgres"
        for secret_key in ("password", "admin_password"):
            database.pop(secret_key, None)
        creds["database"] = db_creds
    if "preview_width" not in database:
        database["preview_width"] = 300
    if "preview_height" not in database:
        database["preview_height"] = 150

    # Do not overwrite an existing pipeline_class.
    if not pipeline.get("pipeline_class"):
        pipeline["pipeline_class"] = "PipelineSurveillance"

    existing_sources = [_as_dict(x) for x in _as_list(pipeline.get("sources"))]
    existing_by_key = {_source_key(s): s for s in existing_sources}

    new_sources: list[dict[str, Any]] = []
    enabled_sources: dict[str, bool] = {}
    source_creds = _as_dict(creds.get("sources"))
    kept_uris: set[str] = set()

    for idx, basic_src in enumerate(_as_list(basic.get("sources"))):
        if not isinstance(basic_src, dict):
            continue
        sid = int(basic_src.get("id", idx))
        probe = {
            "source_ids": [sid],
            "source_names": [basic_src.get("name") or f"Cam{sid + 1}"],
            "camera": basic_src.get("address"),
        }
        existing = existing_by_key.get(_source_key(probe))
        if existing is None:
            for cand in existing_sources:
                ids = cand.get("source_ids")
                if isinstance(ids, list) and ids:
                    try:
                        if int(ids[0]) == sid:
                            existing = cand
                            break
                    except Exception:
                        continue
        row = _build_source_row(basic_src, existing, idx)
        new_sources.append(row)
        rec = bool(basic_src.get("record", True))
        for logical_id in _row_source_ids(row, idx):
            enabled_sources[str(logical_id)] = rec
        address = str(row.get("camera") or "")
        if address.startswith("rtsp://") or address.startswith("http"):
            kept_uris.add(address)
            username = basic_src.get("username")
            password = basic_src.get("password")
            entry = _as_dict(source_creds.get(address))
            if username not in (None, ""):
                entry["username"] = username
            if isinstance(password, str) and password:
                entry["password"] = password
            if entry:
                source_creds[address] = entry

    for uri in list(source_creds.keys()):
        if uri.startswith("rtsp://") or uri.startswith("http"):
            if uri not in kept_uris:
                prev_cameras = {str(s.get("camera") or "") for s in existing_sources}
                if uri in prev_cameras:
                    source_creds.pop(uri, None)
    creds["sources"] = source_creds
    pipeline["sources"] = new_sources

    analytics_enabled = bool(basic.get("analytics_enabled", False))
    if analytics_enabled:
        detectors = [copy.deepcopy(_as_dict(d)) for d in _as_list(pipeline.get("detectors"))]
        trackers = [copy.deepcopy(_as_dict(t)) for t in _as_list(pipeline.get("trackers"))]
        logical_ids = _all_logical_ids(new_sources)
        if not detectors:
            pipeline["detectors"] = [_default_detector(sid) for sid in sorted(logical_ids)]
        else:
            covered = _covered_source_ids(detectors)
            for sid in sorted(logical_ids):
                if sid not in covered:
                    detectors.append(_default_detector(sid))
            pipeline["detectors"] = detectors
        if not trackers:
            pipeline["trackers"] = [_default_tracker(sid) for sid in sorted(logical_ids)]
        else:
            covered_t = _covered_source_ids(trackers)
            for sid in sorted(logical_ids):
                if sid not in covered_t:
                    trackers.append(_default_tracker(sid))
            pipeline["trackers"] = trackers
        # Never create/overwrite mc_trackers if missing — leave Advanced to manage.
    else:
        pipeline["detectors"] = []
        pipeline["trackers"] = []
        # leave mc_trackers / events alone

    if enabled_sources:
        recording_enabled = any(bool(v) for v in enabled_sources.values())
    else:
        recording_enabled = bool(basic.get("recording_enabled", False))
    record["enabled"] = recording_enabled
    if recording_enabled and "continuous_recording_enabled" not in record:
        record["continuous_recording_enabled"] = True
    if enabled_sources:
        # Replace with explicit per-id map for current logical sources only.
        record["enabled_sources"] = {k: bool(v) for k, v in enabled_sources.items()}

    config["pipeline"] = pipeline
    config["controller"] = controller
    config["database"] = database
    config["record"] = record
    if storage_monitor:
        config["storage_monitor"] = storage_monitor

    # Only seed empty sections for brand-new configs; never replace existing ones.
    if "objects_handler" not in config:
        config["objects_handler"] = {}
    if "events_detectors" not in config:
        config["events_detectors"] = {}
    if "events_processor" not in config:
        config["events_processor"] = {}
    if "visualizer" not in config:
        config["visualizer"] = {"num_width": 1, "num_height": 1}

    _write_alarm_schedule_to_config(config, basic)

    return config, creds
