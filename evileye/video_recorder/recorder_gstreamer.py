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
        # Create daily subfolder YYYY-MM-DD inside out_dir, then camera name subfolder
        date_dir = start_time.strftime("%Y-%m-%d")
        
        # Get camera folder name from source metadata
        # Compose from all source_names or source_ids (for split sources)
        if self.source and self.source.source_names and len(self.source.source_names) > 0:
            camera_folder = "-".join(self.source.source_names)
        elif self.source and self.source.source_ids and len(self.source.source_ids) > 0:
            camera_folder = "-".join(str(sid) for sid in self.source.source_ids)
        elif self.source:
            camera_folder = self.source.source_name
        else:
            camera_folder = "source"
        
        # Create path: out_dir/YYYY-MM-DD/CameraName/
        base_out_dir = Path(self.params.out_dir) if self.params.out_dir else Path(".")
        out_dir = base_out_dir / date_dir / camera_folder
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
            self.logger.info(f"Recording directory created/verified: {out_dir}")
        except Exception as e:
            self.logger.error(f"Failed to create recording directory {out_dir}: {e}")
            raise
        ts = start_time.strftime("%Y%m%d_%H%M%S")
        name = self.params.filename_tmpl.format(
            source_name=self.source.source_name if self.source else "source",
            start_time=ts,
            seq=seq,
            ext=self.params.container,
        )
        stem = (out_dir / name).with_suffix("")
        location = str(stem) + "_%05d." + self.params.container
        self.logger.info(f"Recording location pattern: {location}")
        return location

    def _build_rtsp_branch(self) -> str:
        # Use uridecodebin which handles RTSP better and automatically connects pads
        # Then re-encode to H264 for MP4 compatibility
        mux_factory = "mp4mux" if self.params.container.lower() == "mp4" else "matroskamux"
        location = self._next_location(_dt.datetime.now(), 0)
        
        # Build RTSP URI with authentication if provided
        rtsp_uri = self.source.source_address
        if self.source.username and self.source.password:
            # Insert credentials into URI if not already present
            if "@" not in rtsp_uri.split("://")[1]:
                protocol = rtsp_uri.split("://")[0]
                rest = rtsp_uri.split("://")[1]
                rtsp_uri = f"{protocol}://{self.source.username}:{self.source.password}@{rest}"
        
        # Use uridecodebin which handles RTSP authentication and decoding better
        # Note: uridecodebin automatically handles H264/H265 and connects pads correctly
        # uridecodebin doesn't support latency property, so we skip it
        branch = (
            f"uridecodebin uri=\"{rtsp_uri}\" ! "
            "videoconvert ! x264enc tune=zerolatency speed-preset=ultrafast bitrate=2000 ! h264parse ! queue ! "
            f"splitmuxsink max-size-time={self.params.segment_length_sec * 1000000000} "
            f"location=\"{location}\" muxer-factory={mux_factory} async-finalize=true"
        )
        return branch

    def _build_file_branch(self) -> str:
        mux_factory = "mp4mux" if self.params.container.lower() == "mp4" else "matroskamux"
        location = self._next_location(_dt.datetime.now(), 0)
        src = str(self.source.source_address)
        # Note: muxer-properties cannot be set via parse_launch string, so we skip faststart
        if src.lower().endswith('.mp4') and self.params.container.lower() == 'mp4':
            # Remux mp4 h264 stream without re-encoding (best-effort)
            branch = (
                f"filesrc location=\"{src}\" ! qtdemux name=demux demux.video_0 ! h264parse ! queue ! video/x-h264,stream-format=avc,alignment=au ! "
                f"splitmuxsink max-size-time={self.params.segment_length_sec * 1000000000} "
                f"location=\"{location}\" muxer-factory={mux_factory} async-finalize=true"
            )
        else:
            # Fallback: decode and re-encode to h264
            branch = (
                f"filesrc location=\"{src}\" ! decodebin name=dec ! queue ! "
                "x264enc tune=zerolatency byte-stream=true speed-preset=ultrafast ! h264parse ! queue ! video/x-h264,stream-format=avc,alignment=au ! "
                f"splitmuxsink max-size-time={self.params.segment_length_sec * 1000000000} "
                f"location=\"{location}\" muxer-factory={mux_factory} async-finalize=true"
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

    def _on_bus_message(self, bus, message):
        """Handle GStreamer bus messages for recording pipeline."""
        try:
            msg_type = message.type
            if msg_type == Gst.MessageType.ERROR:
                err, debug = message.parse_error()
                self.logger.error(f"GStreamer recording ERROR: {err}, debug: {debug}")
                self.is_running = False
            elif msg_type == Gst.MessageType.EOS:
                self.logger.info("GStreamer recording EOS received")
                self.is_running = False
            elif msg_type == Gst.MessageType.WARNING:
                warn, debug = message.parse_warning()
                self.logger.warning(f"GStreamer recording WARNING: {warn}, debug: {debug}")
            elif msg_type == Gst.MessageType.STATE_CHANGED:
                if message.src == self._pipeline:
                    old_state, new_state, pending_state = message.parse_state_changed()
                    self.logger.debug(f"Recording pipeline state: {old_state.value_nick} -> {new_state.value_nick}")
        except Exception as e:
            self.logger.error(f"Error handling recording bus message: {e}")

    def start(self, source_meta: SourceMeta, params: RecordingParams) -> None:
        if not _GST_OK:
            raise RuntimeError("GStreamer not available")
        self.source = source_meta
        self.params = params
        pipeline_desc = self._build_pipeline()
        self.logger.info(f"Starting GStreamer recording pipeline: {pipeline_desc}")
        self._pipeline = Gst.parse_launch(pipeline_desc)
        if not self._pipeline:
            raise RuntimeError("Failed to create GStreamer recording pipeline")
        
        # Setup bus to handle errors
        bus = self._pipeline.get_bus()
        if bus:
            bus.add_signal_watch()
            bus.connect("message", self._on_bus_message)
        
        # Set state to playing
        ret = self._pipeline.set_state(Gst.State.PLAYING)
        if ret == Gst.StateChangeReturn.FAILURE:
            self.logger.error("Failed to start GStreamer recording pipeline")
            raise RuntimeError("Failed to start recording pipeline")
        elif ret == Gst.StateChangeReturn.ASYNC:
            # Wait for state change
            ret = self._pipeline.get_state(Gst.CLOCK_TIME_NONE)
            if ret[0] == Gst.StateChangeReturn.FAILURE:
                self.logger.error("Failed to start GStreamer recording pipeline (async)")
                raise RuntimeError("Failed to start recording pipeline")
        
        self.is_running = True
        self.logger.info(f"Recording pipeline started successfully for {source_meta.source_name}")

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


