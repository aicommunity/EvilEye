"""P0: pipeline mixin must catch _RecordingFilesystemError without NameError."""

from evileye.capture.gstreamer_capture_pipeline import _RecordingFilesystemError
from evileye.capture.gstreamer_capture_recording import (
    _RecordingFilesystemError as RecordingFsError,
)


def test_pipeline_mixin_imports_recording_filesystem_error():
    assert _RecordingFilesystemError is RecordingFsError
    err = _RecordingFilesystemError("out_dir not writable")
    try:
        raise err
    except _RecordingFilesystemError as caught:
        assert "not writable" in str(caught)
