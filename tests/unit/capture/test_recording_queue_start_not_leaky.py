from pathlib import Path


def test_recording_queue_starts_without_leaky_drop():
    src = (
        Path(__file__).resolve().parents[3]
        / "evileye"
        / "capture"
        / "gstreamer_capture_pipeline.py"
    ).read_text(encoding="utf-8")
    assert "queue name=recording_queue" in src
    assert "leaky=no" in src
    assert "leaky=downstream" not in src
