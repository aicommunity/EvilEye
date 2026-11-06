"""Inject one missing PTS into the real recorder branch on an isolated test pattern."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--unguarded', action='store_true')
    args = parser.parse_args()
    import gi
    gi.require_version('Gst', '1.0')
    from gi.repository import Gst
    from evileye.video_recorder.continuous_recorder_gst import GstContinuousRecorder
    from evileye.video_recorder.recording_params import RecordingParams
    from evileye.video_recorder.recorder_base import SourceMeta
    Gst.init(None)
    work = Path(tempfile.mkdtemp(prefix='evileye-pts-check-'))
    pipeline = Gst.parse_launch('videotestsrc is-live=true num-buffers=75 ! '
        'video/x-raw,width=320,height=240,framerate=15/1 ! tee name=t '
        't. ! queue ! fakesink sync=false t. ! queue name=recording_queue')
    recorder = GstContinuousRecorder()
    if args.unguarded:
        recorder._attach_timestamp_guard = lambda *args: None
    params = RecordingParams.from_config(dict(enabled=True, continuous_recording_enabled=True,
        out_dir=str(work), min_file_size_kb=0, validate_video_integrity=False, segment_length_sec=30))
    recorder.start(SourceMeta('Test', None, 'test', fps=15), params)
    recorder.start_with_pipeline(pipeline=pipeline,
        recording_queue_elem=pipeline.get_by_name('recording_queue'), Gst=Gst)
    observed = {'encoded': 0, 'captured': 0}
    def inject(pad, info):
        observed['encoded'] += 1
        if observed['encoded'] == 15:
            info.get_buffer().pts = Gst.CLOCK_TIME_NONE
        return Gst.PadProbeReturn.OK
    def capture(pad, info):
        observed['captured'] += 1
        return Gst.PadProbeReturn.OK
    recorder._refs.queue_before_mux.get_static_pad('sink').add_probe(Gst.PadProbeType.BUFFER, inject)
    pipeline.get_by_name('t').get_static_pad('sink').add_probe(Gst.PadProbeType.BUFFER, capture)
    pipeline.set_state(Gst.State.PLAYING)
    try:
        message = pipeline.get_bus().timed_pop_filtered(15*Gst.SECOND, Gst.MessageType.EOS | Gst.MessageType.ERROR)
        error = message.parse_error()[0].message if message and message.type == Gst.MessageType.ERROR else None
    finally:
        recorder.stop_with_pipeline(pipeline=pipeline, Gst=Gst)
        pipeline.set_state(Gst.State.NULL)
    outputs = list(work.rglob('*.mp4'))
    playable = []
    for path in outputs:
        result = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
            '-count_frames', '-show_entries', 'stream=nb_read_frames', '-of', 'csv=p=0', str(path)],
            capture_output=True, text=True)
        if result.returncode == 0 and result.stdout.strip():
            playable.append(int(result.stdout.strip()))
    print(json.dumps(dict(unguarded=args.unguarded, error=error, observed=observed,
                          dropped_pts=getattr(recorder, 'invalid_pts_dropped', 0),
                          playable_frames=playable, output=str(work))))
    if args.unguarded:
        assert error and 'multiplex' in error.lower(), 'missing PTS failure did not reproduce'
    else:
        assert error is None and observed['captured'] == 75
        assert recorder.invalid_pts_dropped == 1 and playable and sum(playable) >= 70


if __name__ == '__main__':
    main()
