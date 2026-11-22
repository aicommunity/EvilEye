import os
import time
from pathlib import Path

import pytest
import numpy as np
from queue import Empty

from evileye.capture.queue_utils import DropOldestQueue
from evileye.video_recorder.file_validator import FileValidator
from evileye.video_recorder.path_generator import PathGenerator
from evileye.video_recorder.recording_params import RecordingParams
from evileye.video_recorder.recorder_base import SourceMeta
from evileye.video_recorder.recorder_opencv import OpenCVRecorder


def test_drop_oldest_queue_drops_and_reports():
    q = DropOldestQueue(maxsize=2)
    assert q.put(1) is False
    assert q.put(2) is False
    dropped = q.put(3)
    assert dropped is True
    assert q.qsize() == 2
    # Oldest (1) should be gone; remaining should be 2 and 3
    first = q.get()
    second = q.get()
    assert {first, second} == {2, 3}


def test_drop_oldest_queue_raises_empty_when_queue_is_empty():
    q = DropOldestQueue(maxsize=2)

    with pytest.raises(Empty):
        q.get_nowait()


def test_path_generator_creates_expected_structure(tmp_path: Path):
    params = RecordingParams()
    params.out_dir = str(tmp_path)
    params.filename_tmpl = "{source_name}_{start_time}_{seq}.{ext}"
    source = SourceMeta(
        source_name="CamX",
        source_address="rtsp://example",
        source_type="IpCamera",
        source_names=["CamX"],
        source_ids=[0],
    )

    path = Path(
        PathGenerator.generate_stream_path(
            source=source,
            params=params,
            segment_started_ts=1_700_000_000,  # fixed timestamp
            seq=1,
            use_pattern=False,
        )
    )
    assert path.parent.exists()
    # Filename should contain source name and sequence suffix
    assert "CamX" in path.name
    assert "_1." in path.name


def test_large_unfinalized_splitmux_fragment_is_kept(tmp_path: Path):
    fragment = tmp_path / "Cam1_20261122_205841_0_00001.mp4"
    fragment.write_bytes(b"\x00" * 4096)
    old = time.time() - 3600
    os.utime(fragment, (old, old))
    should_delete, reason = FileValidator.should_delete_file(
        fragment,
        min_size_kb=1,
        min_age_seconds=0,
        validate_integrity=True,
    )
    assert should_delete is False
    assert reason is None


def test_splitmux_with_accidental_moov_bytes_is_kept(tmp_path: Path, monkeypatch):
    """Regression: substring 'moov' in mdat made OpenCV integrity delete live parts."""
    fragment = tmp_path / "Cam4_20261123_000150_0_00000.mp4"
    # Payload contains the letters moov but not as an ISO box type at +4.
    fragment.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 8 + b"XXXX" + b"moov" + b"YYYY" + b"\x00" * (64 * 1024))
    old = time.time() - 120
    os.utime(fragment, (old, old))
    monkeypatch.setattr(
        FileValidator,
        "is_file_valid",
        staticmethod(lambda *_a, **_k: False),
    )
    should_delete, reason = FileValidator.should_delete_file(
        fragment,
        min_size_kb=1,
        min_age_seconds=30,
        validate_integrity=True,
    )
    assert should_delete is False
    assert reason is None


def test_splitmux_truncated_after_abandon_not_deleted_by_min_size(tmp_path: Path):
    """Regression for Cam4_..._000611: post-abandon 0-byte part vs min_file_size_kb=500."""
    fragment = tmp_path / "Cam4_20261123_000611_0_00000.mp4"
    fragment.write_bytes(b"")  # truncated during hung teardown
    # mtime older than default MIN_FILE_AGE (30s) but younger than stub age (300s)
    old = time.time() - 60
    os.utime(fragment, (old, old))
    should_delete, reason = FileValidator.should_delete_file(
        fragment,
        min_size_kb=500,
        min_age_seconds=30,
        validate_integrity=True,
    )
    assert should_delete is False
    assert reason is None


def test_splitmux_growing_under_min_size_is_kept(tmp_path: Path):
    """New reconnect fragment can stay <500KB for >30s while muxing starts."""
    fragment = tmp_path / "Cam4_20261123_001740_0_00000.mp4"
    fragment.write_bytes(b"\x00" * (100 * 1024))  # 100KB < 500KB min
    old = time.time() - 90
    os.utime(fragment, (old, old))
    should_delete, reason = FileValidator.should_delete_file(
        fragment,
        min_size_kb=500,
        min_age_seconds=30,
        validate_integrity=True,
    )
    assert should_delete is False
    assert reason is None


def test_splitmux_ancient_empty_stub_can_be_deleted(tmp_path: Path):
    fragment = tmp_path / "Cam4_20261123_000000_0_00099.mp4"
    fragment.write_bytes(b"")
    old = time.time() - 600
    os.utime(fragment, (old, old))
    should_delete, reason = FileValidator.should_delete_file(
        fragment,
        min_size_kb=500,
        min_age_seconds=30,
        validate_integrity=True,
    )
    assert should_delete is True
    assert reason is not None
    assert "splitmux stub" in reason


def test_file_validator_delete_small_file(tmp_path: Path):
    small_file = tmp_path / "small.mp4"
    small_file.write_bytes(b"0" * 512)  # 0.5 KB
    should_delete, reason = FileValidator.should_delete_file(
        small_file,
        min_size_kb=2,  # require at least 2 KB
        min_age_seconds=0,
        validate_integrity=False,
    )
    assert should_delete is True
    assert reason is not None


class _FakeWriter:
    def __init__(self):
        self.frames = []

    def isOpened(self):
        return True

    def write(self, frame):
        self.frames.append(frame)

    def release(self):
        return None


class _FakeFactory:
    def __init__(self, writer):
        self.writer = writer

    def create_writer(self, path, fps, frame_size, container, fallback_container=None):
        return self.writer, "FAKE", container


def test_opencv_recorder_writes_with_injected_factory(tmp_path: Path):
    writer = _FakeWriter()
    factory = _FakeFactory(writer)
    pg = PathGenerator()
    params = RecordingParams()
    params.out_dir = str(tmp_path)
    source = SourceMeta(source_name="CamX", source_address="", source_type="VideoFile", width=4, height=4, fps=10.0)

    recorder = OpenCVRecorder(path_generator=pg, writer_factory=factory)
    recorder.start(source_meta=source, params=params)
    frame = np.zeros((4, 4, 3), dtype=np.uint8)
    recorder.on_frame(frame)
    recorder.stop()

    assert writer.frames, "Frame should be written via fake writer"
