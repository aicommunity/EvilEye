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


def clone_capture_image(frame: CaptureImage) -> CaptureImage:
    cloned = CaptureImage()
    cloned.source_id = getattr(frame, "source_id", None)
    cloned.time_stamp = getattr(frame, "time_stamp", None)
    cloned.frame_id = getattr(frame, "frame_id", None)
    cloned.current_video_frame = getattr(frame, "current_video_frame", None)
    cloned.current_video_position = getattr(frame, "current_video_position", None)
    image = getattr(frame, "image", None)
    cloned.image = image.copy() if image is not None else None
    return cloned


def render_preview_frame(frame: CaptureImage, context: PreviewRenderContext) -> CaptureImage:
    rendered = clone_capture_image(frame)
    apply_preview_overlay(rendered, context)
    return rendered


def apply_preview_overlay(frame: CaptureImage, context: PreviewRenderContext) -> CaptureImage:
    if frame is None or getattr(frame, "image", None) is None:
        return frame

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
    if context.show_debug_info:
        utils.draw_debug_info(frame, context.debug_info or {})
    _draw_zones(frame.image, context.zones)
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
    for zone in zones:
        try:
            zone_type, zone_coords, _ = zone
        except Exception:
            continue
        if not zone_coords:
            continue
        zone_name = str(zone_type).strip().lower()
        if zone_name in {"rect", "rectangle"} and len(zone_coords) >= 2:
            x1, y1 = zone_coords[0]
            x2, y2 = zone_coords[1]
            cv2.rectangle(
                image,
                (int(x1 * w), int(y1 * h)),
                (int(x2 * w), int(y2 * h)),
                (0, 0, 255),
                thickness=2,
            )
            continue
        points = np.int32([[(int(px * w), int(py * h)) for px, py in zone_coords]])
        cv2.polylines(image, points, isClosed=True, color=(0, 0, 255), thickness=2)


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
    overlay = image.copy()
    cv2.rectangle(overlay, (x, y), (x + box_width, y + box_height), (0, 0, 0), thickness=-1)
    cv2.addWeighted(overlay, 0.35, image, 0.65, 0.0, dst=image)

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
