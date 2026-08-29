from __future__ import annotations

import time
from types import SimpleNamespace

import numpy as np

from evileye.core.frame import CaptureImage
from evileye.controller.services.preview_render_service import PreviewRenderJob, PreviewRenderService
from evileye.visualization_modules.preview_render import PreviewRenderContext, render_preview_frame


def _make_frame(source_id: int = 0, frame_id: int = 1) -> CaptureImage:
    frame = CaptureImage()
    frame.source_id = source_id
    frame.frame_id = frame_id
    frame.current_video_position = 1000
    frame.image = np.zeros((120, 160, 3), dtype=np.uint8)
    return frame


def test_render_preview_frame_keeps_source_image_immutable():
    frame = _make_frame()
    obj = SimpleNamespace(
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
    context = PreviewRenderContext(
        source_name="Cam0",
        track_info=[obj],
        event_signal_enabled=True,
        event_active_obj_ids={42},
        active_event_labels=["AttributeEvent [42]"],
        show_debug_info=False,
    )

    rendered = render_preview_frame(frame, context)

    assert rendered is not frame
    assert np.count_nonzero(rendered.image) > 0
    assert np.count_nonzero(frame.image) == 0


def test_preview_render_service_processes_oldest_pending_job_first():
    service = PreviewRenderService()
    now = time.time()
    service._pending_jobs["src:1"] = PreviewRenderJob(
        frame=_make_frame(source_id=1),
        context=PreviewRenderContext(source_name="Cam1"),
        source_id=1,
        submitted_at=now + 0.2,
    )
    service._pending_jobs["src:2"] = PreviewRenderJob(
        frame=_make_frame(source_id=2),
        context=PreviewRenderContext(source_name="Cam2"),
        source_id=2,
        submitted_at=now,
    )
    job = service._get_next_job()
    assert job is not None
    assert job.source_id == 2


def test_preview_render_service_skips_frames_without_consumers():
    class DummyStreamingService:
        def __init__(self):
            self.submitted = []

        def has_consumers(self, source_id=None):
            return False

        def submit_frame(self, frame):
            self.submitted.append(frame)
            return True

    streaming_service = DummyStreamingService()
    service = PreviewRenderService()
    service.configure(streaming_service=streaming_service, num_workers=1)
    try:
        accepted = service.submit_frame(_make_frame(), PreviewRenderContext(source_name="Cam0"))
        time.sleep(0.1)
        assert accepted is False
        assert streaming_service.submitted == []
    finally:
        service.stop()
