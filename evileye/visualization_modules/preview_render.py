from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np

from ..capture.video_capture_base import CaptureImage
from ..utils import utils


@dataclass
class PreviewRenderContext:
    source_name: str | int | None = None
    source_duration_msecs: float | int | None = None
    track_info: list[Any] = field(default_factory=list)
    debug_info: dict[str, Any] = field(default_factory=dict)
    show_debug_info: bool = False
    font_scale: float = 3.0
    font_thickness: int = 5
    font_color: tuple[int, int, int] = (0, 0, 255)
    text_config: dict[str, Any] = field(default_factory=dict)
    class_mapping: dict[str, int] = field(default_factory=dict)
    event_signal_enabled: bool = False
    event_color_rgb: tuple[int, int, int] = (255, 0, 0)
    event_active_obj_ids: set[int] = field(default_factory=set)
    active_event_labels: list[str] = field(default_factory=list)
    zones: list[Any] = field(default_factory=list)
    show_boxes: bool = True
    show_zones: bool = True
    # When False, boxes/zones are sent via metadata only (SVG overlay in web UI).
    burn_in_overlay: bool = True


def serialize_preview_metadata(
    context: PreviewRenderContext,
    image_shape=None,
    *,
    frame_id: int | None = None,
    frame: CaptureImage | None = None,
    source_id: int | None = None,
) -> dict[str, Any]:
    """Build WS overlay payload (normalized 0..1 coords) from preview context."""
    h = w = None
    if image_shape is not None and len(image_shape) >= 2:
        h, w = int(image_shape[0]), int(image_shape[1])

    resolved_source_id = source_id
    if resolved_source_id is None and frame is not None:
        resolved_source_id = getattr(frame, "source_id", None)
    objects: list[dict[str, Any]] = []
    if context.show_boxes:
        for obj in context.track_info or []:
            try:
                track = getattr(obj, "track", None)
                bbox = getattr(track, "bounding_box", None) if track is not None else None
                if bbox is None:
                    bbox = getattr(obj, "bounding_box", None)
                if not bbox or len(bbox) < 4:
                    continue
                x1, y1, x2, y2 = [float(v) for v in bbox[:4]]
                if w and h and max(x1, y1, x2, y2) > 1.5:
                    x1, x2 = x1 / w, x2 / w
                    y1, y2 = y1 / h, y2 / h
                class_id = getattr(obj, "class_id", None)
                if class_id is None and track is not None:
                    class_id = getattr(track, "class_id", None)
                class_name = None
                if context.class_mapping and class_id is not None:
                    try:
                        reverse = {cid: name for name, cid in context.class_mapping.items()}
                        class_name = reverse.get(class_id)
                    except Exception:
                        class_name = None
                conf = getattr(track, "confidence", None) if track is not None else None
                track_id = getattr(track, "track_id", None) if track is not None else getattr(obj, "object_id", None)
                object_id = getattr(obj, "object_id", None)
                global_id = getattr(obj, "global_id", None)
                event_active = bool(object_id is not None and object_id in (context.event_active_obj_ids or set()))
                attributes = _serialize_object_attributes(getattr(obj, "attributes", None))
                trail = _serialize_object_trail(obj, frame_id, w, h)
                objects.append(
                    {
                        "object_id": object_id,
                        "global_id": global_id,
                        "track_id": track_id,
                        "class_id": class_id,
                        "class_name": class_name,
                        "conf": float(conf) if conf is not None else None,
                        "bbox": [x1, y1, x2, y2],
                        "event_active": event_active,
                        "attributes": attributes,
                        "trail": trail,
                    }
                )
            except Exception:
                continue

    zones: list[dict[str, Any]] = []
    if context.show_zones:
        for zone in context.zones or []:
            try:
                zone_type, zone_coords, _extra = zone
                points = _normalize_zone_points(zone_coords, w, h)
                if points:
                    zones.append({"name": str(zone_type), "points": points})
            except Exception:
                continue

    payload = {
        "objects": objects,
        "zones": zones,
        "signalization": bool(context.event_signal_enabled and context.active_event_labels),
        "event_labels": list(context.active_event_labels or []),
        "event_color": [int(v) for v in context.event_color_rgb],
        "debug_rois": _serialize_debug_rois(context.debug_info, source_id=resolved_source_id, w=w, h=h)
        if context.show_debug_info else [],
        "overlay": _serialize_overlay_info(context, frame),
    }
    return payload


def _normalize_zone_points(
    zone_coords: Any,
    w: int | None,
    h: int | None,
) -> list[list[float]]:
    """Normalize zone polygon points to 0..1 (pixel coords use frame w/h like ROI)."""
    if not zone_coords:
        return []
    points_raw: list[tuple[float, float]] = []
    for coord in zone_coords or []:
        if not isinstance(coord, (list, tuple)) or len(coord) < 2:
            continue
        points_raw.append((float(coord[0]), float(coord[1])))
    if not points_raw:
        return []
    max_val = max(max(abs(px), abs(py)) for px, py in points_raw)
    if w and h and max_val > 1.5:
        return [[px / float(w), py / float(h)] for px, py in points_raw]
    return [[px, py] for px, py in points_raw]


def _serialize_object_attributes(attrs: Any, max_items: int = 4) -> list[dict[str, Any]]:
    if not isinstance(attrs, dict) or not attrs:
        return []
    result: list[dict[str, Any]] = []
    for name, data in list(attrs.items())[:max_items]:
        if not isinstance(data, dict):
            continue
        result.append(
            {
                "name": str(name),
                "state": str(data.get("state", "none")),
                "confidence": float(data.get("confidence_smooth", 0.0) or 0.0),
                "frames_present": int(data.get("frames_present", 0) or 0),
                "total_time_ms": int(data.get("total_time_ms", 0) or 0),
                "found_ratio": float(data.get("found_ratio", 0.0) or 0.0),
            }
        )
    return result


def _serialize_object_trail(obj: Any, frame_id: int | None, w: int | None, h: int | None, max_segments: int = 8):
    history = list(getattr(obj, "history", None) or [])
    if not history:
        return []
    last_hist_index = len(history) - 1
    if frame_id is not None and getattr(obj, "frame_id", None) != frame_id:
        for i in range(len(history) - 1):
            try:
                if getattr(history[i], "frame_id", None) == frame_id:
                    last_hist_index = i
                    break
            except Exception:
                continue
    hist_start_index = max(0, last_hist_index - max_segments)
    points: list[list[float]] = []
    for i in range(hist_start_index, last_hist_index + 1):
        try:
            track = getattr(history[i], "track", None)
            bbox = getattr(track, "bounding_box", None) if track is not None else None
            if not bbox or len(bbox) < 4:
                continue
            x1, _, x2, y2 = [float(v) for v in bbox[:4]]
            cx, cy = (x1 + x2) / 2.0, y2
            if w and h and max(cx, cy) > 1.5:
                cx, cy = cx / float(w), cy / float(h)
            points.append([cx, cy])
        except Exception:
            continue
    return points


def _serialize_debug_rois(
    debug_info: dict[str, Any] | None,
    *,
    source_id: int | None,
    w: int | None,
    h: int | None,
) -> list[list[float]]:
    if not debug_info or source_id is None:
        return []
    detectors = debug_info.get("detectors")
    if not isinstance(detectors, dict):
        return []
    rois_out: list[list[float]] = []
    for detector_info in detectors.values():
        try:
            source_ids = detector_info.get("source_ids") or []
            if source_id not in source_ids:
                continue
            source_idx = source_ids.index(source_id)
            roi_groups = detector_info.get("roi") or []
            if not isinstance(roi_groups, list) or source_idx not in range(len(roi_groups)):
                continue
            for roi in roi_groups[source_idx] or []:
                if not isinstance(roi, (list, tuple)) or len(roi) < 4:
                    continue
                x, y, rw, rh = [float(v) for v in roi[:4]]
                if w and h and max(x, y, rw, rh) > 1.5:
                    x1 = x / float(w)
                    y1 = y / float(h)
                    x2 = (x + rw) / float(w)
                    y2 = (y + rh) / float(h)
                else:
                    x1, y1, x2, y2 = x, y, x + rw, y + rh
                rois_out.append([x1, y1, x2, y2])
        except Exception:
            continue
    return rois_out


def _serialize_overlay_info(context: PreviewRenderContext, frame: CaptureImage | None) -> dict[str, Any]:
    info: dict[str, Any] = {}
    if context.source_name is not None:
        info["source_name"] = str(context.source_name)
    if frame is not None and context.source_duration_msecs is not None:
        pos = getattr(frame, "current_video_position", None)
        if pos is not None:
            try:
                info["time_label"] = f"{float(pos) / 1000.0:.1f} [{float(context.source_duration_msecs) / 1000.0:.1f}]"
            except Exception:
                pass
    return info


def clone_capture_image(frame: CaptureImage) -> CaptureImage:
    cloned = CaptureImage()
    cloned.source_id = getattr(frame, "source_id", None)
    cloned.time_stamp = getattr(frame, "time_stamp", None)
    cloned.frame_id = getattr(frame, "frame_id", None)
    cloned.current_video_frame = getattr(frame, "current_video_frame", None)
    cloned.current_video_position = getattr(frame, "current_video_position", None)
    cloned.source_video_duration = getattr(frame, "source_video_duration", None)
    image = getattr(frame, "image", None)
    cloned.image = image.copy() if image is not None else None
    try:
        setattr(cloned, "_streaming_image_owned", True)
    except Exception:
        pass
    return cloned


def render_preview_frame(frame: CaptureImage, context: PreviewRenderContext) -> CaptureImage:
    rendered = clone_capture_image(frame)
    apply_preview_overlay(rendered, context)
    return rendered


def apply_preview_overlay(frame: CaptureImage, context: PreviewRenderContext) -> CaptureImage:
    if frame is None or getattr(frame, "image", None) is None:
        return frame

    if context.show_boxes and context.burn_in_overlay:
        utils.draw_boxes_tracking(
            frame,
            context.track_info or [],
            context.source_name,
            context.source_duration_msecs,
            context.font_scale,
            context.font_thickness,
            context.font_color,
            text_config=context.text_config,
            class_mapping=context.class_mapping,
            event_active_obj_ids=context.event_active_obj_ids,
            event_color=_rgb_to_bgr(context.event_color_rgb),
        )
    if context.show_debug_info and context.burn_in_overlay:
        utils.draw_debug_info(frame, context.debug_info or {})
    if context.show_zones and context.burn_in_overlay:
        _draw_zones(frame.image, context.zones)
    if context.burn_in_overlay:
        _draw_event_overlay(frame.image, context)
    return frame


def _rgb_to_bgr(color_rgb: tuple[int, int, int] | list[int]) -> tuple[int, int, int]:
    try:
        r, g, b = color_rgb
        return int(b), int(g), int(r)
    except Exception:
        return (0, 0, 255)


def _draw_zones(image, zones: list[Any]) -> None:
    if image is None or not zones:
        return

    h, w = image.shape[:2]
    red_bgr = (0, 0, 255)

    # Semi-transparent fill for zones (visual clarity).
    # We blend once for all zones to keep it reasonably cheap.
    fill_alpha = 0.50
    overlay = image.copy()
    # (kind, ...)
    borders: list[tuple[Any, ...]] = []

    for zone in zones:
        try:
            zone_type, zone_coords, _ = zone
        except Exception:
            continue

        if not zone_coords:
            continue

        zone_name = str(zone_type).strip().lower()

        # Rectangle (normalized coords)
        if zone_name in {"rect", "rectangle"} and len(zone_coords) >= 2:
            (x1, y1) = zone_coords[0]
            (x2, y2) = zone_coords[1]

            x_left, x_right = (min(x1, x2), max(x1, x2))
            y_top, y_bottom = (min(y1, y2), max(y1, y2))

            pt1 = (int(x_left * w), int(y_top * h))
            pt2 = (int(x_right * w), int(y_bottom * h))

            cv2.rectangle(overlay, pt1, pt2, red_bgr, thickness=-1)
            borders.append(("rect", pt1, pt2))
            continue

        # Polygon (normalized points)
        pts = []
        for px, py in zone_coords:
            try:
                pts.append((int(px * w), int(py * h)))
            except Exception:
                continue

        if not pts:
            continue

        pts_arr = np.asarray(pts, dtype=np.int32)
        cv2.fillPoly(overlay, [pts_arr], red_bgr)
        borders.append(("poly", pts_arr))

    # Blend filled areas.
    cv2.addWeighted(overlay, fill_alpha, image, 1.0 - fill_alpha, 0.0, dst=image)

    # Re-draw borders fully opaque for crisp outlines.
    for border in borders:
        kind = border[0]
        if kind == "rect":
            _, pt1, pt2 = border
            cv2.rectangle(image, pt1, pt2, red_bgr, thickness=2)
        else:
            _, pts_arr = border
            cv2.polylines(image, [pts_arr], isClosed=True, color=red_bgr, thickness=2)


def _draw_event_overlay(image, context: PreviewRenderContext) -> None:
    if image is None or not context.event_signal_enabled or not context.active_event_labels:
        return

    h, w = image.shape[:2]
    color = _rgb_to_bgr(context.event_color_rgb)
    cv2.rectangle(image, (0, 0), (w - 1, h - 1), color, thickness=4)

    line_height = max(22, h // 32)
    x = 12
    y = 12
    box_width = max(220, min(w - 24, int(w * 0.45)))
    box_height = min(h - 24, 12 + len(context.active_event_labels) * line_height + 12)
    x2 = min(w, x + box_width)
    y2 = min(h, y + box_height)
    if x2 > x and y2 > y:
        roi = image[y:y2, x:x2]
        if roi.size > 0:
            darkened = np.zeros_like(roi)
            cv2.addWeighted(darkened, 0.35, roi, 0.65, 0.0, dst=roi)

    font_scale = max(0.5, min(w, h) / 1000.0)
    thickness = max(1, int(font_scale * 2))
    max_lines = max(1, (box_height - 20) // line_height)
    for idx, label in enumerate(context.active_event_labels[:max_lines]):
        baseline_y = y + 18 + idx * line_height
        cv2.putText(
            image,
            str(label),
            (x + 8, baseline_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            font_scale,
            color,
            thickness,
            cv2.LINE_AA,
        )
