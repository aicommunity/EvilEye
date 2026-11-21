"""Streaming metadata must forward debug_rois to live overlay consumers."""

from evileye.controller.services import streaming_service
from evileye.controller.services.streaming_service import StreamFrameJob, StreamingService


def test_publish_jpeg_forwards_debug_rois(monkeypatch):
    service = StreamingService()
    job = StreamFrameJob(
        pipeline_id="7",
        image=None,
        source_id=2,
        frame_id=1,
        created_at=1.0,
        objects=[],
        zones=[],
        signalization=False,
        metadata={
            "debug_rois": [[0.0, 0.0, 0.5, 0.5]],
            "event_color": [255, 0, 0],
            "event_labels": ["test"],
            "overlay": {"source_name": "Cam3"},
        },
    )
    published: dict = {}

    class _Broker:
        def publish_jpeg(self, pipeline_id, jpeg_bytes, metadata=None):
            published["pipeline_id"] = pipeline_id
            published["metadata"] = dict(metadata or {})

    monkeypatch.setattr(streaming_service, "get_frame_broker", lambda: _Broker())
    service._publish_jpeg("7:2", b"jpeg", job)

    meta = published["metadata"]
    assert meta["debug_rois"] == [[0.0, 0.0, 0.5, 0.5]]
    assert meta["event_color"] == [255, 0, 0]
    assert meta["event_labels"] == ["test"]
    assert meta["overlay"] == {"source_name": "Cam3"}
