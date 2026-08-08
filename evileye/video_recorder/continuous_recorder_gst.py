from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List
import datetime as _dt
import threading
import time
import weakref
import atexit

from evileye.core.logger import get_module_logger
from evileye.video_recorder.recording_params import RecordingParams
from evileye.video_recorder.recorder_base import VideoRecorderBase, SourceMeta


@dataclass
class GstBranchRefs:
    """References to elements created by GstContinuousRecorder."""

    recording_queue: object
    videoconvert: object
    capsfilter: object
    x264enc: object
    h264parse: object
    queue_before_mux: object
    splitmuxsink: object


class GstContinuousRecorder(VideoRecorderBase):
    """

    _instances: "weakref.WeakSet[GstContinuousRecorder]" = weakref.WeakSet()
    Continuous-запись для GStreamer backend.

    Важно: этот класс управляет только веткой записи (от `recording_queue` до splitmuxsink)
    и не владеет главным пайплайном захвата.
    """

    def __init__(self) -> None:
        super().__init__()
        self.logger = get_module_logger("gst_continuous_recorder")
        self._refs: Optional[GstBranchRefs] = None
        self._check_thread: Optional[threading.Thread] = None
        self._check_stop = threading.Event()
        self._recording_out_dir: Optional[Path] = None
        self._recording_checked_files: set[Path] = set()
        self._recording_min_file_size_kb: int = 0
        self._recording_container: str = "mp4"
        self._lock = threading.RLock()
        self._segments_attached: int = 0
        self._last_stats_ts: float = 0.0
        try:
            GstContinuousRecorder._instances.add(self)
        except Exception:
            pass

    @classmethod
    def shutdown_all(cls) -> None:
        """Best-effort stop of background check threads (used in tests/atexit)."""
        try:
            items = list(cls._instances)
        except Exception:
            return
        for r in items:
            try:
                r.is_running = False
                r._check_stop.set()
                t = getattr(r, "_check_thread", None)
                if t is not None and t.is_alive():
                    try:
                        t.join(timeout=2.0)
                    except Exception:
                        pass
            except Exception:
                pass

    def start(self, source_meta: SourceMeta, params: RecordingParams) -> None:
        # This start() is for API compatibility; actual wiring requires pipeline.
        self.source = source_meta
        self.params = params
        self.is_running = bool(params.enabled and params.continuous_recording_enabled)

    def start_with_pipeline(self, *, pipeline, recording_queue_elem, Gst) -> None:
        """
        Attach recording branch to an existing pipeline.
        `recording_queue_elem` is expected to exist in the base pipeline.
        """
        if not self.is_running:
            return
        with self._lock:
            if self._refs is not None:
                self.stop_with_pipeline(pipeline=pipeline, Gst=Gst)

            # Create elements
            videoconvert = Gst.ElementFactory.make("videoconvert", "recording_videoconvert")
            # Force I420 so x264enc emits browser-playable High/Main (not High 4:4:4).
            capsfilter = Gst.ElementFactory.make("capsfilter", "recording_i420_caps")
            x264enc = Gst.ElementFactory.make("x264enc", "recording_x264enc")
            h264parse = Gst.ElementFactory.make("h264parse", "recording_h264parse")
            queue_before_mux = Gst.ElementFactory.make("queue", "recording_queue_before_mux")
            splitmuxsink = Gst.ElementFactory.make("splitmuxsink", "recording_splitmuxsink")
            if not (videoconvert and capsfilter and x264enc and h264parse and queue_before_mux and splitmuxsink):
                raise RuntimeError("Failed to create one or more recording elements")

            capsfilter.set_property("caps", Gst.Caps.from_string("video/x-raw,format=I420"))
            x264enc.set_property("tune", "zerolatency")
            x264enc.set_property("speed-preset", "ultrafast")
            x264enc.set_property("bitrate", 2000)
            try:
                # Explicit profile for HTML5 <video> compatibility (Chrome/Firefox).
                x264enc.set_property("profile", "high")
            except Exception:
                pass

            # IMPORTANT: bound mux queue to avoid runaway RSS if mux/disk stalls.
            try:
                queue_before_mux.set_property("max-size-buffers", 200)
                queue_before_mux.set_property("max-size-bytes", 5 * 1024 * 1024)
                queue_before_mux.set_property("max-size-time", 2_000_000_000)
                queue_before_mux.set_property("leaky", 2)  # downstream
            except Exception:
                pass

            splitmuxsink.set_property("max-size-time", self.params.segment_length_sec * 1_000_000_000)
            splitmuxsink.set_property(
                "muxer-factory",
                "mp4mux" if self.params.container.lower() == "mp4" else "matroskamux",
            )
            splitmuxsink.set_property("async-finalize", True)

            # Build output path: base/Streams/YYYY-MM-DD/CameraName/
            camera_folder = (
                "-".join(self.source.source_names)
                if self.source and self.source.source_names
                else (self.source.source_name if self.source else "source")
            )
            base_dir = Path(self.params.out_dir) if self.params.out_dir else Path("EvilEyeData")
            date_dir = _dt.datetime.now().strftime("%Y-%m-%d")
            out_dir = base_dir / "Streams" / date_dir / camera_folder
            out_dir.mkdir(parents=True, exist_ok=True)

            ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            source_name = self.source.source_name if self.source else camera_folder
            name = self.params.filename_tmpl.format(
                source_name=source_name,
                start_time=ts,
                seq=0,
                ext=self.params.container,
            )
            stem = (out_dir / name).with_suffix("")
            location = str(stem) + "_%05d." + self.params.container
            splitmuxsink.set_property("location", location)

            self._recording_out_dir = out_dir
            self._recording_min_file_size_kb = self.params.min_file_size_kb
            self._recording_container = self.params.container
            self._recording_checked_files = set()

            # Add to pipeline and link
            pipeline.add(videoconvert)
            pipeline.add(capsfilter)
            pipeline.add(x264enc)
            pipeline.add(h264parse)
            pipeline.add(queue_before_mux)
            pipeline.add(splitmuxsink)

            if not recording_queue_elem.link(videoconvert):
                raise RuntimeError("Failed to link recording_queue -> videoconvert")
            if not videoconvert.link(capsfilter):
                raise RuntimeError("Failed to link videoconvert -> capsfilter(I420)")
            if not capsfilter.link(x264enc):
                raise RuntimeError("Failed to link capsfilter -> x264enc")
            if not x264enc.link(h264parse):
                raise RuntimeError("Failed to link x264enc -> h264parse")
            if not h264parse.link(queue_before_mux):
                raise RuntimeError("Failed to link h264parse -> queue_before_mux")
            if not queue_before_mux.link(splitmuxsink):
                raise RuntimeError("Failed to link queue_before_mux -> splitmuxsink")

            # Sync state if safe
            try:
                ret, current_state, _pending = pipeline.get_state(Gst.SECOND)
                if ret != Gst.StateChangeReturn.FAILURE and current_state in (Gst.State.NULL, Gst.State.READY):
                    for elem in (videoconvert, capsfilter, x264enc, h264parse, queue_before_mux, splitmuxsink):
                        elem.sync_state_with_parent()
            except Exception:
                pass

            self._refs = GstBranchRefs(
                recording_queue=recording_queue_elem,
                videoconvert=videoconvert,
                capsfilter=capsfilter,
                x264enc=x264enc,
                h264parse=h264parse,
                queue_before_mux=queue_before_mux,
                splitmuxsink=splitmuxsink,
            )

            self._start_check_thread()
            self._segments_attached += 1
            self._last_stats_ts = time.time()
            self.logger.info("GstContinuousRecorder branch attached: location=%s", location)

    def _start_check_thread(self) -> None:
        # Best-effort small/invalid file cleanup, similar to previous in-capture implementation.
        if self._check_thread and self._check_thread.is_alive():
            return
        self._check_stop.clear()

        def _worker():
            # Use Event.wait() so stop() can wake the thread quickly.
            while True:
                if self._check_stop.is_set():
                    break
                try:
                    try:
                        now = time.time()
                        if self._refs is not None and (now - self._last_stats_ts) >= 5.0:
                            self._last_stats_ts = now
                            lvl = None
                            try:
                                lvl = self._refs.recording_queue.get_property("current-level-buffers")
                            except Exception:
                                lvl = None
                            self.logger.debug(
                                "GstContinuousRecorder stats: src=%s segments_attached=%s record_queue_buf=%s",
                                self.source.source_name if self.source else "source",
                                self._segments_attached,
                                lvl if lvl is not None else "n/a",
                            )
                    except Exception:
                        pass

                    out_dir = self._recording_out_dir
                    if not out_dir or not out_dir.exists():
                        if self._check_stop.wait(timeout=5.0):
                            break
                        continue
                    from evileye.video_recorder.utils import check_and_delete_small_files

                    validate_integrity = getattr(self.params, "validate_video_integrity", True)
                    validation_timeout = getattr(self.params, "video_validation_timeout", 2.0)

                    for fp in out_dir.glob(f"*.{self._recording_container}"):
                        if fp in self._recording_checked_files:
                            continue
                        check_and_delete_small_files(
                            fp,
                            self._recording_min_file_size_kb,
                            validate_integrity=validate_integrity,
                            validation_timeout=validation_timeout,
                        )
                        try:
                            stat = fp.stat()
                            if (time.time() - stat.st_mtime) >= 60.0:
                                self._recording_checked_files.add(fp)
                        except Exception:
                            pass
                except Exception:
                    pass
                if self._check_stop.wait(timeout=5.0):
                    break

        tname = f"GstRecorderFileCheck-{self.source.source_name if self.source else 'source'}"
        self._check_thread = threading.Thread(target=_worker, name=tname, daemon=True)
        self._check_thread.start()

    def on_frame(self, frame) -> None:
        # GStreamer branch records internally; no Python-frame feed required.
        return

    def rotate_segment(self) -> None:
        # splitmuxsink rotates based on max-size-time.
        return

    def stop_with_pipeline(self, *, pipeline, Gst) -> None:
        with self._lock:
            self._check_stop.set()
            t = self._check_thread
            self._check_thread = None
            refs = self._refs
            self._refs = None
            self._recording_out_dir = None
            self._recording_checked_files = set()

        if t and t.is_alive():
            try:
                t.join(timeout=6.0)
            except Exception:
                pass

        if not refs:
            return

        for elem in [
            refs.videoconvert,
            refs.capsfilter,
            refs.x264enc,
            refs.h264parse,
            refs.queue_before_mux,
            refs.splitmuxsink,
        ]:
            try:
                elem.set_state(Gst.State.NULL)
            except Exception:
                pass
            try:
                if pipeline and elem.get_parent() == pipeline:
                    pipeline.remove(elem)
            except Exception:
                pass

    def stop(self) -> None:
        # Need pipeline+Gst to remove elements; caller should use stop_with_pipeline.
        self.is_running = False


try:
    atexit.register(GstContinuousRecorder.shutdown_all)
except Exception:
    pass
