import time
from types import SimpleNamespace as S

import cv2
import numpy as np

from evileye.video_recorder.event_buffer import EventBuffer
from evileye.video_recorder.event_recorder import EventRecorder
from evileye.video_recorder.recording_params import RecordingParams
from evileye.video_recorder.recorder_base import SourceMeta
from evileye.controller.services.event_recording_service import EventRecordingService


def test_valid_short_event_clip_survives_continuous_segment_size_limit(tmp_path):
    now = time.time()
    buffer = EventBuffer(10, 5)
    for index in range(5):
        buffer.add_frame(np.zeros((240, 320, 3), dtype=np.uint8), now-1+index*.2)
    params = RecordingParams.from_config({'enabled': True, 'event_recording_enabled': True,
        'out_dir': str(tmp_path), 'min_file_size_kb': 500})
    recorder = EventRecorder(SourceMeta('Cam3', None, 'test', fps=5,
        source_names=['Cam3'], source_ids=[2]), params, buffer)
    success, _ = recorder.start_event_recording(1, 'ZoneEvent', now, 2)
    assert success
    try:
        deadline = time.monotonic()+3
        while recorder._pre_event_frames and time.monotonic() < deadline:
            time.sleep(.01)
    finally:
        path = recorder.stop_event_recording()
    assert path is not None and path.exists() and path.stat().st_size < 500*1024
    capture = cv2.VideoCapture(str(path))
    try:
        assert capture.read()[0]
    finally:
        capture.release()


def test_split_source_event_recorder_uses_its_logical_camera_name(tmp_path):
    host = S(event_buffers={}, event_recorders={})
    source = S(source_ids=[1, 2], source_names=['Cam2', 'Cam3'], source_fps=10,
               source_address='rtsp://camera', source_type='IpCamera', username=None, password=None)
    EventRecordingService().initialize_event_recording(host,
        {'record': {'enabled': True, 'event_recording_enabled': True},
         'database': {'image_dir': str(tmp_path)}}, S(get_sources=lambda: [source]))
    assert host.event_recorders[2].source.source_names == ['Cam3']
    assert host.event_recorders[2].source.source_ids == [2]
