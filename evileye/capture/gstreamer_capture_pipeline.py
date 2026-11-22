"""GStreamer capture mixin — see video_capture_gstreamer.py."""

from __future__ import annotations

from .gstreamer_capture_common import (
    CaptureConstants,
    CaptureDeviceType,
    CaptureInitializationError,
    Empty,
    GLib,
    Gst,
    List,
    Optional,
    datetime,
    threading,
    time,
)
from .gstreamer_capture_recording import _RecordingFilesystemError

# Keep strong refs to Gst objects that timed out while leaving PLAYING/PAUSED.
# Dropping the last Python ref in that state aborts the process (g_mutex_clear).
_ORPHANED_GST_NATIVE: list = []


class GStreamerCapturePipelineMixin:
    @staticmethod
    def _orphan_gst_native(*objects) -> None:
        """Pin native objects so Python GC cannot dispose a non-NULL Gst element."""
        for obj in objects:
            if obj is None:
                continue
            if obj not in _ORPHANED_GST_NATIVE:
                _ORPHANED_GST_NATIVE.append(obj)

    def _gst_element_is_null(self, element) -> bool:
        """Best-effort check that an element reached NULL after set_state."""
        if element is None or Gst is None:
            return True
        try:
            _ret, state, _pending = element.get_state(0)
            return state == Gst.State.NULL
        except Exception:
            return False
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

            if getattr(self, "_force_decodebin", False):
                # Last-resort path supports the file's actual codec instead of
                # assuming every MP4 contains H.264.
                pipeline = (
                    f'filesrc location="{self.source_address}" '
                    f"! decodebin name=dec ! videoconvert"
                )
                self.logger.info(
                    f"Using decodebin fallback for {self.source_names}"
                )
            elif use_nvdec:
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
            # leaky=downstream: a stalled muxer must not block RTSP teardown / set_state(NULL).
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
            # leaky=downstream: a stalled muxer must not block RTSP teardown / set_state(NULL).
            common_tail += " t. ! queue name=recording_queue max-size-buffers=5 max-size-bytes=0 max-size-time=500000000 leaky=downstream"
        else:
            common_tail += " ! queue max-size-buffers=10 max-size-bytes=0 max-size-time=0 ! video/x-raw,format=BGR ! appsink name=sink emit-signals=true wait-on-eos=false enable-last-sample=false sync=true max-buffers=3 drop=true"

        h264_candidate = (
            f"{base_rtsp} ! rtph264depay ! h264parse ! avdec_h264{common_tail}"
        )
        h265_candidate = (
            f"{base_rtsp} ! rtph265depay ! h265parse ! avdec_h265{common_tail}"
        )

        # Starting PLAYING is asynchronous for RTSP, so the first candidate must
        # match the common codec or the pipeline can reconnect forever before a
        # later candidate gets a chance. Prefer H.264 when no camera credentials
        # identify the H.265-oriented camera configuration; keep the established
        # H.265-first order for authenticated cameras.
        if self.username and self.password:
            candidates.extend((h265_candidate, h264_candidate))
        else:
            candidates.extend((h264_candidate, h265_candidate))

        return candidates

    def _gst_has(self, element_name: str) -> bool:
        """Check if GStreamer element factory exists."""
        try:
            return self.gstreamer_available and Gst.ElementFactory.find(element_name) is not None
        except Exception:
            return False

    def _format_gst_diagnostic(self, error, debug=None) -> str:
        """Keep RTSP failure details while removing any camera credentials."""
        details = str(error)
        if debug:
            details = f"{details}; {debug}"
        for secret in (getattr(self, "username", None), getattr(self, "password", None)):
            if secret:
                details = details.replace(str(secret), "****")
        return self._mask_credentials_in_pipeline(details)

    def _set_pipeline_playing(self, *, wait_for_async: bool) -> None:
        """Start a pipeline without waiting indefinitely on a source.

        Live RTSP state changes depend on network negotiation and are observed
        asynchronously through the bus and first-frame health. Finite sources
        may wait briefly for preroll, but initialization has a hard bound.
        """
        result = self.pipeline.set_state(Gst.State.PLAYING)
        if result == Gst.StateChangeReturn.FAILURE:
            raise RuntimeError("Failed to start GStreamer pipeline")
        if result != Gst.StateChangeReturn.ASYNC or not wait_for_async:
            return

        result, _state, _pending = self.pipeline.get_state(10 * Gst.SECOND)
        if result == Gst.StateChangeReturn.FAILURE:
            raise RuntimeError("GStreamer pipeline failed during startup")
        if result == Gst.StateChangeReturn.ASYNC:
            raise TimeoutError("GStreamer pipeline startup exceeded 10 seconds")

    def _init_pipeline(self):
        """
        Initialize GStreamer pipeline.
        For IP cameras, tries multiple pipeline candidates (H265, H264) until one works.
        Live RTSP transitions start asynchronously; finite sources use a bounded preroll wait.
        """
        pipeline_str = None
        # Tear down outside pipeline_lock. Holding that lock across disconnect/NULL
        # blocks grab's get_state for as long as the native call is stuck.
        # Prefer the orphan path before the "still running" gate: after abandon the
        # hung worker may still be alive, but init must rebuild without waiting.
        if getattr(self, "_pipeline_null_abandoned", False):
            # The previous NULL is orphaned. Drop the Python pointers and build
            # the next pipeline without another reinit_before_init teardown.
            self.pipeline = None
            self.bus = None
            self.appsink = None
        elif self._reconnect_teardown_still_running():
            self.logger.error(
                "Skipping pipeline rebuild for %s: previous GStreamer teardown is still running",
                self.source_names,
            )
            raise RuntimeError("GStreamer teardown still running")
        elif self.pipeline is not None or self.bus is not None or self.appsink is not None:
            self._teardown_pipeline("reinit_before_init", join_main_loop=True)
            if self._reconnect_teardown_still_running():
                raise RuntimeError("GStreamer teardown still running")
        try:
            with self.pipeline_lock:
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
                                # Drop the previous candidate outside the lifecycle lock.
                                # set_state(NULL) can block forever and must not pin pipeline_lock.
                                stale_pipeline = self.pipeline if self.pipeline else None
                                if stale_pipeline is not None:
                                    self.pipeline = None
                                    self.pipeline_lock.release()
                                    try:
                                        self._set_gst_state_null_bounded(
                                            stale_pipeline,
                                            timeout_sec=CaptureConstants.TEARDOWN_NULL_TIMEOUT_SEC,
                                            label=f"candidate:{self.source_names}",
                                        )
                                    except Exception:
                                        pass
                                    finally:
                                        self.pipeline_lock.acquire()

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
                                self._connect_appsink_callback()

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

                            # RTSP negotiation is asynchronous. Do not block before
                            # the GLib bus loop is running.
                            try:
                                self._set_pipeline_playing(wait_for_async=False)
                            except RuntimeError as e:
                                last_error = f"Failed to start pipeline candidate {i}: {self._format_gst_diagnostic(e)}"
                                continue

                            # Success! This candidate works
                            pipeline_str = candidate_str
                            if i > 1:
                                self.logger.info(f"Pipeline candidate {i} succeeded!")
                            break

                        except Exception as e:
                            details = self._format_gst_diagnostic(e)
                            self.logger.warning(f"Error with pipeline candidate {i}: {details}")
                            last_error = details
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
                    self._connect_appsink_callback()

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

                            # Recreate pipeline without recording. NULL stays outside the lock.
                            stale_pipeline = self.pipeline
                            self.pipeline = None
                            if stale_pipeline is not None:
                                self.pipeline_lock.release()
                                try:
                                    self._set_gst_state_null_bounded(
                                        stale_pipeline,
                                        timeout_sec=CaptureConstants.TEARDOWN_NULL_TIMEOUT_SEC,
                                        label=f"recording-rebuild:{self.source_names}",
                                    )
                                except Exception:
                                    pass
                                finally:
                                    self.pipeline_lock.acquire()

                            pipeline_str = self._build_pipeline()
                            self.logger.info(
                                f"GStreamer pipeline (recording disabled): {self._mask_credentials_in_pipeline(pipeline_str)}")
                            self.pipeline = Gst.parse_launch(pipeline_str)
                            if not self.pipeline:
                                raise RuntimeError("Failed to create GStreamer pipeline after disabling recording") from e
                            self.bus = self.pipeline.get_bus()
                            if self.bus is not None:
                                try:
                                    self.bus.add_signal_watch()
                                    self._bus_handler_id = self.bus.connect("message", self._on_bus_message)
                                except Exception:
                                    pass
                            self.appsink = self.pipeline.get_by_name("sink")
                            if not self.appsink:
                                raise RuntimeError("Failed to get appsink element after disabling recording") from e
                            self._connect_appsink_callback()
                        except Exception as e:
                            self.logger.error(f"Failed to setup recording branch: {e}", exc_info=True)
                            # Don't continue - recording branch must be set up before pipeline goes to PLAYING
                            raise

                    # Finite sources can preroll synchronously, with a hard timeout.
                    # Recording branch must be fully set up before this point.
                    self._set_pipeline_playing(wait_for_async=True)

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
                self._first_pts_ns = None
                # Reset performance metrics for new pipeline run
                self._perf_last_log = self._init_time
                self._perf_frame_count = 0
                self._perf_pull_total = 0.0
                self._perf_process_total = 0.0
                self._perf_pts_accum = 0.0
                self._perf_pts_count = 0
                self._perf_frame_buffer_full = 0

        except Exception as e:
            is_video_file = self.source_type == CaptureDeviceType.VideoFile
            uses_hardware_decoder = bool(
                pipeline_str and any(
                    decoder in pipeline_str
                    for decoder in ("nvh264dec", "nvv4l2decoder")
                )
            )
            uses_explicit_h264_decoder = bool(
                pipeline_str and "h264parse" in pipeline_str and "avdec_h264" in pipeline_str
            )
            fallback_message = None
            if is_video_file and uses_hardware_decoder and not self._force_sw_decoder:
                self._force_sw_decoder = True
                fallback_message = "Hardware decoder failed; retrying with software decoding"
            elif (
                is_video_file
                and uses_explicit_h264_decoder
                and not getattr(self, "_force_decodebin", False)
            ):
                self._force_decodebin = True
                fallback_message = "Explicit H.264 decoder failed; retrying with decodebin"

            if fallback_message:
                self.logger.warning(
                    "%s for %s", fallback_message, self.source_names
                )
                self._teardown_pipeline("decoder_fallback", join_main_loop=False)
                self._init_pipeline()
                return

            details = self._format_gst_diagnostic(e)
            self.logger.error(f"Failed to initialize GStreamer pipeline: {details}")
            if pipeline_str:
                self.logger.error(
                    f"Pipeline string was: {self._mask_credentials_in_pipeline(pipeline_str)}"
                )
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
                        # A file loop starts a new media/frame generation even
                        # though the configured source remains available.
                        self._record_reconnect(datetime.datetime.now())
                        self._first_pts_ns = None
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
                    self._note_capture_down()
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
                            self._note_capture_down()
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
                        self._note_capture_down()
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

    def _connect_appsink_callback(self) -> None:
        """Connect new-sample and stamp the active pipeline generation."""
        try:
            self._appsink_handler_id = self.appsink.connect("new-sample", self._on_new_sample)
            self._appsink_generation = getattr(self, "_pipeline_generation", 0)
        except Exception:
            self._appsink_handler_id = None

    def _flush_recording_queue(self, pipeline, generation: int | None = None) -> None:
        """Best-effort unblock of the recording branch before set_state(NULL)."""
        if pipeline is None or Gst is None:
            return
        try:
            queue = pipeline.get_by_name("recording_queue")
        except Exception:
            queue = None
        if queue is None:
            return
        try:
            queue.set_property("leaky", 2)  # downstream
        except Exception:
            pass
        for pad_name in ("sink", "src"):
            try:
                pad = queue.get_static_pad(pad_name)
                if pad is None:
                    continue
                pad.send_event(Gst.Event.new_flush_start())
                pad.send_event(Gst.Event.new_flush_stop(True))
            except Exception:
                pass
        self._set_gst_state_null_bounded(
            queue,
            timeout_sec=min(2.0, CaptureConstants.TEARDOWN_NULL_TIMEOUT_SEC),
            label=f"recording_queue:{self.source_names}",
            generation=generation,
        )

    def _set_gst_state_null_bounded(self, element, *, timeout_sec: float, label: str, generation: int | None = None) -> bool:
        """Move an element to NULL without hanging Python when a streaming thread is stuck."""
        if element is None or Gst is None:
            return True
        done = threading.Event()
        error: list[BaseException] = []
        reached_null = {"ok": False}

        def _worker():
            try:
                element.set_state(Gst.State.NULL)
                try:
                    # Prefer a bounded wait when the state change is asynchronous.
                    _ret, state, _pending = element.get_state(max(1, int(timeout_sec * Gst.SECOND)))
                    reached_null["ok"] = state == Gst.State.NULL
                except Exception:
                    # Fall back to a zero-timeout probe if the typed get_state failed.
                    reached_null["ok"] = self._gst_element_is_null(element)
            except BaseException as exc:  # noqa: BLE001 - must always unblock waiter
                error.append(exc)
            finally:
                done.set()

        worker = threading.Thread(target=_worker, name=f"gst-null-{label}"[:40], daemon=True)
        worker.start()
        if done.wait(timeout_sec + 0.5):
            if error:
                try:
                    self.logger.debug("GStreamer set_state(NULL) error for %s: %s", label, error[0])
                except Exception:
                    pass
                self._orphan_gst_native(element)
                try:
                    if generation is None or int(getattr(self, "_pipeline_generation", 0)) == int(generation):
                        self._pipeline_null_abandoned = True
                except Exception:
                    pass
                return False
            if reached_null["ok"] or self._gst_element_is_null(element):
                return True
            try:
                self.logger.error(
                    "GStreamer set_state(NULL) finished without NULL for %s; orphaning native element",
                    label,
                )
            except Exception:
                pass
            self._orphan_gst_native(element)
            try:
                if generation is None or int(getattr(self, "_pipeline_generation", 0)) == int(generation):
                    self._pipeline_null_abandoned = True
            except Exception:
                pass
            return False
        try:
            self.logger.error(
                "GStreamer set_state(NULL) timed out after %.1fs for %s; abandoning native element",
                timeout_sec,
                label,
            )
        except Exception:
            pass
        # Pin the element: the hung set_state thread may still hold a ref, but
        # callers must not assume they can drop theirs without aborting the process.
        self._orphan_gst_native(element)
        try:
            if generation is None or int(getattr(self, "_pipeline_generation", 0)) == int(generation):
                self._pipeline_null_abandoned = True
        except Exception:
            pass
        return False

    def _generation_is_current(self, generation: int) -> bool:
        return int(getattr(self, "_pipeline_generation", 0)) == int(generation)

    def _detach_pipeline_state(self, reason: str, expected_generation: int | None = None) -> dict:
        """Drop Python references. Must stay free of GStreamer calls."""
        with self.pipeline_lock:
            current = int(getattr(self, "_pipeline_generation", 0))
            if expected_generation is not None and current != int(expected_generation):
                return {
                    "reason": reason,
                    "generation": current,
                    "pipeline": None,
                    "bus": None,
                    "appsink": None,
                    "skipped": True,
                }
            state = {
                "reason": reason,
                "generation": int(getattr(self, "_pipeline_generation", 0)),
                "pipeline": self.pipeline,
                "bus": self.bus,
                "appsink": self.appsink,
                "bus_handler_id": self._bus_handler_id,
                "appsink_handler_id": self._appsink_handler_id,
                "loop": getattr(self, "loop", None),
                "main_loop_thread": getattr(self, "main_loop_thread", None),
                "recorder": getattr(self, "_gst_continuous_recorder", None),
            }
            self.pipeline = None
            self.bus = None
            self.appsink = None
            self._bus_handler_id = None
            self._appsink_handler_id = None
            self.loop = None
            self.main_loop_thread = None
            self._gst_continuous_recorder = None
            self.is_inited = False
            self.is_working = False
            self._last_sample_wall_ts = 0.0
        return state

    def _native_teardown_body(self, state: dict, *, join_main_loop: bool) -> None:
        """GStreamer cleanup of an already-detached pipeline. Does not hold lifecycle locks."""
        pipeline = state.get("pipeline")
        bus = state.get("bus")
        appsink = state.get("appsink")
        generation = state.get("generation", 0)
        reason = state.get("reason") or ""

        try:
            self.logger.info(
                "GStreamer teardown for %s: reason=%s, join_main_loop=%s, "
                "had_pipeline=%s, had_bus=%s, had_sink=%s, bus_handler_id=%s, appsink_handler_id=%s",
                self.source_names,
                reason,
                join_main_loop,
                pipeline is not None,
                bus is not None,
                appsink is not None,
                state.get("bus_handler_id"),
                state.get("appsink_handler_id"),
            )
        except Exception:
            pass

        try:
            if appsink is not None:
                try:
                    appsink.set_property("emit-signals", False)
                except Exception:
                    pass
                handler_id = state.get("appsink_handler_id")
                if handler_id is not None:
                    try:
                        appsink.disconnect(handler_id)
                    except Exception:
                        pass
        except Exception:
            pass

        try:
            if bus is not None:
                handler_id = state.get("bus_handler_id")
                if handler_id is not None:
                    try:
                        bus.disconnect(handler_id)
                    except Exception:
                        pass
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

        try:
            self._flush_recording_queue(pipeline, generation)
        except Exception:
            pass

        abandoned = False
        try:
            cancel = getattr(self, "_teardown_cancel", None)
            abandoned = bool(cancel is not None and cancel.is_set()) or (
                not self._generation_is_current(generation)
            )
        except Exception:
            abandoned = not self._generation_is_current(generation)

        # Capture-pipeline teardowns must not finalize/NULL an open splitmux:
        # qtmux/mp4mux rewrites incomplete fragments to 0B even when the source
        # has already gone quiet and finalize looks "stable" before abandon.
        had_recorder = state.get("recorder") is not None
        try:
            recorder = state.get("recorder")
            if recorder is not None and pipeline is not None:
                try:
                    recorder.stop_with_pipeline(
                        pipeline=pipeline,
                        Gst=Gst,
                        finalize=False,
                        cancel_event=getattr(self, "_teardown_cancel", None),
                    )
                except Exception:
                    pass
            # Do not run a second finalize via _cleanup_recording_branch here.
        except Exception:
            pass

        if self._generation_is_current(generation):
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

        try:
            loop = state.get("loop")
            thread = state.get("main_loop_thread")
            if loop is not None and loop.is_running():
                loop.quit()
            if join_main_loop and thread is not None and thread.is_alive():
                if threading.current_thread() is not thread:
                    thread.join(timeout=2.0)
        except Exception:
            pass

        if self._generation_is_current(generation):
            try:
                self._stop_notify_worker()
            except Exception:
                pass

        if pipeline is not None:
            # Pipeline NULL also NULLs splitmuxsink children and truncates open
            # fragments. When a recorder branch was attached, always orphan.
            skip_null = bool(
                had_recorder
                or abandoned
                or (
                    getattr(self, "_teardown_cancel", None) is not None
                    and self._teardown_cancel.is_set()
                )
            )
            if skip_null:
                self._orphan_gst_native(
                    pipeline,
                    bus,
                    appsink,
                    state.get("loop"),
                    state.get("recorder"),
                )
                try:
                    self.logger.error(
                        "Skipping pipeline NULL to preserve recording for %s "
                        "(reason=%s, generation=%s, had_recorder=%s, abandoned=%s)",
                        self.source_names,
                        reason,
                        generation,
                        had_recorder,
                        abandoned,
                    )
                except Exception:
                    pass
                try:
                    self._pipeline_null_abandoned = True
                except Exception:
                    pass
            else:
                null_ok = self._set_gst_state_null_bounded(
                    pipeline,
                    timeout_sec=CaptureConstants.TEARDOWN_NULL_TIMEOUT_SEC,
                    label=f"pipeline:{self.source_names}:gen={generation}",
                    generation=generation,
                )
                if not null_ok:
                    # Do not let Python drop the last refs to a non-NULL pipeline.
                    self._orphan_gst_native(
                        pipeline,
                        bus,
                        appsink,
                        state.get("loop"),
                        state.get("recorder"),
                    )
                    try:
                        self.logger.error(
                            "Abandoned GStreamer pipeline for %s after NULL timeout (reason=%s, generation=%s)",
                            self.source_names,
                            reason,
                            generation,
                        )
                    except Exception:
                        pass
        try:
            if self._generation_is_current(generation):
                self._maybe_schedule_malloc_trim(reason=reason)
        except Exception:
            pass
        try:
            if reason and self._generation_is_current(generation):
                self.logger.debug("Teardown completed for %s: reason=%s", self.source_names, reason)
        except Exception:
            pass

    def _teardown_pipeline(
        self,
        reason: str,
        *,
        join_main_loop: bool,
        expected_generation: int | None = None,
    ) -> None:
        """
        Detach the pipeline, then run native cleanup with a hard budget.

        The caller must not hold `_release_lock` or `pipeline_lock`. A stuck
        GStreamer call cannot keep those locks, and a late native thread does
        not write fields that belong to a newer generation.
        """
        if not self.gstreamer_available:
            return
        state = self._detach_pipeline_state(reason, expected_generation=expected_generation)
        if state.get("skipped"):
            return
        if (
            state.get("pipeline") is None
            and state.get("bus") is None
            and state.get("appsink") is None
        ):
            return
        done = threading.Event()

        def _worker():
            try:
                self._native_teardown_body(state, join_main_loop=join_main_loop)
            finally:
                done.set()

        worker = threading.Thread(
            target=_worker,
            name=f"gst-teardown-{reason}"[:40],
            daemon=True,
        )
        self._gst_teardown_thread = worker
        worker.start()
        budget = float(getattr(CaptureConstants, "TEARDOWN_BUDGET_SEC", 15.0))
        if done.wait(budget):
            return
        try:
            self.logger.error(
                "GStreamer teardown budget %.1fs exceeded for %s (reason=%s, generation=%s)",
                budget,
                self.source_names,
                reason,
                state.get("generation"),
            )
        except Exception:
            pass
        # Signal in-flight stop_with_pipeline to skip splitmux NULL (preserves bytes).
        try:
            cancel = getattr(self, "_teardown_cancel", None)
            if cancel is not None:
                cancel.set()
        except Exception:
            pass
        # Worker is still running (or about to drop locals). Pin native objects now
        # so a late return from set_state(NULL) cannot dispose a PLAYING pipeline.
        self._orphan_gst_native(
            state.get("pipeline"),
            state.get("bus"),
            state.get("appsink"),
            state.get("loop"),
            state.get("recorder"),
        )
        if self._generation_is_current(state.get("generation", 0)):
            self._pipeline_null_abandoned = True
        # Forget the hung worker so init/rebuild can proceed with orphaned refs.
        # Leaving `_gst_teardown_thread` alive forever blocked Cam4/Cam5 reconnect.
        detach = getattr(self, "_detach_abandoned_teardown_workers", None)
        if callable(detach):
            detach()
        else:
            self._gst_teardown_thread = None
