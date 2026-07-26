"""Shared ROI split for thread and MP detection paths."""

from __future__ import annotations

from typing import Any


def split_capture_for_detection(
    image: Any,
    roi: list,
    roi_coords_per_camera: dict,
) -> list:
    """Split a capture frame into ROI batches (same contract as detection_thread_base)."""
    if not roi or not roi[0]:
        return [[image, [0, 0]]]
    coords = roi_coords_per_camera[image.source_id]
    from evileye.utils import utils

    return utils.create_roi(image, coords)
