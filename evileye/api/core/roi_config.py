"""ROI configuration helpers shared by API editors and runtime control."""
from __future__ import annotations

from typing import Any

from evileye.visualization_modules.overlay_config import (
    extract_debug_rois_from_params,
    source_video_size_for_source,
    video_size_for_source,
)

_DEFAULT_FRAME_SIZE = (1920, 1080)


def _detectors_list(body: dict[str, Any]) -> list[dict[str, Any]] | None:
    detectors = body.get("detectors")
    if isinstance(detectors, list):
        return [d for d in detectors if isinstance(d, dict)]
    pipe = body.get("pipeline")
    if isinstance(pipe, dict):
        nested = pipe.get("detectors")
        if isinstance(nested, list):
            return [d for d in nested if isinstance(d, dict)]
    return None


def detector_entry_for_source(
    body: dict[str, Any], source_id: int
) -> tuple[dict[str, Any], int] | None:
    """Return (detector dict, source_idx within detector.source_ids) for source_id."""
    detectors = _detectors_list(body)
    if not detectors:
        return None
    for det in detectors:
        source_ids = det.get("source_ids") or []
        if not isinstance(source_ids, list):
            continue
        if source_id in source_ids:
            return det, source_ids.index(source_id)
        if not source_ids:
            return det, 0
    if detectors:
        return detectors[0], 0
    return None


def _roi_is_pixel_coords(roi: list[float]) -> bool:
    try:
        return max(float(v) for v in roi[:4]) > 1.5
    except (TypeError, ValueError, IndexError):
        return False


def _xywh_to_xyxy_norm(
    roi_xywh: list[float], img_w: int, img_h: int
) -> list[float] | None:
    if len(roi_xywh) < 4:
        return None
    try:
        x, y, rw, rh = [float(v) for v in roi_xywh[:4]]
    except (TypeError, ValueError):
        return None
    if _roi_is_pixel_coords(roi_xywh):
        if img_w <= 0 or img_h <= 0:
            return None
        x1 = x / float(img_w)
        y1 = y / float(img_h)
        x2 = (x + rw) / float(img_w)
        y2 = (y + rh) / float(img_h)
    else:
        x1, y1 = x, y
        x2, y2 = x + rw, y + rh
    return [x1, y1, x2, y2]


def _xyxy_norm_to_xywh(
    roi_xyxy: list[float], img_w: int, img_h: int
) -> list[int] | None:
    if len(roi_xyxy) < 4:
        return None
    try:
        x1, y1, x2, y2 = [float(v) for v in roi_xyxy[:4]]
    except (TypeError, ValueError):
        return None
    if img_w <= 0 or img_h <= 0:
        return None
    left = min(x1, x2)
    right = max(x1, x2)
    top = min(y1, y2)
    bottom = max(y1, y2)
    x = int(round(left * img_w))
    y = int(round(top * img_h))
    # Inclusive boundaries (matches ObjectDetectorBase.set_rois_for_source).
    w = max(0, int(round(right * img_w)) - x + 1)
    h = max(0, int(round(bottom * img_h)) - y + 1)
    if w <= 0 or h <= 0:
        return None
    return [x, y, w, h]


def detector_rois_for_source(body: dict[str, Any], source_id: int) -> list[list[float]]:
    """Read raw ROI rectangles ([x,y,w,h]) for source from nested detector config."""
    entry = detector_entry_for_source(body, source_id)
    if entry is None:
        return []
    det, source_idx = entry
    roi_groups = det.get("roi") or []
    if not isinstance(roi_groups, list) or source_idx not in range(len(roi_groups)):
        return []
    raw = roi_groups[source_idx]
    if not isinstance(raw, list):
        return []
    out: list[list[float]] = []
    for item in raw:
        if isinstance(item, (list, tuple)) and len(item) >= 4:
            try:
                out.append([float(v) for v in item[:4]])
            except (TypeError, ValueError):
                continue
    return out


def _infer_frame_size_from_pixel_rois(rois_xywh: list[list[float]]) -> tuple[int, int] | None:
    """Infer native frame size from stored pixel ROI extents."""
    max_right = 0
    max_bottom = 0
    found = False
    for roi in rois_xywh:
        if not _roi_is_pixel_coords(roi):
            continue
        try:
            x, y, w, h = [float(v) for v in roi[:4]]
        except (TypeError, ValueError):
            continue
        max_right = max(max_right, int(round(x + w)))
        max_bottom = max(max_bottom, int(round(y + h)))
        found = True
    if found and max_right > 0 and max_bottom > 0:
        return max_right, max_bottom
    return None


def roi_frame_size_for_source(body: dict[str, Any], source_id: int) -> tuple[int, int]:
    """Best frame size for ROI editor normalization (source metadata + ROI inference)."""
    configured = source_video_size_for_source(body, source_id)
    inferred = _infer_frame_size_from_pixel_rois(detector_rois_for_source(body, source_id))
    if inferred:
        if (
            configured == _DEFAULT_FRAME_SIZE
            or inferred[0] > configured[0]
            or inferred[1] > configured[1]
        ):
            return (
                max(configured[0], inferred[0]),
                max(configured[1], inferred[1]),
            )
    if configured != _DEFAULT_FRAME_SIZE:
        return configured
    return video_size_for_source(body, source_id)


def set_detector_rois_for_source(
    body: dict[str, Any], source_id: int, rois_xywh: list[list[float]]
) -> None:
    """Write ROI rectangles ([x,y,w,h]) for source into nested detector config."""
    entry = detector_entry_for_source(body, source_id)
    if entry is None:
        return
    det, source_idx = entry
    roi_groups = det.get("roi")
    if not isinstance(roi_groups, list):
        roi_groups = []
        det["roi"] = roi_groups
    while len(roi_groups) <= source_idx:
        roi_groups.append([])
    roi_groups[source_idx] = [list(r) for r in rois_xywh]


def ui_rois_from_pixels(
    rois_pixel: list[list[float]], img_w: int, img_h: int
) -> list[list[float]]:
    """Convert stored pixel ROI ([x,y,w,h]) to normalized UI xyxy."""
    ui: list[list[float]] = []
    for raw in rois_pixel or []:
        converted = _xywh_to_xyxy_norm(raw, img_w, img_h)
        if converted is not None:
            ui.append(converted)
    return ui


def ui_pixels_from_rois(
    ui_rois: list[list[float]], img_w: int, img_h: int
) -> list[list[int]]:
    """Convert normalized UI xyxy to detector storage ([x,y,w,h] pixels)."""
    out: list[list[int]] = []
    for roi in ui_rois or []:
        converted = _xyxy_norm_to_xywh(roi, img_w, img_h)
        if converted is not None:
            out.append(converted)
    return out


def roi_coord_ref(body: dict[str, Any], source_id: int) -> dict[str, int]:
    """Frame size hint for editor save/load (source metadata, matches live coord_ref)."""
    w, h = source_video_size_for_source(body, source_id)
    return {"w": int(w), "h": int(h)}


def display_rois_for_source(body: dict[str, Any], source_id: int) -> list[list[float]]:
    """Normalized UI xyxy using same logic as live config fallback overlay."""
    w, h = source_video_size_for_source(body, source_id)
    return extract_debug_rois_from_params(body, source_id=source_id, img_w=w, img_h=h)


def ui_rois_from_detector(body: dict[str, Any], source_id: int) -> list[list[float]]:
    """Convert detector ROI ([x,y,w,h]) to normalized UI xyxy (legacy alias)."""
    return display_rois_for_source(body, source_id)


def ui_rois_to_detector(
    body: dict[str, Any], source_id: int, ui_rois: list[list[float]]
) -> list[list[int]]:
    """Convert normalized UI xyxy to detector storage ([x,y,w,h] pixels)."""
    w, h = source_video_size_for_source(body, source_id)
    return ui_pixels_from_rois(ui_rois, w, h)


def xywh_list_to_xyxy_int(rois_xywh: list[list[float]]) -> list[list[int]]:
    """Convert stored [x,y,w,h] rects to inclusive pixel xyxy for set_rois_for_source."""
    out: list[list[int]] = []
    for roi in rois_xywh or []:
        if not isinstance(roi, (list, tuple)) or len(roi) < 4:
            continue
        try:
            x, y, w, h = [int(round(float(v))) for v in roi[:4]]
        except (TypeError, ValueError):
            continue
        if w <= 0 or h <= 0:
            continue
        out.append([x, y, x + w - 1, y + h - 1])
    return out
