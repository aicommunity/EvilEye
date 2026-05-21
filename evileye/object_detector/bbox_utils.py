"""Bounding-box extraction helpers for detection threads."""

from __future__ import annotations

from typing import Any, List, Optional, Sequence, Tuple

import numpy as np


def extract_xyxy_conf_cls_from_result(result: Any):
    """Return (xyxy, conf, cls) arrays from an ultralytics-style result."""
    if result is None:
        return None, None, None
    boxes = getattr(result, "boxes", None)
    if boxes is None:
        return None, None, None
    try:
        arr = boxes.cpu().numpy()
    except AttributeError:
        try:
            arr = boxes.numpy()
        except Exception:
            return None, None, None
    return arr.xyxy, arr.conf, arr.cls


def roi_boxes_to_image_coords(
        result: Any,
        roi_offset: Sequence[int],
        *,
        logger: Optional[Any] = None,
) -> Tuple[List, List, List]:
    """
    Convert detection boxes for one ROI split to image coordinates.

    Args:
        result: Model prediction for one ROI crop
        roi_offset: (x_offset, y_offset) from split_image entry roi[1]
        logger: Optional logger for debug messages
    """
    bboxes_coords: List = []
    confidences: List = []
    ids: List = []
    coords, confs, class_ids = extract_xyxy_conf_cls_from_result(result)
    if coords is None:
        return bboxes_coords, confidences, ids

    from evileye.utils import utils

    for coord, class_id, conf in zip(coords, class_ids, confs):
        if not np.all(np.isfinite(coord)):
            if logger is not None:
                logger.debug("Skipping bbox with non-finite coords: %s", coord)
            continue
        abs_coords = utils.roi_to_image(coord, roi_offset[0], roi_offset[1])
        bboxes_coords.append(abs_coords)
        confidences.append(conf)
        ids.append(class_id)
    return bboxes_coords, confidences, ids


def mp_dict_list_to_image_coords(
        result_list: list,
        roi_offset: Sequence[int],
        *,
        logger: Optional[Any] = None,
) -> Tuple[List, List, List]:
    """Convert MP worker dict detections to full-image coordinates."""
    from evileye.utils import utils

    bboxes_coords: List = []
    confidences: List = []
    ids: List = []
    for item in result_list:
        if not isinstance(item, dict):
            continue
        coord = item.get("bbox_xyxy", [])
        if not coord or len(coord) < 4:
            continue
        coord_arr = np.asarray(coord, dtype=np.float64)
        if not np.all(np.isfinite(coord_arr)):
            if logger is not None:
                logger.debug("Skipping bbox with non-finite coords: %s", coord)
            continue
        abs_coords = utils.roi_to_image(coord_arr, roi_offset[0], roi_offset[1])
        bboxes_coords.append(abs_coords)
        confidences.append(item.get("confidence", 0.0))
        ids.append(item.get("class_id", -1))
    return bboxes_coords, confidences, ids


def clip_xyxy_list(
        boxes: list,
        width: int,
        height: int,
) -> list:
    """Clip xyxy boxes to image bounds; drop degenerate boxes."""
    if width <= 0 or height <= 0:
        return []
    clipped = []
    max_x = width - 1
    max_y = height - 1
    for box in boxes:
        if box is None or len(box) < 4:
            continue
        x1, y1, x2, y2 = (float(box[0]), float(box[1]), float(box[2]), float(box[3]))
        x1 = max(0.0, min(x1, float(max_x)))
        y1 = max(0.0, min(y1, float(max_y)))
        x2 = max(0.0, min(x2, float(max_x)))
        y2 = max(0.0, min(y2, float(max_y)))
        if x1 < x2 and y1 < y2:
            clipped.append([x1, y1, x2, y2])
    return clipped
