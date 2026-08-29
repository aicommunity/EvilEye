from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from evileye.core.frame import CaptureImage
from evileye.visualization_modules.preview_render import PreviewRenderContext, serialize_preview_metadata


def _make_frame() -> CaptureImage:
    frame = CaptureImage()
    frame.source_id = 0
    frame.frame_id = 10
    frame.current_video_position = 2500
    frame.image = np.zeros((100, 200, 3), dtype=np.uint8)
    return frame


def _make_object() -> SimpleNamespace:
    hist = []
    for fid, x1 in [(8, 20), (9, 30), (10, 40)]:
        hist.append(
            SimpleNamespace(
                frame_id=fid,
                track=SimpleNamespace(
                    bounding_box=[x1, 20, x1 + 20, 60],
                    track_id=77,
                    confidence=0.9,
                    class_id=0,
                ),
            )
        )
    return SimpleNamespace(
        object_id=42,
        global_id=314,
        frame_id=10,
        history=hist,
        attributes={
            "helmet": {
                "state": "exists",
                "confidence_smooth": 0.93,
                "frames_present": 3,
                "total_time_ms": 500,
                "found_ratio": 0.8,
            }
        },
        track=hist[-1].track,
    )


def test_serialize_preview_metadata_extended_fields():
    frame = _make_frame()
    obj = _make_object()
    ctx = PreviewRenderContext(
        source_name="Cam0",
        source_duration_msecs=6000,
        track_info=[obj],
        show_boxes=True,
        show_zones=True,
        zones=[["poly", [[0.1, 0.1], [0.3, 0.1], [0.2, 0.4]], None]],
        class_mapping={"person": 0},
        event_signal_enabled=True,
        event_color_rgb=(255, 0, 0),
        event_active_obj_ids={42},
        active_event_labels=["ZoneEvent [42]"],
        show_debug_info=True,
        debug_info={"detectors": {"det0": {"source_ids": [0], "roi": [[[10, 10, 20, 20]]]}}},
    )

    meta = serialize_preview_metadata(ctx, frame.image.shape, frame_id=frame.frame_id, frame=frame)
    first = meta["objects"][0]

    assert first["object_id"] == 42
    assert first["global_id"] == 314
    assert first["event_active"] is True
    assert first["class_name"] == "person"
    assert len(first["trail"]) >= 2
    assert first["attributes"][0]["name"] == "helmet"
    assert meta["event_labels"] == ["ZoneEvent [42]"]
    assert meta["signalization"] is True
    assert meta["event_color"] == [255, 0, 0]
    assert len(meta["debug_rois"]) == 1
    assert meta["overlay"]["source_name"] == "Cam0"
    assert "time_label" in meta["overlay"]
