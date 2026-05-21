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
