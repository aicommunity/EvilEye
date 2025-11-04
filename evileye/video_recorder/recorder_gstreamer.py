from __future__ import annotations

import datetime as _dt
import threading
from pathlib import Path
from typing import Optional

from evileye.core.logger import get_module_logger
from evileye.video_recorder.recording_params import RecordingParams
from evileye.video_recorder.recorder_base import VideoRecorderBase, SourceMeta

try:
    import gi  # type: ignore
    gi.require_version('Gst', '1.0')
    from gi.repository import Gst, GLib  # type: ignore
    _GST_OK = True
except Exception:  # pragma: no cover - environment dependent
    Gst = None
    GLib = None
    _GST_OK = False


class GStreamerRecorder(VideoRecorderBase):
    def __init__(self) -> None:
        super().__init__()
        self.logger = get_module_logger("recorder_gst")
        self._pipeline = None
        self._loop: Optional[GLib.MainLoop] = None
        self._thread: Optional[threading.Thread] = None

        if _GST_OK and not Gst.is_initialized():
            Gst.init(None)

    def _next_location(self, start_time: _dt.datetime, seq: int) -> str:
        # Create daily subfolder YYYY-MM-DD inside out_dir
        date_dir = start_time.strftime("%Y-%m-%d")
        out_dir = Path(self.params.out_dir) / date_dir if self.params.out_dir else Path(".") / date_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = start_time.strftime("%Y%m%d_%H%M%S")
        name = self.params.filename_tmpl.format(
            source_name=self.source.source_name if self.source else "source",
            start_time=ts,
            seq=seq,
            ext=self.params.container,
        )
        stem = (out_dir / name).with_suffix("")
        return str(stem) + "_%05d." + self.params.container

    def _build_rtsp_branch(self) -> str:
        # Choose codec depay/parse elements; prefer h264; allow h265 fallback
        # This branch keeps encoded bitstream and remuxes only.
        # Note: many IP cams are h264; for h265 use h265 elements.
        # Using splitmuxsink with muxer-factory and muxer-properties.
        mux_factory = "mp4mux" if self.params.container.lower() == "mp4" else "matroskamux"
        mux_props = "faststart=true" if mux_factory == "mp4mux" else ""
        # Let splitmuxsink handle segmentation by time
        location = self._next_location(_dt.datetime.now(), 0)
        # location is template; splitmuxsink will append increment if pattern contains %
        # we will provide numeric-increment style with splitmuxsink's "location"
        # Use key-unit interval by default
        muxer_props_str = f" muxer-properties=\"{mux_props}\"" if mux_props else ""
        branch = (
            f"rtspsrc location=\"{self.source.source_address}\" latency=200 ! rtpjitterbuffer ! "
            "rtph264depay ! h264parse config-interval=1 ! queue ! video/x-h264,stream-format=avc,alignment=au ! "
            f"splitmuxsink max-size-time={self.params.segment_length_sec * 1000000000} "
            f"location=\"{location}\" muxer-factory={mux_factory}{muxer_props_str} async-finalize=true"
        )
        return branch

    def _build_file_branch(self) -> str:
        mux_factory = "mp4mux" if self.params.container.lower() == "mp4" else "matroskamux"
        mux_props = "faststart=true" if mux_factory == "mp4mux" else ""
        location = self._next_location(_dt.datetime.now(), 0)
        src = str(self.source.source_address)
        muxer_props_str = f" muxer-properties=\"{mux_props}\"" if mux_props else ""
        if src.lower().endswith('.mp4') and self.params.container.lower() == 'mp4':
            # Remux mp4 h264 stream without re-encoding (best-effort)
            branch = (
                f"filesrc location=\"{src}\" ! qtdemux name=demux demux.video_0 ! h264parse ! queue ! video/x-h264,stream-format=avc,alignment=au ! "
                f"splitmuxsink max-size-time={self.params.segment_length_sec * 1000000000} "
                f"location=\"{location}\" muxer-factory={mux_factory}{muxer_props_str} async-finalize=true"
            )
        else:
            # Fallback: decode and re-encode to h264
            branch = (
                f"filesrc location=\"{src}\" ! decodebin name=dec ! queue ! "
                "x264enc tune=zerolatency byte-stream=true speed-preset=ultrafast ! h264parse ! queue ! video/x-h264,stream-format=avc,alignment=au ! "
                f"splitmuxsink max-size-time={self.params.segment_length_sec * 1000000000} "
                f"location=\"{location}\" muxer-factory={mux_factory}{muxer_props_str} async-finalize=true"
            )
        return branch

    def _build_pipeline(self) -> str:
        if not self.source or not self.source.source_address:
            raise ValueError("SourceMeta with source_address is required for GStreamerRecorder")
        # For IP camera prefer copy (remux). For local files we may re-encode if needed.
        if self.source.source_type and self.source.source_type.lower() in ("ipcamera", "ip", "rtsp"):
            return self._build_rtsp_branch()
        else:
            return self._build_file_branch()

    def start(self, source_meta: SourceMeta, params: RecordingParams) -> None:
        if not _GST_OK:
            raise RuntimeError("GStreamer not available")
        self.source = source_meta
        self.params = params
        pipeline_desc = self._build_pipeline()
        self.logger.info(f"Starting GStreamer recording pipeline: {pipeline_desc}")
        self._pipeline = Gst.parse_launch(pipeline_desc)
        # Avoid running a separate GLib main loop to prevent conflicts with Qt main loop
        # GStreamer internal threads will handle streaming; we just set state
        self._pipeline.set_state(Gst.State.PLAYING)
        self.is_running = True

    def rotate_segment(self) -> None:
        # splitmuxsink can be told to split by sending a force-key-unit or property tweak,
        # but we rely on time-based rotation; explicit rotate is optional.
        pass

    def stop(self) -> None:
        if not self.is_running:
            return
        try:
            if self._pipeline is not None:
                self._pipeline.set_state(Gst.State.NULL)
        finally:
            self._loop = None
            self._thread = None
            self._pipeline = None
            self.is_running = False


