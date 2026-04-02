from __future__ import annotations

import numpy as np

from evileye.core.frame import CaptureImage
from evileye.controller.services.streaming_service import StreamingService
from evileye.events_control.events_controller import EventsDetectorsController


def _make_frame() -> CaptureImage:
    frame = CaptureImage()
    frame.source_id = 1
    frame.frame_id = 10
    frame.image = np.zeros((32, 32, 3), dtype=np.uint8)
    return frame


def test_streaming_service_uses_owned_images_without_copy():
    service = StreamingService()
    service.configure(pipeline_id="p1", publish_fps=0, num_workers=1)
    service._should_publish = lambda _key: True  # type: ignore[method-assign]
    try:
        frame = _make_frame()
        frame._streaming_image_owned = True
        accepted = service.submit_frame(frame)
        assert accepted is True
        stats = service.get_runtime_stats()
        assert stats["used_owned_images"] == 1
        assert stats["copied_images"] == 0
    finally:
        service.stop()


def test_events_controller_queue_is_bounded():
    class DummyDetector:
        def __init__(self, idx: int):
            self.idx = idx

        def get_name(self):
            return f"d{self.idx}"

        def get(self):
            return [{"event_id": self.idx}]

    controller = EventsDetectorsController([DummyDetector(1)])
    controller.init_impl()
    for _ in range(controller.queue_out_maxsize + 5):
        controller._publish_events_snapshot()
    stats = controller.get_runtime_stats()
    assert stats["queue_size"] == controller.queue_out_maxsize
    assert stats["queue_drops"] > 0
