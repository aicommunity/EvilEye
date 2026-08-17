from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from evileye.core.frame import CaptureImage
from evileye.visualization_modules.preview_render import (
    PreviewRenderContext,
    render_preview_frame,
    serialize_preview_metadata,
)


def _make_frame() -> CaptureImage:
    frame = CaptureImage()
    frame.source_id = 0
    frame.frame_id = 1
    frame.image = np.zeros((120, 160, 3), dtype=np.uint8)
    return frame


def _make_obj():
    return SimpleNamespace(
        object_id=42,
        global_id=None,
        frame_id=1,
        history=[],
        attributes={},
        track=SimpleNamespace(
            bounding_box=[20, 20, 80, 80],
            track_id=42,
            confidence=0.99,
            class_id=0,
        ),
    )


def test_burn_in_overlay_false_skips_boxes_on_jpeg_but_keeps_metadata():
    frame = _make_frame()
    obj = _make_obj()
    context = PreviewRenderContext(
        source_name="Cam0",
        track_info=[obj],
        show_boxes=True,
        burn_in_overlay=False,
        event_signal_enabled=False,
    )

    rendered = render_preview_frame(frame, context)
    meta = serialize_preview_metadata(context, rendered.image.shape)

    assert np.count_nonzero(rendered.image) == 0
    assert len(meta["objects"]) == 1


def test_burn_in_overlay_true_draws_boxes_on_jpeg():
    frame = _make_frame()
    obj = _make_obj()
    context = PreviewRenderContext(
        source_name="Cam0",
        track_info=[obj],
        show_boxes=True,
        burn_in_overlay=True,
        event_signal_enabled=False,
    )

    rendered = render_preview_frame(frame, context)

    assert np.count_nonzero(rendered.image) > 0
