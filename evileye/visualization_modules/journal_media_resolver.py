from __future__ import annotations

import datetime
import glob
import logging
import os
from typing import Any, Optional

from evileye.visualization_modules.journal_metadata_extractor import EventMetadataExtractor
from evileye.visualization_modules.journal_path_resolver import JournalPathResolver

DEFAULT_IMAGE_WIDTH = 1920
DEFAULT_IMAGE_HEIGHT = 1080
MIN_VIDEO_BYTES = 1000
VIDEO_EXTENSIONS = (".mp4", ".mkv", ".webm", ".avi")


def row_key(row: dict[str, Any]) -> str:
    return f"{row.get('time')}|{row.get('event')}|{row.get('information')}"


def relative_to_base(abs_path: str | None, base_dir: str) -> str | None:
    if not abs_path or not base_dir:
        return None
    try:
        base = os.path.realpath(base_dir)
        target = os.path.realpath(abs_path)
        if not target.startswith(base + os.sep) and target != base:
            return None
        return os.path.relpath(target, base)
    except Exception:
        return None


def _parse_timestamp(value: Any) -> datetime.datetime | None:
    if isinstance(value, datetime.datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except Exception:
            return None
    return None


def _video_file_ok(path: str) -> bool:
    if not os.path.isfile(path):
        return False
    try:
        return os.path.getsize(path) >= MIN_VIDEO_BYTES
    except OSError:
        return False


def _glob_video(pattern_base: str) -> str | None:
    for ext in VIDEO_EXTENSIONS:
        for path in glob.glob(pattern_base + ext):
            if _video_file_ok(path):
                return path
    return None


def _saved_video_path(event_data: dict[str, Any], base_dir: str, *, is_lost: bool) -> str | None:
    video_path_key = "video_path_lost" if is_lost else "video_path"
    saved_video_path = event_data.get(video_path_key)
    if not saved_video_path:
        return None
    full_path = os.path.join(base_dir, str(saved_video_path))
    return full_path if _video_file_ok(full_path) else None


def resolve_event_video_path(
        event_data: dict[str, Any] | None,
        base_dir: str,
        *,
        is_lost: bool = False,
        source_mappings: dict[str, tuple[Any, Any]] | None = None,
        preview_path: str = "",
        logger: logging.Logger | None = None,
) -> str | None:
    log = logger or logging.getLogger("journal_media_resolver")
    if not event_data or not base_dir:
        return None

    video_path_key = "video_path_lost" if is_lost else "video_path"
    saved_video_path = event_data.get(video_path_key)
    if saved_video_path:
        full_path = os.path.join(base_dir, str(saved_video_path))
        if _video_file_ok(full_path):
            return full_path
        if os.path.exists(full_path):
            log.debug("Saved video too small or missing: %s preview=%s", full_path, preview_path)

    event_type = event_data.get("event_type", "")
    time_stamp = event_data.get("ts") or event_data.get("time_stamp")
    source_name = event_data.get("source_name", "")
    source_id = event_data.get("source_id")
    event_id_numeric = event_data.get("event_id_numeric")
    if not event_type or not time_stamp:
        return None

    dt = _parse_timestamp(time_stamp)
    if dt is None:
        return None

    date_folder = dt.strftime("%Y-%m-%d")
    time_str = dt.strftime("%Y%m%d_%H%M%S")
    time_str_partial = dt.strftime("%Y%m%d_%H%M")

    event_name_map = {
        "zone_entered": "ZoneEvent",
        "zone_left": "ZoneEvent",
        "attr_found": "AttributeEvent",
        "attr_lost": "AttributeEvent",
        "fov_found": "FOVEvent",
        "fov_lost": "FOVEvent",
    }
    event_name = event_name_map.get(str(event_type), str(event_type))

    source_mappings = source_mappings or {}
    possible_source_names: list[str] = []
    if source_id is not None:
        for src_name, (src_id, _address) in source_mappings.items():
            if src_id == source_id:
                possible_source_names.append(src_name)
    if source_name and source_name not in possible_source_names:
        possible_source_names.append(str(source_name))
    if not possible_source_names:
        possible_source_names = [str(source_name)] if source_name else []

    possible_camera_folders: list[str] = []
    if len(possible_source_names) > 1:
        possible_camera_folders.append("-".join(possible_source_names))
    for src_name in possible_source_names:
        if src_name and src_name not in possible_camera_folders:
            possible_camera_folders.append(src_name)
    if not possible_camera_folders:
        possible_camera_folders = [str(source_name)] if source_name else []

    videos_base_dir = os.path.join(base_dir, "Events", date_folder, "Videos")
    if not os.path.isdir(videos_base_dir):
        return None

    def _check(path: str) -> str | None:
        return path if _video_file_ok(path) else None

    if event_id_numeric is not None:
        for camera_folder in possible_camera_folders:
            for src_name in possible_source_names:
                candidate_base = os.path.join(
                    videos_base_dir,
                    camera_folder,
                    f"{src_name}_{event_name}_{event_id_numeric}_{time_str}",
                )
                found = _glob_video(candidate_base)
                if found:
                    return found

        try:
            for folder_name in os.listdir(videos_base_dir):
                folder_path = os.path.join(videos_base_dir, folder_name)
                if not os.path.isdir(folder_path):
                    continue
                pattern_base = os.path.join(folder_path, f"*_{event_name}_{event_id_numeric}_{time_str}")
                found = _glob_video(pattern_base)
                if found:
                    return found
                pattern_time_base = os.path.join(folder_path, f"*_{event_name}_*_{time_str}")
                matching = []
                for ext in VIDEO_EXTENSIONS:
                    matching.extend(glob.glob(pattern_time_base + ext))
                for video_path in matching:
                    filename = os.path.basename(video_path)
                    if any(src in filename for src in possible_source_names if src):
                        found = _check(video_path)
                        if found:
                            return found
                if matching:
                    found = _check(matching[0])
                    if found:
                        return found
        except OSError:
            pass

    for camera_folder in possible_camera_folders:
        for src_name in possible_source_names:
            alt_base = os.path.join(videos_base_dir, camera_folder, f"{src_name}_{event_name}_{time_str}")
            found = _glob_video(alt_base)
            if found:
                return found

    try:
        all_matching: list[str] = []
        for ext in VIDEO_EXTENSIONS:
            pattern = f"*_{event_name}_*_{time_str}{ext}"
            for folder_name in os.listdir(videos_base_dir):
                folder_path = os.path.join(videos_base_dir, folder_name)
                if os.path.isdir(folder_path):
                    all_matching.extend(glob.glob(os.path.join(folder_path, pattern)))
        if not all_matching:
            for ext in VIDEO_EXTENSIONS:
                pattern_partial = f"*_{event_name}_*_{time_str_partial}*{ext}"
                for folder_name in os.listdir(videos_base_dir):
                    folder_path = os.path.join(videos_base_dir, folder_name)
                    if os.path.isdir(folder_path):
                        all_matching.extend(glob.glob(os.path.join(folder_path, pattern_partial)))
        for video_path in all_matching:
            filename = os.path.basename(video_path)
            if any(src in filename for src in possible_source_names if src):
                found = _check(video_path)
                if found:
                    return found
        if all_matching:
            return _check(all_matching[0])
    except OSError:
        pass
    return None


def resolve_stream_segment_path(
        event_data: dict[str, Any] | None,
        base_dir: str,
        *,
        source_mappings: dict[str, tuple[Any, Any]] | None = None,
        logger: logging.Logger | None = None,
) -> tuple[str | None, int]:
    log = logger or logging.getLogger("journal_media_resolver")
    if not event_data or not base_dir:
        return None, 0

    timestamp = event_data.get("ts") or event_data.get("time_stamp")
    dt = _parse_timestamp(timestamp)
    if dt is None:
        return None, 0

    date_folder = dt.strftime("%Y-%m-%d")
    source_name = str(event_data.get("source_name") or "")
    source_id = event_data.get("source_id")
    source_mappings = source_mappings or {}

    streams_dir = os.path.join(base_dir, "Streams", date_folder)
    if not os.path.isdir(streams_dir):
        return None, 0

    camera_folders: list[str] = []
    if source_name:
        camera_folder_path = os.path.join(streams_dir, source_name)
        if os.path.isdir(camera_folder_path):
            camera_folders.append(source_name)

    if source_id is not None:
        for src_name, (src_id, _address) in source_mappings.items():
            if src_id == source_id:
                composite_folder = os.path.join(streams_dir, src_name)
                if os.path.isdir(composite_folder) and src_name not in camera_folders:
                    camera_folders.append(src_name)

    try:
        for folder_name in os.listdir(streams_dir):
            folder_path = os.path.join(streams_dir, folder_name)
            if not os.path.isdir(folder_path) or folder_name in camera_folders:
                continue
            if source_name and (source_name in folder_name or folder_name in source_name):
                camera_folders.append(folder_name)
    except OSError as exc:
        log.debug("Error listing streams_dir: %s", exc)

    if not camera_folders:
        return None, 0

    segment_length_sec = 300
    best_segment: str | None = None
    best_offset = 0
    min_time_diff = float("inf")

    for camera_folder in camera_folders:
        camera_path = os.path.join(streams_dir, camera_folder)
        if not os.path.isdir(camera_path):
            continue
        for segment_file in glob.glob(os.path.join(camera_path, "*")):
            if os.path.splitext(segment_file)[1].lower() not in VIDEO_EXTENSIONS:
                continue
            filename = os.path.basename(segment_file)
            parts = os.path.splitext(filename)[0].split("_")
            if len(parts) < 3:
                continue
            try:
                segment_start = datetime.datetime.strptime(f"{parts[1]}_{parts[2]}", "%Y%m%d_%H%M%S")
            except ValueError:
                continue
            segment_end = segment_start + datetime.timedelta(seconds=segment_length_sec)
            if segment_start <= dt < segment_end:
                offset_seconds = int((dt - segment_start).total_seconds())
                if _video_file_ok(segment_file):
                    return segment_file, max(0, offset_seconds)
            time_diff = abs((dt - segment_start).total_seconds())
            if time_diff < segment_length_sec and time_diff < min_time_diff:
                min_time_diff = time_diff
                best_segment = segment_file
                best_offset = max(0, int((dt - segment_start).total_seconds()))

    if best_segment and _video_file_ok(best_segment):
        return best_segment, best_offset
    return None, 0


def _image_dimensions(image_path: str | None) -> tuple[int, int]:
    if not image_path or not os.path.isfile(image_path):
        return DEFAULT_IMAGE_WIDTH, DEFAULT_IMAGE_HEIGHT
    try:
        from PIL import Image

        with Image.open(image_path) as img:
            return img.size
    except Exception:
        return DEFAULT_IMAGE_WIDTH, DEFAULT_IMAGE_HEIGHT


def resolve_preview_image_path(
        img_path: str,
        base_dir: str,
        event_data: dict[str, Any] | None,
        journal_type: str,
) -> str | None:
    if not img_path:
        return None
    return JournalPathResolver.resolve_image_path(
        img_path,
        base_dir,
        event_data=event_data,
        journal_type=journal_type,
    )


def _dimensions_for_bbox(abs_preview_path: str | None, journal_type: str) -> tuple[int, int]:
    if not abs_preview_path:
        return 0, 0
    frame = JournalPathResolver.resolve_frame_path(abs_preview_path, journal_type=journal_type)
    target = frame if frame and os.path.isfile(frame) else abs_preview_path
    return _image_dimensions(target)


def enrich_grouped_row(
        row: dict[str, Any],
        *,
        base_dir: str,
        journal_type: str,
        source_mappings: dict[str, tuple[Any, Any]] | None = None,
        include_raw_events: bool = True,
        list_mode: bool = False,
        meta_only: bool = False,
) -> dict[str, Any]:
    enriched = dict(row)
    found_event = enriched.get("found_event") if isinstance(enriched.get("found_event"), dict) else None
    lost_event = enriched.get("lost_event") if isinstance(enriched.get("lost_event"), dict) else None
    base_event = found_event or lost_event or {}

    date_folder = enriched.get("date_folder") or base_event.get("date_folder") or ""
    if not date_folder:
        dt = _parse_timestamp(enriched.get("time"))
        if dt is not None:
            date_folder = dt.strftime("%Y-%m-%d")
    enriched["date_folder"] = date_folder

    def _event_data(mode: str) -> dict[str, Any] | None:
        ev = found_event if mode == "found" else lost_event
        if not ev:
            return None
        payload = dict(ev)
        if date_folder and not payload.get("date_folder"):
            payload["date_folder"] = date_folder
        return payload

    for mode, path_key in (("found", "preview"), ("lost", "lost_preview")):
        img_path = str(enriched.get(path_key) or "")
        event_data = _event_data(mode)
        if list_mode:
            enriched[f"has_{mode}_preview"] = bool(img_path)
        else:
            abs_path = resolve_preview_image_path(img_path, base_dir, event_data, journal_type)
            enriched[f"has_{mode}_preview"] = bool(abs_path and os.path.isfile(abs_path))

    if journal_type == "events":
        if list_mode or meta_only:
            found_abs = _saved_video_path(found_event or {}, base_dir, is_lost=False)
            lost_abs = _saved_video_path(lost_event or {}, base_dir, is_lost=True)
        else:
            found_abs = resolve_event_video_path(
                found_event, base_dir, is_lost=False, source_mappings=source_mappings, preview_path=str(enriched.get("preview") or "")
            )
            lost_abs = resolve_event_video_path(
                lost_event, base_dir, is_lost=True, source_mappings=source_mappings, preview_path=str(enriched.get("lost_preview") or "")
            )
        enriched["has_found_video"] = bool(found_abs)
        enriched["has_lost_video"] = bool(lost_abs)
        enriched["found_video_path"] = relative_to_base(found_abs, base_dir)
        enriched["lost_video_path"] = relative_to_base(lost_abs, base_dir)
        enriched["has_stream_video"] = False
        enriched["stream_video_path"] = None
        enriched["stream_offset_seconds"] = 0
    else:
        if list_mode or meta_only:
            segment_abs = None
            offset = 0
        else:
            segment_abs, offset = resolve_stream_segment_path(found_event, base_dir, source_mappings=source_mappings)
        enriched["has_found_video"] = False
        enriched["has_lost_video"] = False
        enriched["found_video_path"] = None
        enriched["lost_video_path"] = None
        enriched["has_stream_video"] = bool(segment_abs)
        enriched["stream_video_path"] = relative_to_base(segment_abs, base_dir)
        enriched["stream_offset_seconds"] = offset if segment_abs else 0

    if not list_mode:
        for mode in ("found", "lost"):
            ev = found_event if mode == "found" else lost_event
            img_path = str(enriched.get("preview" if mode == "found" else "lost_preview") or "")
            abs_path = resolve_preview_image_path(img_path, base_dir, _event_data(mode), journal_type)
            if meta_only:
                img_w, img_h = DEFAULT_IMAGE_WIDTH, DEFAULT_IMAGE_HEIGHT
            else:
                img_w, img_h = _dimensions_for_bbox(abs_path, journal_type)
            bbox, zone = EventMetadataExtractor.get_bbox_and_zone(ev or {}, is_lost=(mode == "lost"))
            enriched[f"bbox_{mode}"] = EventMetadataExtractor.normalize_bbox_for_display(bbox, img_w, img_h)
            if mode == "found":
                enriched["zone_coords"] = EventMetadataExtractor.normalize_zone_coords(zone, img_w, img_h)
            if enriched.get(f"bbox_{mode}") is None:
                enriched[f"bbox_{mode}"] = None

    if list_mode or not include_raw_events:
        enriched.pop("found_event", None)
        enriched.pop("lost_event", None)

    enriched["row_key"] = row_key(enriched)
    return enriched
