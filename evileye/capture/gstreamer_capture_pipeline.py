"""GStreamer capture mixin — see video_capture_gstreamer.py."""

from __future__ import annotations

from .gstreamer_capture_common import (
    CaptureConstants,
    CaptureDeviceType,
    CaptureInitializationError,
    GLib,
    Gst,
    List,
    Optional,
    datetime,
    threading,
    time,
)
from .gstreamer_capture_recording import _RecordingFilesystemError


class GStreamerCapturePipelineMixin:
    def _build_pipeline(self) -> str:
        """
        Build GStreamer pipeline based on source type and parameters.
        """
        if self.source_type == CaptureDeviceType.IpCamera:
            # IP Camera pipeline - use explicit codec paths like in api-refactoring
            # Try H265 first, then H264 as fallback (handled by pipeline candidates in _init_pipeline)
            # Use UDP protocol by default, but allow TCP fallback if UDP fails (protocols=udp+tcp)
            # This allows GStreamer to try UDP first, then fallback to TCP if UDP doesn't work
            protocol = getattr(self, '_rtsp_protocol', 'udp+tcp')  # Try UDP first, then TCP if UDP fails
            if self.username and self.password:
                # Try H265 first (more common for modern cameras)
                pipeline = f"rtspsrc location={self.source_address} user-id={self.username} user-pw={self.password} protocols={protocol} ! rtph265depay ! h265parse ! avdec_h265 ! videoconvert"
            else:
                # Try H264 first (more compatible)
                pipeline = f"rtspsrc location={self.source_address} protocols={protocol} ! rtph264depay ! h264parse ! avdec_h264 ! videoconvert"

        elif self.source_type == CaptureDeviceType.VideoFile:
            # Video file pipeline - optimized with hardware acceleration support
            # Step 1: Try hardware decoder (NVDEC for NVIDIA GPUs)
            # Step 2: Fallback to explicit software decoder (faster than decodebin)
            # Step 3: Last resort: decodebin (supports all formats)

            file_ext = str(self.source_address).lower()
            is_mp4 = file_ext.endswith('.mp4')
            is_mkv = file_ext.endswith('.mkv')

            # Check for NVIDIA hardware decoder (NVDEC)
            force_sw = False
            try:
                # Allow per-instance override via params too (useful for A/B tests without env).
                p = (self.params or {})
                force_sw = bool(p.get("force_sw_decoder", False))
            except Exception:
                force_sw = False
            force_sw = bool(force_sw or self._force_sw_decoder)

            use_nvdec = (
                    (not force_sw) and
                    self._gst_has('nvh264dec') and
                    is_mp4  # NVDEC works best with MP4/H.264
            )

            # Check for Jetson hardware decoder (older API)
            use_nvv4l2 = (
                    (not force_sw) and
                    self._gst_has('nvv4l2decoder') and
                    self._gst_has('nvvidconv') and
                    is_mp4
            )

            if use_nvdec:
                # Use NVDEC hardware decoder (RTX/GTX series)
                # This is the fastest path for H.264/MP4 files on NVIDIA GPUs
                pipeline = (
                    f"filesrc location={self.source_address} ! qtdemux ! h264parse ! nvh264dec "
                    f"! videoconvert"
                )
                self.logger.info(f"Using NVDEC hardware decoder for {self.source_names}")
            elif use_nvv4l2:
                # Use Jetson hardware decoder (older API)
                pipeline = (
                    f"filesrc location={self.source_address} ! qtdemux ! h264parse ! nvv4l2decoder "
                    f"! nvvidconv ! video/x-raw(memory:NVMM),format=BGRx ! nvvidconv ! video/x-raw,format=BGRx ! videoconvert"
                )
                self.logger.info(f"Using Jetson hardware decoder for {self.source_names}")
            elif is_mp4:
                # Use explicit software decoder for MP4 (faster than decodebin)
                # qtdemux ! h264parse ! avdec_h264 is more efficient than decodebin
                if self._gst_has('qtdemux') and self._gst_has('h264parse') and self._gst_has('avdec_h264'):
                    pipeline = (
                        f"filesrc location={self.source_address} ! qtdemux ! h264parse ! avdec_h264 ! videoconvert"
                    )
                    self.logger.info(f"Using explicit H.264 decoder for {self.source_names}")
                else:
                    # Fallback to decodebin if explicit decoder not available
                    pipeline = f"filesrc location={self.source_address} ! decodebin name=dec ! videoconvert"
            else:
                # For other formats, use decodebin (supports all codecs)
                pipeline = f"filesrc location={self.source_address} ! decodebin name=dec ! videoconvert"
            if force_sw:
                try:
                    self.logger.info(
                        f"Force software decoder enabled for {self.source_names} (EVILEYE_GST_FORCE_SW_DECODER/params)")
                except Exception:
                    pass


        elif self.source_type == CaptureDeviceType.Device:
            # USB/Device camera pipeline
            device_id = self.source_address if self.source_address.isdigit() else "0"
            pipeline = f"v4l2src device=/dev/video{device_id} ! videoconvert"

        elif self.source_type == CaptureDeviceType.ImageSequence:
            # Image sequence pipeline - prefer explicit caps/decoder to avoid typefind issues
            pattern = str(self.source_address)
            is_pattern = any(ch in pattern for ch in ['%', '*', '?'])
            if not is_pattern:
                # Treat as directory; append wildcard to pick all images
                if pattern.endswith("/"):
                    pattern = f"{pattern}frame_%05d.jpg"
                else:
                    pattern = f"{pattern}/frame_%05d.jpg"
            # Determine decoder/caps from extension if possible
            decoder = "decodebin"
            caps_str = None
            import os
            _, ext = os.path.splitext(pattern.lower())
            fps_num, fps_den = (15, 1)
            if self.desired_fps and self.desired_fps > 0:
                fps = float(self.desired_fps)
                if abs(fps - round(fps)) < 1e-6:
                    fps_num, fps_den = int(round(fps)), 1
                else:
                    fps_num, fps_den = int(round(fps * 1001)), 1001
            if ext in {".jpg", ".jpeg"}:
                caps_str = f"image/jpeg,framerate={fps_num}/{fps_den}"
                decoder = "jpegdec"
            elif ext == ".png":
                caps_str = f"image/png,framerate={fps_num}/{fps_den}"
                decoder = "pngdec"
            elif ext == ".bmp":
                caps_str = f"image/bmp,framerate={fps_num}/{fps_den}"
                decoder = "decodebin"
            # Build pipeline with caps when known to avoid gst_type_find errors
            if caps_str:
                pipeline = (
                    f"multifilesrc location={pattern} loop=false do-timestamp=true caps=\"{caps_str}\" "
                    f"! {decoder} ! videoconvert"
                )
            else:
                pipeline = (
                    f"multifilesrc location={pattern} loop=false do-timestamp=true "
                    f"! decodebin ! videoconvert"
                )

        else:
            raise ValueError(f"Unsupported source type: {self.source_type}")

        # Add common pipeline end - simplified
        # Apply desired FPS if requested using videorate (before format caps/appsink)
        # NOTE: For VideoFile, videorate can slow down playback unnecessarily.
        # Only apply videorate for live sources (IpCamera) or when explicitly desired.
        if self.desired_fps and self.desired_fps > 0:
            # For VideoFile, videorate may unnecessarily slow down playback
            # Only apply if it's a live source or explicitly needed
            if self.source_type != CaptureDeviceType.VideoFile:
                try:
                    # Convert to fraction (prefer integer; fallback to 1001 base)
                    fps = float(self.desired_fps)
                    if abs(fps - round(fps)) < 1e-6:
                        num, den = int(round(fps)), 1
                    else:
                        # Use 1001 denominator for common NTSC-like framerates
                        num, den = int(round(fps * 1001)), 1001
                    # Limit to desired FPS without upsampling (no capsfilter forcing framerate)
                    # videorate max-rate drops frames if source faster; if slower, it passes through
                    pipeline += f" ! videorate max-rate={num} drop-only=true"
                except Exception:
                    # If anything goes wrong, skip forcing fps
                    pass
        # Determine sync mode: true for all sources to maintain correct playback speed
        # sync=true ensures video files play at their native FPS rate
        sync_mode = "true"

        # If continuous recording is enabled, use tee to split stream: one to appsink, one to recording
        # `enabled` is a master switch. Continuous recording must be explicitly enabled.
        continuous_enabled = bool(
            self.recording_params
            and self.recording_params.enabled
            and self.recording_params.continuous_recording_enabled
        )
        if continuous_enabled:
            # Use tee to split stream
            # NOTE: tee requires queues on each branch to avoid blocking
            pipeline += " ! tee name=t"
            # Branch 1: to appsink for capture
            # For VideoFile, use minimal queue (just enough for tee to work)
            # Increased max-buffers to 5 for better buffering with hardware decoder
            if self.source_type == CaptureDeviceType.VideoFile:
                pipeline += f" t. ! queue max-size-buffers=2 max-size-bytes=0 max-size-time=0 ! video/x-raw,format=BGR ! appsink name=sink emit-signals=true wait-on-eos=false enable-last-sample=false sync={sync_mode} max-buffers=5 drop=true"
            else:
                # For live sources, keep larger queue for isolation
                pipeline += f" t. ! queue max-size-buffers=10 max-size-bytes=0 max-size-time=0 ! video/x-raw,format=BGR ! appsink name=sink emit-signals=true wait-on-eos=false enable-last-sample=false sync={sync_mode} max-buffers=5 drop=true"
            # Branch 2: to recording (will be connected after pipeline creation)
            # IMPORTANT: recording branch must be bounded.
            # If encoder/muxer/disk is slower than realtime, an unbounded queue will
            # accumulate raw frames and inflate RSS indefinitely.
            pipeline += " t. ! queue name=recording_queue max-size-buffers=5 max-size-bytes=0 max-size-time=500000000 leaky=downstream"
        else:
            # No recording - direct to appsink
            # For VideoFile, no queue needed (no tee)
            # Increased max-buffers to 5 for better buffering with hardware decoder
            if self.source_type == CaptureDeviceType.VideoFile:
                pipeline += f" ! video/x-raw,format=BGR ! appsink name=sink emit-signals=true wait-on-eos=false enable-last-sample=false sync={sync_mode} max-buffers=5 drop=true"
            else:
                # For live sources, keep queue for isolation
                pipeline += f" ! queue max-size-buffers=10 max-size-bytes=0 max-size-time=0 ! video/x-raw,format=BGR ! appsink name=sink emit-signals=true wait-on-eos=false enable-last-sample=false sync={sync_mode} max-buffers=5 drop=true"

        return pipeline

    def _build_pipeline_candidates(self) -> List[str]:
        """
        Build multiple pipeline candidates for IP cameras (H265, H264).
        Returns list of pipeline strings to try in order.
        Uses UDP protocol by default, never switches to TCP automatically.
        """
        if self.source_type != CaptureDeviceType.IpCamera:
            return [self._build_pipeline()]

        candidates = []

        # Build base RTSP part - use UDP protocol by default, but allow TCP fallback
        # protocols=udp+tcp allows GStreamer to try UDP first, then fallback to TCP if UDP fails
        protocol = getattr(self, '_rtsp_protocol', 'udp+tcp')  # Try UDP first, then TCP if UDP fails
        if self.username and self.password:
            base_rtsp = f"rtspsrc location={self.source_address} user-id={self.username} user-pw={self.password} protocols={protocol}"
        else:
            base_rtsp = f"rtspsrc location={self.source_address} protocols={protocol}"

        # Build common tail (videoconvert + queue + appsink/tee)
        # For IP cameras, use sync=true to synchronize with real-time clock
        # (Note: _build_pipeline_candidates is only called for IpCamera, so sync is always true here)
        common_tail = " ! videoconvert"
        # `enabled` is a master switch. Continuous recording must be explicitly enabled.
        continuous_enabled = bool(
            self.recording_params
            and self.recording_params.enabled
            and self.recording_params.continuous_recording_enabled
        )
        if continuous_enabled:
            common_tail += " ! tee name=t"
            common_tail += " t. ! queue max-size-buffers=10 max-size-bytes=0 max-size-time=0 ! video/x-raw,format=BGR ! appsink name=sink emit-signals=true wait-on-eos=false enable-last-sample=false sync=true max-buffers=3 drop=true"
            # IMPORTANT: recording branch must be bounded to avoid runaway RSS.
            common_tail += " t. ! queue name=recording_queue max-size-buffers=5 max-size-bytes=0 max-size-time=500000000 leaky=downstream"
        else:
            common_tail += " ! queue max-size-buffers=10 max-size-bytes=0 max-size-time=0 ! video/x-raw,format=BGR ! appsink name=sink emit-signals=true wait-on-eos=false enable-last-sample=false sync=true max-buffers=3 drop=true"

        # Candidate 1: H265 (if username/password provided, try H265 first)
        if self.username and self.password:
            candidates.append(f"{base_rtsp} ! rtph265depay ! h265parse ! avdec_h265{common_tail}")

        # Candidate 2: H264 (always try H264)
        candidates.append(f"{base_rtsp} ! rtph264depay ! h264parse ! avdec_h264{common_tail}")

        # Candidate 3: H265 without auth (if no username/password, try H265)
        if not self.username or not self.password:
            candidates.insert(0, f"{base_rtsp} ! rtph265depay ! h265parse ! avdec_h265{common_tail}")

        return candidates

    def _gst_has(self, element_name: str) -> bool:
        """Check if GStreamer element factory exists."""
        try:
            return self.gstreamer_available and Gst.ElementFactory.find(element_name) is not None
        except Exception:
            return False

    def _init_pipeline(self):
        """
        Initialize GStreamer pipeline.
        For IP cameras, tries multiple pipeline candidates (H265, H264) until one works.
        Uses simple approach from api-refactoring with get_state(Gst.CLOCK_TIME_NONE).
        """
        pipeline_str = None
        try:
            with self.pipeline_lock:
                if self.pipeline:
                    # Use full teardown to avoid accumulating signal watches/callbacks on re-init
                    # (may happen during reconnects or repeated init attempts).
                    try:
                        self._teardown_pipeline("reinit_before_init", join_main_loop=True)
                    except Exception:
                        try:
                            self.pipeline.set_state(Gst.State.NULL)
                        except Exception:
                            pass
                        self.pipeline = None

                # For IP cameras, try multiple pipeline candidates
                if self.source_type == CaptureDeviceType.IpCamera:
                    candidates = self._build_pipeline_candidates()
                    pipeline_str = None
                    last_error = None

                    for i, candidate_str in enumerate(candidates, 1):
                        try:
                            if i > 1:
                                self.logger.info(f"Trying pipeline candidate {i}/{len(candidates)}")
                                self.logger.debug(
                                    f"GStreamer pipeline (candidate): {self._mask_credentials_in_pipeline(candidate_str)}")
                            else:
                                self.logger.info(
                                    f"GStreamer pipeline: {self._mask_credentials_in_pipeline(candidate_str)}")

                            # Some failures (like unwritable recording dir) should disable recording
                            # and retry the SAME codec candidate without recording branch, without failing the whole init.
                            attempted_without_recording = False
                            while True:
                                # Clean up previous pipeline if any
                                if self.pipeline:
                                    try:
                                        self.pipeline.set_state(Gst.State.NULL)
                                    except Exception:
                                        pass
                                    self.pipeline = None

                                # Parse and create pipeline
                                self.pipeline = Gst.parse_launch(candidate_str)
                                if not self.pipeline:
                                    self.logger.warning(f"Failed to create pipeline candidate {i}")
                                    last_error = f"Failed to create pipeline candidate {i}"
                                    break

                                # Setup bus
                                self.bus = self.pipeline.get_bus()
                                if self.bus is not None:
                                    try:
                                        self.bus.add_signal_watch()
                                        self._bus_handler_id = self.bus.connect("message", self._on_bus_message)
                                    except Exception:
                                        pass

                                # Get appsink element
                                self.appsink = self.pipeline.get_by_name("sink")
                                if not self.appsink:
                                    self.logger.warning(f"Failed to get appsink from candidate {i}")
                                    last_error = f"Failed to get appsink from candidate {i}"
                                    break

                                # Connect callback
                                try:
                                    self._appsink_handler_id = self.appsink.connect("new-sample", self._on_new_sample)
                                except Exception:
                                    self._appsink_handler_id = None

                                # Setup recording branch if continuous recording enabled
                                # `enabled` is a master switch. Continuous recording must be explicitly enabled.
                                continuous_enabled = bool(
                                    self.recording_params
                                    and self.recording_params.enabled
                                    and self.recording_params.continuous_recording_enabled
                                )
                                if continuous_enabled and not attempted_without_recording:
                                    try:
                                        self._setup_recording_branch()
                                    except _RecordingFilesystemError as e:
                                        # Disable recording due to FS issues, log once, and retry without recording
                                        self._recording_disabled_due_to_fs = True
                                        try:
                                            if self.recording_params:
                                                self.recording_params.enabled = False
                                                self.recording_params.continuous_recording_enabled = False
                                        except Exception:
                                            pass
                                        # Log once per source set
                                        try:
                                            src_key = tuple(self.source_names) if self.source_names else str(
                                                self.source_address)
                                        except Exception:
                                            src_key = str(self.source_address)
                                        if src_key not in self.__class__._recording_fs_error_logged:
                                            self.__class__._recording_fs_error_logged.add(src_key)
                                            self.logger.warning(
                                                f"Recording disabled for {self.source_names} due to output path error: {e}. "
                                                f"Video capture will continue without recording."
                                            )
                                        # Rebuild candidate without recording (no tee/recording_queue)
                                        try:
                                            new_candidates = self._build_pipeline_candidates()
                                            # Preserve codec preference for this candidate
                                            if "rtph265depay" in candidate_str:
                                                codec_token = "rtph265depay"
                                            elif "rtph264depay" in candidate_str:
                                                codec_token = "rtph264depay"
                                            else:
                                                codec_token = None
                                            if codec_token:
                                                matched = [c for c in new_candidates if codec_token in c]
                                                candidate_str = matched[0] if matched else new_candidates[0]
                                            else:
                                                candidate_str = new_candidates[0]
                                        except Exception:
                                            # Fallback: just disable tee by trying to re-init with new candidates list
                                            pass
                                        attempted_without_recording = True
                                        continue
                                    except Exception as e:
                                        # Other recording setup errors are real errors and should fail the candidate
                                        self.logger.error(f"Failed to setup recording branch: {e}", exc_info=True)
                                        raise

                                # Success path continues below (set PLAYING)
                                break
                            else:
                                # while True exhausted via break; continue to set_state below
                                pass
                            if not self.pipeline:
                                continue

                            # Set pipeline to playing state - simple approach from api-refactoring
                            # Recording branch must be fully set up before this point
                            ret = self.pipeline.set_state(Gst.State.PLAYING)
                            if ret == Gst.StateChangeReturn.FAILURE:
                                # Get error message from bus
                                msg = self.bus.pop_filtered(Gst.MessageType.ERROR | Gst.MessageType.WARNING)
                                if msg:
                                    if msg.type == Gst.MessageType.ERROR:
                                        err, debug = msg.parse_error()
                                        self.logger.warning(
                                            f"GStreamer pipeline ERROR (candidate {i}): {err}, debug: {debug}")
                                    elif msg.type == Gst.MessageType.WARNING:
                                        warn, debug = msg.parse_warning()
                                        self.logger.warning(
                                            f"GStreamer pipeline WARNING (candidate {i}): {warn}, debug: {debug}")
                                last_error = f"Failed to start pipeline candidate {i}"
                                continue
                            elif ret == Gst.StateChangeReturn.ASYNC:
                                # Wait for state change to complete - use CLOCK_TIME_NONE like api-refactoring
                                ret = self.pipeline.get_state(Gst.CLOCK_TIME_NONE)
                                if ret[0] == Gst.StateChangeReturn.FAILURE:
                                    # Get error message from bus
                                    msg = self.bus.pop_filtered(Gst.MessageType.ERROR | Gst.MessageType.WARNING)
                                    if msg:
                                        if msg.type == Gst.MessageType.ERROR:
                                            err, debug = msg.parse_error()
                                            self.logger.warning(
                                                f"GStreamer pipeline ERROR (candidate {i} async): {err}, debug: {debug}")
                                        elif msg.type == Gst.MessageType.WARNING:
                                            warn, debug = msg.parse_warning()
                                            self.logger.warning(
                                                f"GStreamer pipeline WARNING (candidate {i} async): {warn}, debug: {debug}")
                                    last_error = f"Failed to start pipeline candidate {i} (async)"
                                    continue

                            # Success! This candidate works
                            pipeline_str = candidate_str
                            if i > 1:
                                self.logger.info(f"Pipeline candidate {i} succeeded!")
                            break

                        except Exception as e:
                            self.logger.warning(f"Error with pipeline candidate {i}: {e}")
                            last_error = str(e)
                            continue

                    if not pipeline_str:
                        # All candidates failed
                        raise RuntimeError(f"All pipeline candidates failed. Last error: {last_error}")
                else:
                    # For non-IP cameras, use single pipeline
                    pipeline_str = self._build_pipeline()
                    self.logger.info(f"GStreamer pipeline: {self._mask_credentials_in_pipeline(pipeline_str)}")

                    # Parse and create pipeline
                    self.pipeline = Gst.parse_launch(pipeline_str)
                    if not self.pipeline:
                        raise RuntimeError("Failed to create GStreamer pipeline")

                    # Setup bus to handle EOS/ERROR
                    self.bus = self.pipeline.get_bus()
                    if self.bus is not None:
                        try:
                            self.bus.add_signal_watch()
                            self._bus_handler_id = self.bus.connect("message", self._on_bus_message)
                        except Exception:
                            pass

                    # Get appsink element
                    self.appsink = self.pipeline.get_by_name("sink")
                    if not self.appsink:
                        raise RuntimeError("Failed to get appsink element")

                    # Connect callback
                    try:
                        self._appsink_handler_id = self.appsink.connect("new-sample", self._on_new_sample)
                    except Exception:
                        self._appsink_handler_id = None

                    # `enabled` is a master switch. Continuous recording must be explicitly enabled.
                    continuous_enabled = bool(
                        self.recording_params
                        and self.recording_params.enabled
                        and self.recording_params.continuous_recording_enabled
                    )
                    if continuous_enabled:
                        try:
                            self._setup_recording_branch()
                            # Verify that recording branch is properly linked before proceeding
                            recording_queue = self.pipeline.get_by_name("recording_queue")
                            if recording_queue:
                                src_pad = recording_queue.get_static_pad("src")
                                if src_pad:
                                    peer = src_pad.get_peer()
                                    if not peer:
                                        self.logger.error("recording_queue src pad is not linked after setup!")
                                        raise RuntimeError(
                                            "Recording branch setup incomplete: recording_queue not linked")
                        except _RecordingFilesystemError as e:
                            # Disable recording and rebuild pipeline without tee/recording_queue
                            self._recording_disabled_due_to_fs = True
                            try:
                                if self.recording_params:
                                    self.recording_params.enabled = False
                                    self.recording_params.continuous_recording_enabled = False
                            except Exception:
                                pass
                            try:
                                src_key = tuple(self.source_names) if self.source_names else str(self.source_address)
                            except Exception:
                                src_key = str(self.source_address)
                            if src_key not in self.__class__._recording_fs_error_logged:
                                self.__class__._recording_fs_error_logged.add(src_key)
                                self.logger.warning(
                                    f"Recording disabled for {self.source_names} due to output path error: {e}. "
                                    f"Video capture will continue without recording."
                                )

                            # Recreate pipeline without recording
                            try:
                                self.pipeline.set_state(Gst.State.NULL)
                            except Exception:
                                pass
                            self.pipeline = None

                            pipeline_str = self._build_pipeline()
                            self.logger.info(
                                f"GStreamer pipeline (recording disabled): {self._mask_credentials_in_pipeline(pipeline_str)}")
                            self.pipeline = Gst.parse_launch(pipeline_str)
                            if not self.pipeline:
                                raise RuntimeError("Failed to create GStreamer pipeline after disabling recording")
                            self.bus = self.pipeline.get_bus()
                            if self.bus is not None:
                                try:
                                    self.bus.add_signal_watch()
                                    self._bus_handler_id = self.bus.connect("message", self._on_bus_message)
                                except Exception:
                                    pass
                            self.appsink = self.pipeline.get_by_name("sink")
                            if not self.appsink:
                                raise RuntimeError("Failed to get appsink element after disabling recording")
                            try:
                                self._appsink_handler_id = self.appsink.connect("new-sample", self._on_new_sample)
                            except Exception:
                                self._appsink_handler_id = None
                        except Exception as e:
                            self.logger.error(f"Failed to setup recording branch: {e}", exc_info=True)
                            # Don't continue - recording branch must be set up before pipeline goes to PLAYING
                            raise

                    # Set pipeline to playing state - simple approach from api-refactoring
                    # Recording branch must be fully set up before this point
                    ret = self.pipeline.set_state(Gst.State.PLAYING)
                    if ret == Gst.StateChangeReturn.FAILURE:
                        raise RuntimeError("Failed to start GStreamer pipeline")
                    elif ret == Gst.StateChangeReturn.ASYNC:
                        # Wait for state change to complete - use CLOCK_TIME_NONE like api-refactoring
                        ret = self.pipeline.get_state(Gst.CLOCK_TIME_NONE)
                        if ret[0] == Gst.StateChangeReturn.FAILURE:
                            raise RuntimeError("Failed to start GStreamer pipeline")

                # Query duration for VideoFile
                if self.source_type == CaptureDeviceType.VideoFile:
                    try:
                        ok, dur_ns = self.pipeline.query_duration(Gst.Format.TIME)
                        if ok and dur_ns and dur_ns > 0:
                            self.video_duration = float(dur_ns) / 1e6  # ms
                            if self.source_fps:
                                self.video_length = int((self.video_duration / 1000.0) * self.source_fps)
                    except Exception:
                        pass

                self.logger.info("GStreamer pipeline initialized successfully")
                # Track initialization time to ignore early EOS messages
                self._init_time = time.time()
                # Reset performance metrics for new pipeline run
                self._perf_last_log = self._init_time
                self._perf_frame_count = 0
                self._perf_pull_total = 0.0
                self._perf_process_total = 0.0
                self._perf_pts_accum = 0.0
                self._perf_pts_count = 0
                self._perf_frame_buffer_full = 0

        except Exception as e:
            self.logger.error(f"Failed to initialize GStreamer pipeline: {e}")
            if pipeline_str:
                self.logger.error(f"Pipeline string was: {self._mask_credentials_in_pipeline(pipeline_str)}")
            raise

    def _mask_credentials_in_pipeline(self, pipeline_str: str) -> str:
        """
        Mask credentials (username and password) in pipeline string for logging.
        Replaces user-id=... and user-pw=... with user-id=**** and user-pw=****
        Also masks credentials in RTSP URLs (rtsp://user:pass@host → rtsp://****:****@host)
        """
        if not pipeline_str:
            return pipeline_str
        try:
            import re
            # Mask user-id="username" or user-id=username
            pipeline_str = re.sub(r'user-id=["\']?([^"\'\s]+)["\']?', r'user-id="****"', pipeline_str)
            # Mask user-pw="password" or user-pw=password
            pipeline_str = re.sub(r'user-pw=["\']?([^"\'\s]+)["\']?', r'user-pw="****"', pipeline_str)
            # Mask credentials in RTSP URL: rtsp://user:pass@host → rtsp://****:****@host
            pipeline_str = re.sub(r'rtsp://[^:@/]+:[^@]+@', 'rtsp://****:****@', pipeline_str)
            # Mask credentials in RTSP URL without password: rtsp://user@host → rtsp://****@host
            pipeline_str = re.sub(r'rtsp://[^:@/]+@', 'rtsp://****@', pipeline_str)
        except Exception:
            pass
        return pipeline_str

    def _on_bus_message(self, bus, message):
        try:
            msg_type = message.type
            if msg_type == Gst.MessageType.EOS:
                self.logger.info(
                    f"GStreamer EOS received for {self.source_names} (is_inited={self.is_inited}, is_working={self.is_working})")
                if self.source_type == CaptureDeviceType.VideoFile and self.loop_play:
                    # Prevent multiple simultaneous reconnection attempts
                    if self._reconnecting:
                        return

                    self._reconnecting = True
                    try:
                        # NOTE: Seek-based looping is disabled by default because with some demux/decoder
                        # combinations it can trigger GStreamer segment-format criticals and lead to
                        # downstream "no frames" restarts. Enable explicitly with env EVILEYE_GST_LOOP_SEEK=1.
                        self._restart_counter += 1
                        self._log_resource_stats("before_restart_eos")

                        did_seek = False
                        pipeline = None
                        with self.pipeline_lock:
                            pipeline = self.pipeline
                        allow_seek = False
                        try:
                            import os as _os
                            allow_seek = _os.environ.get("EVILEYE_GST_LOOP_SEEK", "").strip().lower() in {"1", "true",
                                                                                                          "yes", "on"}
                        except Exception:
                            allow_seek = False

                        if allow_seek and pipeline is not None:
                            try:
                                # Mark not working until first frame after seek.
                                self.is_working = False
                                self.is_inited = True
                                # Drop python-side frames immediately.
                                try:
                                    with self.frame_lock:
                                        while not self.frame_buffer.empty():
                                            try:
                                                frame = self.frame_buffer.get_nowait()
                                                if frame is not None:
                                                    frame.image = None
                                            except Empty:
                                                break
                                        if self.last_frame is not None:
                                            try:
                                                self.last_frame.image = None
                                            except Exception:
                                                pass
                                            self.last_frame = None
                                except Exception:
                                    pass

                                flags = Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT
                                did_seek = bool(
                                    pipeline.seek(
                                        1.0,  # rate
                                        Gst.Format.TIME,
                                        flags,
                                        Gst.SeekType.SET,
                                        0,  # start (ns)
                                        Gst.SeekType.NONE,
                                        -1,  # stop
                                    )
                                )
                                if did_seek:
                                    try:
                                        pipeline.set_state(Gst.State.PLAYING)
                                    except Exception:
                                        pass
                            except Exception:
                                did_seek = False

                        if did_seek:
                            self._init_time = None
                            self.logger.info("Looping video: seeked to start successfully (no pipeline rebuild)")
                            self._log_resource_stats("after_restart_eos")
                        else:
                            # Fallback to full rebuild when seek is not supported / fails.
                            if allow_seek:
                                self.logger.warning("Looping video: seek failed; falling back to pipeline rebuild")
                            self._teardown_pipeline("eos_loop_restart", join_main_loop=False)
                            self._init_time = None
                            time.sleep(0.1)
                            self._init_pipeline()

                            # Verify pipeline is actually initialized and playing
                            with self.pipeline_lock:
                                if self.pipeline is not None:
                                    ret, state, pending = self.pipeline.get_state(0)
                                    if ret == Gst.StateChangeReturn.SUCCESS and state == Gst.State.PLAYING:
                                        # is_working will be set in _on_new_sample when first frame is received
                                        self.is_inited = True
                                        self.logger.info(
                                            f"Looping video: pipeline restarted successfully (is_inited={self.is_inited}, is_working={self.is_working}, state={state})")
                                        self._log_resource_stats("after_restart_eos")
                                    else:
                                        self.logger.warning(
                                            f"Loop restart: pipeline created but not PLAYING (state={state}, ret={ret})")
                                        self.is_inited = False
                                        self.is_working = False
                                else:
                                    self.logger.error("Loop restart: pipeline is None after _init_pipeline()")
                                    self.is_inited = False
                                    self.is_working = False
                    except Exception as e:
                        self.logger.error(
                            f"Loop restart failed: {e} (is_inited={self.is_inited}, is_working={self.is_working})",
                            exc_info=True)
                        # Mark as not initialized on failure
                        self.is_inited = False
                        self.is_working = False
                    finally:
                        self._reconnecting = False
                elif self.source_type == CaptureDeviceType.IpCamera:
                    # For IP cameras, EOS means disconnect - but ignore early EOS (within 5 seconds of init)
                    # This prevents false positives when pipeline is still initializing
                    now = time.time()
                    if self._init_time and (now - self._init_time) < CaptureConstants.INIT_GRACE_PERIOD_SECONDS:
                        self.logger.debug(
                            f"Ignoring early EOS ({(now - self._init_time):.1f}s after init) - pipeline may still be initializing")
                        return
                    # For IP cameras, EOS means disconnect - mark not working; monitor thread handles reconnect
                    self.logger.warning("GStreamer EOS for IP camera")
                    self.is_working = False
                    timestamp = datetime.datetime.now()
                    self._record_disconnect(timestamp)
                    for sub in self.subscribers:
                        sub.update()
                    # Trigger reconnect loop if not already running
                    if self.run_flag and not self._reconnecting:
                        threading.Thread(target=self._reconnect_loop, daemon=True).start()
                else:
                    self.finished = True
                    self.is_working = False
            elif msg_type == Gst.MessageType.ERROR:
                err, debug = message.parse_error()
                err_str = str(err)
                debug_str = str(debug)

                # Проверяем, является ли это "Internal data stream error" от udpsrc
                is_udp_stream_error = (
                        "Internal data stream error" in err_str and
                        "udpsrc" in debug_str.lower()
                )

                # Получаем значение ignore_udp_stream_errors из конфига
                ignore_udp_errors = getattr(self.capture_config, 'ignore_udp_stream_errors', True)

                if is_udp_stream_error and ignore_udp_errors:
                    # Это временная потеря UDP пакетов - не критично
                    now = time.time()
                    self._udp_error_count += 1

                    # Запоминаем время первой ошибки в серии
                    if self._last_udp_error_time is None:
                        self._last_udp_error_time = now

                    time_since_first_error = now - self._last_udp_error_time

                    # Логируем как DEBUG (не ERROR)
                    self.logger.debug(
                        f"UDP stream error (temporary packet loss) for {self.source_names}: "
                        f"error_count={self._udp_error_count}, "
                        f"time_since_first={time_since_first_error:.1f}s, "
                        f"debug={debug_str[:100]}"
                    )

                    # Реконнектим только если:
                    # 1. Ошибок подряд >= threshold
                    # 2. Прошло >= delay секунд с первой ошибки
                    should_reconnect = (
                            self._udp_error_count >= self._udp_error_threshold and
                            time_since_first_error >= self._udp_error_reconnect_delay
                    )

                    if should_reconnect:
                        self.logger.warning(
                            f"UDP stream errors threshold reached for {self.source_names} "
                            f"({self._udp_error_count} errors in {time_since_first_error:.1f}s), triggering reconnect"
                        )
                        self.is_working = False
                        # Сбрасываем счетчик перед реконнектом
                        self._udp_error_count = 0
                        self._last_udp_error_time = None

                        if self.source_type == CaptureDeviceType.IpCamera and self.run_flag:
                            timestamp = datetime.datetime.now()
                            self._record_disconnect(timestamp)
                            for sub in self.subscribers:
                                sub.update()
                            # Store error for protocol switching logic
                            self._last_init_error = RuntimeError(f"{err}: {debug}")
                            # Trigger reconnect loop if not already running
                            if not self._reconnecting:
                                threading.Thread(target=self._reconnect_loop, daemon=True).start()
                    else:
                        # Недостаточно ошибок или времени - просто игнорируем
                        # Поток может восстановиться сам
                        pass
                else:
                    # Другие ошибки или ignore_udp_stream_errors=False - обрабатываем как обычно
                    self.logger.error(f"GStreamer ERROR: {err}, debug: {debug}")
                    self.is_working = False
                    # Сбрасываем счетчик UDP ошибок при других ошибках
                    self._udp_error_count = 0
                    self._last_udp_error_time = None

                    # For IP cameras, just mark not working; monitor thread handles reconnect
                    if self.source_type == CaptureDeviceType.IpCamera and self.run_flag:
                        timestamp = datetime.datetime.now()
                        self._record_disconnect(timestamp)
                        for sub in self.subscribers:
                            sub.update()
                        # Store error for protocol switching logic
                        self._last_init_error = RuntimeError(f"{err}: {debug}")
                        # Trigger reconnect loop if not already running
                        if not self._reconnecting:
                            threading.Thread(target=self._reconnect_loop, daemon=True).start()
            elif msg_type == Gst.MessageType.WARNING:
                warn, debug = message.parse_warning()
                # Check for UDP-related warnings - hide them from logs as they are common and not critical
                if "UDP" in str(warn) or "udp" in str(warn).lower() or "Error sending" in str(
                        warn) or "Error sending UDP packets" in str(warn):
                    # Don't log UDP errors - they are common when UDP is blocked or not supported
                    # Still store error for internal use if needed
                    if self.source_type == CaptureDeviceType.IpCamera:
                        self._last_init_error = RuntimeError(f"UDP connection error: {warn}: {debug}")
                else:
                    # Log other warnings normally
                    self.logger.warning(f"GStreamer pipeline WARNING: {warn}, debug: {debug}")
        except Exception as e:
            self.logger.error(f"Error handling bus message: {e}")

    def _seek_to_start(self):
        try:
            with self.pipeline_lock:
                if not self.pipeline:
                    return
                # Flush and seek to start
                success = self.pipeline.seek_simple(
                    Gst.Format.TIME,
                    Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT | Gst.SeekFlags.ACCURATE,
                    0
                )
                if success:
                    self.logger.info("Looping video: seek to start")
                    self.finished = False
                    self.is_working = True
                else:
                    self.logger.warning("Looping video: seek failed, restarting pipeline")
                    # Fallback: restart pipeline
                    self.pipeline.set_state(Gst.State.NULL)
                    self.pipeline.set_state(Gst.State.PLAYING)
        except Exception as e:
            self.logger.error(f"Looping video: exception during seek: {e}")

    def _start_main_loop(self):
        """
        Start GLib main loop in separate thread.
        """

        def run_loop():
            self.loop = GLib.MainLoop()
            self.loop.run()

        self.main_loop_thread = threading.Thread(target=run_loop, daemon=True)
        self.main_loop_thread.start()

    def _stop_main_loop(self, *, join_thread: bool = True):
        """
        Stop GLib main loop.
        """
        if self.loop and self.loop.is_running():
            self.loop.quit()
        if join_thread and self.main_loop_thread and self.main_loop_thread.is_alive():
            # Avoid self-join if called from within the loop thread (e.g. bus callback)
            try:
                if threading.current_thread() is self.main_loop_thread:
                    return
            except Exception:
                pass
            self.main_loop_thread.join(timeout=2.0)

    def _teardown_pipeline(self, reason: str, *, join_main_loop: bool) -> None:
        """
        Tear down pipeline resources safely.

        Designed to be callable from GStreamer/GLib callback threads (join_main_loop=False).
        """
        if not self.gstreamer_available:
            return

        pipeline = None
        bus = None
        appsink = None

        # Detach references first (under lock) to prevent concurrent use.
        with self.pipeline_lock:
            pipeline = self.pipeline
            self.pipeline = None
            bus = self.bus
            self.bus = None
            appsink = self.appsink
            self.appsink = None
            self.is_inited = False
            self.is_working = False
            self._last_sample_wall_ts = 0.0

        # Log teardown summary early (helps correlate RSS growth with resource release).
        try:
            self.logger.info(
                f"GStreamer teardown for {self.source_names}: reason={reason}, join_main_loop={join_main_loop}, "
                f"had_pipeline={pipeline is not None}, had_bus={bus is not None}, had_sink={appsink is not None}, "
                f"bus_handler_id={self._bus_handler_id}, appsink_handler_id={self._appsink_handler_id}"
            )
        except Exception:
            pass

        # Stop appsink signals and disconnect handler.
        try:
            if appsink is not None:
                try:
                    appsink.set_property("emit-signals", False)
                except Exception:
                    pass
                try:
                    if self._appsink_handler_id is not None:
                        appsink.disconnect(self._appsink_handler_id)
                except Exception:
                    pass
        finally:
            self._appsink_handler_id = None

        # Remove bus watches / callbacks to avoid accumulating GLib sources.
        try:
            if bus is not None:
                try:
                    if self._bus_handler_id is not None:
                        bus.disconnect(self._bus_handler_id)
                except Exception:
                    pass
                finally:
                    self._bus_handler_id = None
                try:
                    bus.remove_signal_watch()
                except Exception:
                    pass
                try:
                    bus.set_flushing(True)
                except Exception:
                    pass
        except Exception:
            pass

        # Stop recording helpers and detach recording elements from the old pipeline.
        try:
            # If decoupled recorder is used, stop it first.
            try:
                if self._gst_continuous_recorder is not None:
                    self._gst_continuous_recorder.stop_with_pipeline(pipeline=pipeline, Gst=Gst)
            except Exception:
                pass
            self._cleanup_recording_branch(pipeline=pipeline)
        except Exception:
            pass

        # Clear frame buffers to drop Python-side references quickly.
        try:
            with self.frame_lock:
                while not self.frame_buffer.empty():
                    try:
                        frame = self.frame_buffer.get_nowait()
                        if frame is not None:
                            frame.image = None
                    except Empty:
                        break
                if self.last_frame is not None:
                    try:
                        self.last_frame.image = None
                    except Exception:
                        pass
                    self.last_frame = None
                self._fps_times.clear()
        except Exception:
            pass

        # Stop GLib main loop (optionally join thread).
        try:
            if join_main_loop:
                self._stop_main_loop(join_thread=True)
            else:
                self._stop_main_loop(join_thread=False)
        except Exception:
            pass

        # Stop notify worker and drop queued frames
        try:
            self._stop_notify_worker()
        except Exception:
            pass

        # Finally, try to move pipeline to NULL to release GStreamer resources.
        if pipeline is not None:
            try:
                pipeline.send_event(Gst.Event.new_eos())
            except Exception:
                pass
            try:
                pipeline.set_state(Gst.State.NULL)
            except Exception:
                pass
            # Drop local refs ASAP to help GC / gi unref.
            try:
                pipeline = None
            except Exception:
                pass
        # Optional: best-effort trimming (async + rate-limited) to reduce RSS plateaus.
        try:
            self._maybe_schedule_malloc_trim(reason=reason)
        except Exception:
            pass
        try:
            if reason:
                self.logger.debug(f"Teardown completed for {self.source_names}: reason={reason}")
        except Exception:
            pass
