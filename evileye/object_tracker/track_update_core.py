"""Shared BoT-SORT update helpers for thread and MP tracker workers."""

from __future__ import annotations

import datetime
from typing import Any

import numpy as np
from ultralytics.engine.results import Boxes

from ..object_detector.object_detection_base import DetectionResultList
from .tracking_results import TrackingResult, TrackingResultList


def parse_detections_to_boxes(det_info: DetectionResultList | dict, image: np.ndarray):
    """Build ultralytics Boxes from detection list (thread + MP worker)."""
    if image is None:
        raise ValueError("image cannot be None")

    cam_id = det_info.source_id if hasattr(det_info, "source_id") else None
    objects = det_info.detections if hasattr(det_info, "detections") else None
    if objects is None and isinstance(det_info, dict):
        cam_id = det_info.get("source_id", cam_id)
        objects = det_info.get("detections", [])
    if objects is None:
        objects = []

    if len(objects) == 0:
        boxes_array = np.empty((0, 6), dtype=np.float32)
        orig_shape = (image.shape[1], image.shape[0])
        return cam_id, Boxes(boxes_array, orig_shape)

    num_objects = len(objects)
    bboxes_xyxy = np.empty((num_objects, 4), dtype=np.float32)
    confidences = np.empty((num_objects, 1), dtype=np.float32)
    class_ids = np.empty((num_objects, 1), dtype=np.float32)

    for i, obj in enumerate(objects):
        if isinstance(obj, dict):
            bbox = obj.get("bounding_box", obj.get("bbox_xyxy", [0, 0, 0, 0]))
            conf = obj.get("confidence", 0.0)
            cls_id = obj.get("class_id", -1)
        else:
            bbox = obj.bounding_box
            conf = obj.confidence
            cls_id = obj.class_id
        bboxes_xyxy[i] = bbox
        confidences[i] = conf
        class_ids[i] = cls_id

    boxes_array = np.concatenate([bboxes_xyxy, confidences, class_ids], axis=1)
    orig_shape = (image.shape[1], image.shape[0])
    return cam_id, Boxes(boxes_array, orig_shape)


def run_tracker_update(tracker, det_info: DetectionResultList, image_np: np.ndarray) -> TrackingResultList:
    """Run BoT-SORT update and build TrackingResultList."""
    cam_id, boxes = parse_detections_to_boxes(det_info, image_np)
    tracks = tracker.update(boxes, image_np)

    tracks_info = TrackingResultList()
    tracks_info.source_id = cam_id
    tracks_info.frame_id = det_info.frame_id if hasattr(det_info, "frame_id") else None
    tracks_info.time_stamp = datetime.datetime.now()

    if len(tracks) > 0:
        tracks_results = np.asarray([x.result for x in tracks], dtype=np.float32)
        for i in range(len(tracks_results)):
            obj = TrackingResult()
            obj.class_id = int(tracks_results[i, 6])
            obj.bounding_box = tracks_results[i, :4].tolist()
            obj.confidence = float(tracks_results[i, 5])
            obj.track_id = int(tracks_results[i, 4])
            obj.tracking_data = {"track_object": tracks[i]}
            tracks_info.tracks.append(obj)
    return tracks_info
