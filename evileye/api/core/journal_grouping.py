from __future__ import annotations

from collections import defaultdict
from typing import Any

from evileye.utils.camera_event_label import (
    format_camera_event_information,
    media_url_without_credentials,
    sanitize_camera_event_record,
    source_names_label,
)


def group_objects_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped_events: dict[Any, dict[str, Any]] = defaultdict(lambda: {"found": None, "lost": None})
    for ev in rows:
        event_type = ev.get("event_type")
        if event_type not in ("found", "lost"):
            continue
        object_id = ev.get("object_id")
        if event_type == "found":
            grouped_events[object_id]["found"] = ev
        else:
            grouped_events[object_id]["lost"] = ev

    table_rows: list[dict[str, Any]] = []
    for _object_id, events in grouped_events.items():
        found_event = events["found"]
        lost_event = events["lost"]
        base_event = found_event or lost_event
        if not base_event:
            continue

        object_id_val = base_event.get("object_id", "") or base_event.get("id", "") or ""
        class_name = (
            base_event.get("class_name")
            or base_event.get("class_id", "")
            or base_event.get("class", "")
            or ""
        )
        confidence = base_event.get("confidence")
        if confidence is None:
            confidence = base_event.get("conf", 0)
        if confidence is None:
            confidence = 0
        if isinstance(confidence, (int, float)):
            conf_str = f"{confidence:.2f}"
        else:
            conf_str = str(confidence) if confidence else "0.00"

        table_rows.append(
            {
                "time": found_event.get("ts") if found_event else (lost_event.get("ts") if lost_event else ""),
                "event": "ObjectEvent",
                "information": f"Object Id={object_id_val}; class: {class_name}; conf: {conf_str}",
                "source": base_event.get("source_name", ""),
                "time_lost": lost_event.get("ts") if lost_event else "",
                "preview": found_event.get("image_filename") if found_event else "",
                "lost_preview": lost_event.get("image_filename") if lost_event else "",
                "date_folder": (found_event or lost_event or {}).get("date_folder", ""),
                "found_event": found_event,
                "lost_event": lost_event,
            }
        )
    table_rows.sort(key=lambda row: str(row.get("time") or ""), reverse=True)
    return table_rows


def group_events_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple, dict[str, Any]] = defaultdict(lambda: {"found": None, "lost": None})
    cam_events: list[dict[str, Any]] = []
    sys_events: list[dict[str, Any]] = []

    for ev in rows:
        event_type = ev.get("event_type") or ""
        if event_type in ("attr_found", "attr_lost"):
            key = ("attr", ev.get("object_id"))
            if event_type == "attr_found":
                grouped[key]["found"] = ev
            else:
                grouped[key]["lost"] = ev
        elif event_type in ("zone_entered", "zone_left"):
            key = ("zone", ev.get("source_id"), ev.get("object_id"))
            if event_type == "zone_entered":
                grouped[key]["found"] = ev
            else:
                grouped[key]["lost"] = ev
        elif event_type in ("fov_found", "fov_lost"):
            key = ("fov", ev.get("source_id"), ev.get("object_id"))
            if event_type == "fov_found":
                grouped[key]["found"] = ev
            else:
                grouped[key]["lost"] = ev
        elif event_type == "cam":
            cam_events.append(ev)
        elif event_type == "sys":
            sys_events.append(ev)

    table_rows: list[dict[str, Any]] = []
    for key, pair in grouped.items():
        kind = key[0]
        found_ev = pair["found"]
        lost_ev = pair["lost"]
        base = found_ev or lost_ev
        if not base:
            continue

        if kind == "attr":
            event_name = "AttributeEvent"
            info = (
                f"AttributeEvent name={base.get('event_name', '')}; "
                f"obj={base.get('object_id')}; "
                f"class={base.get('class_name', base.get('class_id', ''))}; "
                f"attrs={base.get('attrs', [])}"
            )
        elif kind == "zone":
            event_name = "ZoneEvent"
            zone_id = base.get("zone_id")
            info = f"ZoneEvent obj={base.get('object_id')} zone={zone_id}" if zone_id is not None else f"ZoneEvent obj={base.get('object_id')}"
        else:
            event_name = "FOVEvent"
            info = f"FOVEvent obj={base.get('object_id')}"

        table_rows.append(
            {
                "source": base.get("source_name") or str(base.get("source_id", "")),
                "event": event_name,
                "information": info,
                "time": found_ev.get("ts") if found_ev else base.get("ts", ""),
                "time_lost": lost_ev.get("ts") if lost_ev else "",
                "preview": found_ev.get("image_filename", "") if found_ev else "",
                "lost_preview": lost_ev.get("image_filename", "") if lost_ev else "",
                "date_folder": base.get("date_folder", ""),
                "found_event": found_ev,
                "lost_event": lost_ev,
            }
        )

    for ev in cam_events:
        clean = sanitize_camera_event_record(ev)
        identity = (
            source_names_label(clean.get("source_names"))
            or source_names_label(clean.get("source_name"))
            or media_url_without_credentials(str(clean.get("camera_full_address") or ""))
        )
        connection_status = bool(clean.get("connection_status", False))
        table_rows.append(
            {
                "source": identity or "camera",
                "event": "CameraEvent",
                "information": format_camera_event_information(identity, connected=connection_status),
                "time": clean.get("ts", ""),
                "time_lost": "",
                "preview": "",
                "lost_preview": "",
                "date_folder": clean.get("date_folder", ""),
            }
        )

    for ev in sys_events:
        system_event = ev.get("system_event", "")
        information = ev.get("information")
        if not information:
            if system_event == "SystemStart":
                information = "System started"
            elif system_event == "CudaOutOfMemory":
                information = "CUDA out of memory: detection disabled"
            else:
                information = "System stopped"
        table_rows.append(
            {
                "source": "System",
                "event": "SystemEvent",
                "information": information,
                "time": ev.get("ts", ""),
                "time_lost": "",
                "preview": "",
                "lost_preview": "",
            }
        )

    table_rows.sort(key=lambda row: str(row.get("time") or ""), reverse=True)
    return table_rows
