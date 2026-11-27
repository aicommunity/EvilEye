from pathlib import Path


def test_recording_queue_uses_leaky_downstream():
    """A stalled muxer must not block RTSP teardown; the queue drops downstream."""
    src = (
        Path(__file__).resolve().parents[3]
        / "evileye"
        / "capture"
        / "gstreamer_capture_pipeline.py"
    ).read_text(encoding="utf-8")
    assert "queue name=recording_queue" in src
    assert "leaky=downstream" in src
    assert "leaky=no" not in src
