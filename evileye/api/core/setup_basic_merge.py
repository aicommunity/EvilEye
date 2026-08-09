"""Non-destructive merge of Basic setup projection into EvilEye JSON configs."""

from __future__ import annotations

import copy
from typing import Any, Optional


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

    sources_out: list[dict[str, Any]] = []
    for idx, raw in enumerate(_as_list(pipeline.get("sources"))):
        row = _as_dict(raw)
        sid = 0
        ids = row.get("source_ids")
        if isinstance(ids, list) and ids:
            try:
                sid = int(ids[0])
            except Exception:
                sid = idx
        else:
            sid = idx
        names = row.get("source_names")
        name = (
            str(names[0])
            if isinstance(names, list) and names
            else str(row.get("source_name") or row.get("name") or f"Cam{sid + 1}")
        )
        src_type = str(row.get("source") or row.get("type") or "IpCamera")
        address = str(row.get("camera") or row.get("uri") or row.get("address") or "")
        cred = _as_dict(source_creds.get(address))
        enabled_sources = record.get("enabled_sources")
        rec_flag = True
        if isinstance(enabled_sources, dict):
            rec_flag = bool(enabled_sources.get(str(sid), enabled_sources.get(sid, True)))
        elif isinstance(enabled_sources, list):
            rec_flag = sid in enabled_sources or str(sid) in enabled_sources
        sources_out.append(
            {
                "id": sid,
                "name": name,
                "type": SOURCE_TYPE_MAP.get(src_type, src_type),
                "address": address,
                "username": str(cred.get("username") or ""),
                "password_set": bool(cred.get("password") or cred.get("password_hash")),
                "record": rec_flag,
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
        # Prefer OR of per-camera flags so Basic UI matches enabled_sources.
        "recording_enabled": (
            any(bool(s.get("record")) for s in sources_out)
            if sources_out
            else bool(record.get("enabled", False))
        ),
    }


def _default_detector(source_id: int) -> dict[str, Any]:
    return {"source_ids": [source_id]}


def _default_tracker(source_id: int) -> dict[str, Any]:
    return {"source_ids": [source_id]}


def _build_source_row(basic_src: dict[str, Any], existing: Optional[dict[str, Any]], index: int) -> dict[str, Any]:
    row = copy.deepcopy(existing) if isinstance(existing, dict) else {}
    sid = int(basic_src.get("id", index))
    name = str(basic_src.get("name") or f"Cam{sid + 1}")
    src_type = SOURCE_TYPE_MAP.get(str(basic_src.get("type") or "IpCamera"), "IpCamera")
    address = basic_src.get("address")
    if address is None or address == "":
        address = 0 if src_type == "Device" else ""
    row["source"] = src_type
    row["camera"] = address
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

    Returns (new_config, new_credentials). Does not wipe unmanaged sections.
    """
    config = copy.deepcopy(existing_config) if isinstance(existing_config, dict) else {}
    creds = copy.deepcopy(credentials) if isinstance(credentials, dict) else {}

    pipeline = _as_dict(config.get("pipeline"))
    controller = _as_dict(config.get("controller"))
    database = _as_dict(config.get("database"))
    record = _as_dict(config.get("record"))
    storage_monitor = _as_dict(config.get("storage_monitor"))

    old_image_dir = str(database.get("image_dir") or "")
    data_dir = str(basic.get("data_dir") or "").strip()
    if data_dir:
        database["image_dir"] = data_dir
        # Sync out_dir / storage path only when unset or previously tied to image_dir
        out_dir = record.get("out_dir")
        if not out_dir or str(out_dir) == old_image_dir:
            record["out_dir"] = data_dir
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
        # Strip secrets from config database section
        for secret_key in ("password", "admin_password"):
            database.pop(secret_key, None)
        creds["database"] = db_creds
    database.setdefault("preview_width", 300)
    database.setdefault("preview_height", 150)

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
            # try match by id alone
            for cand in existing_sources:
                ids = cand.get("source_ids")
                if isinstance(ids, list) and ids and int(ids[0]) == sid:
                    existing = cand
                    break
        row = _build_source_row(basic_src, existing, idx)
        new_sources.append(row)
        enabled_sources[str(sid)] = bool(basic_src.get("record", True))
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

    # Drop credentials for removed URIs that we previously tracked in sources list
    for uri in list(source_creds.keys()):
        if uri.startswith("rtsp://") or uri.startswith("http"):
            # Keep if still referenced
            if uri not in kept_uris:
                # only remove if it was among previous source cameras
                prev_cameras = {str(s.get("camera") or "") for s in existing_sources}
                if uri in prev_cameras:
                    source_creds.pop(uri, None)
    creds["sources"] = source_creds
    pipeline["sources"] = new_sources

    analytics_enabled = bool(basic.get("analytics_enabled", False))
    if analytics_enabled:
        detectors = _as_list(pipeline.get("detectors"))
        trackers = _as_list(pipeline.get("trackers"))
        if not detectors:
            pipeline["detectors"] = [_default_detector(int((_as_dict(s).get("source_ids") or [i])[0])) for i, s in enumerate(new_sources)]
        else:
            # Ensure coverage for current source ids without wiping model params
            covered: set[int] = set()
            for det in detectors:
                ids = _as_dict(det).get("source_ids") or []
                for x in ids:
                    try:
                        covered.add(int(x))
                    except Exception:
                        pass
            for s in new_sources:
                ids = s.get("source_ids") or []
                if ids and int(ids[0]) not in covered:
                    detectors.append(_default_detector(int(ids[0])))
            pipeline["detectors"] = detectors
        if not trackers:
            pipeline["trackers"] = [_default_tracker(int((_as_dict(s).get("source_ids") or [i])[0])) for i, s in enumerate(new_sources)]
        else:
            covered_t: set[int] = set()
            for tr in trackers:
                ids = _as_dict(tr).get("source_ids") or []
                for x in ids:
                    try:
                        covered_t.add(int(x))
                    except Exception:
                        pass
            for s in new_sources:
                ids = s.get("source_ids") or []
                if ids and int(ids[0]) not in covered_t:
                    trackers.append(_default_tracker(int(ids[0])))
            pipeline["trackers"] = trackers
        if "mc_trackers" not in pipeline:
            pipeline["mc_trackers"] = [
                {"source_ids": [int((s.get("source_ids") or [0])[0]) for s in new_sources], "enable": False}
            ]
    else:
        pipeline["detectors"] = []
        pipeline["trackers"] = []
        # leave mc_trackers / events alone

    # Master switch follows any per-camera record flag (Basic UI has no global checkbox).
    if enabled_sources:
        recording_enabled = any(bool(v) for v in enabled_sources.values())
    else:
        recording_enabled = bool(basic.get("recording_enabled", False))
    record["enabled"] = recording_enabled
    if recording_enabled:
        record.setdefault("continuous_recording_enabled", True)
    if enabled_sources:
        prev = record.get("enabled_sources")
        if isinstance(prev, dict):
            merged_es = dict(prev)
            merged_es.update(enabled_sources)
            # Drop ids no longer present in the sources list
            keep_ids = set(enabled_sources.keys())
            record["enabled_sources"] = {k: bool(v) for k, v in merged_es.items() if str(k) in keep_ids}
        else:
            record["enabled_sources"] = enabled_sources

    config["pipeline"] = pipeline
    config["controller"] = controller
    config["database"] = database
    config["record"] = record
    if storage_monitor:
        config["storage_monitor"] = storage_monitor

    # Ensure common empty sections exist for brand-new configs only
    config.setdefault("objects_handler", config.get("objects_handler", {}))
    config.setdefault("events_detectors", config.get("events_detectors", {}))
    config.setdefault("events_processor", config.get("events_processor", {}))
    config.setdefault("visualizer", config.get("visualizer") or {"num_width": 1, "num_height": 1})

    return config, creds
