"""GStreamer capture mixin — see video_capture_gstreamer.py."""

from __future__ import annotations

from .gstreamer_capture_common import (
    Gst,
    GstContinuousRecorder,
    SourceMeta,
    threading,
    time,
)


class _RecordingFilesystemError(RuntimeError):
    """Raised when recording output directory is not writable/available."""


class GStreamerCaptureRecordingMixin:
    def _setup_recording_branch(self):
        """Setup recording branch using tee output - encode and record to splitmuxsink"""
        # `enabled` is a master switch. Continuous recording must be explicitly enabled.
        continuous_enabled = bool(
            self.recording_params
            and self.recording_params.enabled
            and self.recording_params.continuous_recording_enabled
        )
        if not continuous_enabled:
            return

        try:
            # Preferred path: delegate to decoupled recorder
            try:
                if self._gst_continuous_recorder is None:
                    self._gst_continuous_recorder = GstContinuousRecorder()
                # Build minimal SourceMeta for path generation
                try:
                    src_name = (self.source_names[0] if self.source_names else "source")
                except Exception:
                    src_name = "source"
                meta = SourceMeta(
                    source_name=src_name,
                    source_address=self.source_address,
                    source_type=str(self.source_type),
                    width=None,
                    height=None,
                    fps=self.source_fps,
                    source_names=self.source_names,
                    source_ids=self.source_ids,
                )
                self._gst_continuous_recorder.start(meta, self.recording_params)

                recording_queue = self.pipeline.get_by_name("recording_queue")
                if not recording_queue:
                    raise RuntimeError("Failed to get recording_queue element")
                self._recording_queue_elem = recording_queue
                self._gst_continuous_recorder.start_with_pipeline(
                    pipeline=self.pipeline,
                    recording_queue_elem=recording_queue,
                    Gst=Gst,
                )
                return
            except Exception:
                # fall back to legacy inline implementation below
                pass

            # Clean up existing recording branch if any (prevent duplicates)
            if self._recording_elements:
                self._cleanup_recording_branch()

            from pathlib import Path
            import datetime as _dt

            # Get recording queue element
            recording_queue = self.pipeline.get_by_name("recording_queue")
            if not recording_queue:
                raise RuntimeError("Failed to get recording_queue element")
            self._recording_queue_elem = recording_queue

            # Create recording elements
            videoconvert = Gst.ElementFactory.make("videoconvert", "recording_videoconvert")
            if not videoconvert:
                raise RuntimeError("Failed to create videoconvert element")
            x264enc = Gst.ElementFactory.make("x264enc", "recording_x264enc")
            if not x264enc:
                raise RuntimeError("Failed to create x264enc element")
            x264enc.set_property("tune", "zerolatency")
            x264enc.set_property("speed-preset", "ultrafast")
            x264enc.set_property("bitrate", 2000)

            h264parse = Gst.ElementFactory.make("h264parse", "recording_h264parse")
            if not h264parse:
                raise RuntimeError("Failed to create h264parse element")
            queue_before_mux = Gst.ElementFactory.make("queue", "recording_queue_before_mux")
            if not queue_before_mux:
                raise RuntimeError("Failed to create queue element")
            # IMPORTANT: bound mux queue to avoid runaway RSS if mux/disk stalls.
            try:
                queue_before_mux.set_property("max-size-buffers", 200)
                queue_before_mux.set_property("max-size-bytes", 5 * 1024 * 1024)
                queue_before_mux.set_property("max-size-time", 2_000_000_000)
                queue_before_mux.set_property("leaky", 0)
            except Exception:
                pass

            # Create splitmuxsink
            splitmuxsink = Gst.ElementFactory.make("splitmuxsink", "recording_splitmuxsink")
            if not splitmuxsink:
                raise RuntimeError("Failed to create splitmuxsink element")
            splitmuxsink.set_property("max-size-time", self.recording_params.segment_length_sec * 1000000000)
            splitmuxsink.set_property("muxer-factory",
                                      "mp4mux" if self.recording_params.container.lower() == "mp4" else "matroskamux")
            splitmuxsink.set_property("async-finalize", True)

            # Compose camera folder name from all source_names or source_ids
            if self.source_names and len(self.source_names) > 0:
                camera_folder = "-".join(self.source_names)
            elif self.source_ids and len(self.source_ids) > 0:
                camera_folder = "-".join(str(sid) for sid in self.source_ids)
            else:
                camera_folder = "source"

            # Build output path with camera name subfolder
            # Create path: base/Streams/YYYY-MM-DD/CameraName/
            # recording_params.out_dir should always be set to database.image_dir by Controller
            base_dir = Path(self.recording_params.out_dir) if self.recording_params.out_dir else Path("EvilEyeData")
            date_dir = _dt.datetime.now().strftime("%Y-%m-%d")
            out_dir = base_dir / "Streams" / date_dir / camera_folder
            try:
                out_dir.mkdir(parents=True, exist_ok=True)
            except (PermissionError, FileNotFoundError, OSError) as e:
                # Convert to a known error type so caller can disable recording and continue without flood
                raise _RecordingFilesystemError(str(e)) from e

            ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            source_name = (self.source_names[0] if self.source_names else camera_folder)
            name = self.recording_params.filename_tmpl.format(
                source_name=source_name,
                start_time=ts,
                seq=0,
                ext=self.recording_params.container,
            )
            stem = (out_dir / name).with_suffix("")
            location = str(stem) + "_%05d." + self.recording_params.container
            splitmuxsink.set_property("location", location)

            # Store recording directory and min_file_size_kb for periodic file checking
            self._recording_out_dir = out_dir
            self._recording_min_file_size_kb = self.recording_params.min_file_size_kb
            self._recording_location_pattern = location
            self._recording_container = self.recording_params.container
            self._recording_checked_files = set()  # Track already checked files
            self._recording_elements = [videoconvert, x264enc, h264parse, queue_before_mux, splitmuxsink]
            self._recording_check_thread = None
            self._recording_check_stop = False

            # Start periodic thread to check for new small files (only after pipeline is PLAYING)
            def check_small_files_periodically():
                """Periodically check for newly created small files and delete them"""
                while not self._recording_check_stop and self.run_flag:
                    try:
                        if not self._recording_out_dir or not self._recording_out_dir.exists():
                            time.sleep(5.0)
                            continue

                        # Get all video files in recording directory
                        from evileye.video_recorder.utils import check_and_delete_small_files
                        validate_integrity = getattr(self.recording_params, 'validate_video_integrity', True)
                        validation_timeout = getattr(self.recording_params, 'video_validation_timeout', 2.0)

                        for file_path in self._recording_out_dir.glob(f"*.{self._recording_container}"):
                            if file_path in self._recording_checked_files:
                                continue

                            # Try to delete small/invalid files (only if not active per util's min_age rule)
                            # Also validate integrity if enabled
                            deleted = check_and_delete_small_files(
                                file_path,
                                self._recording_min_file_size_kb,
                                validate_integrity=validate_integrity,
                                validation_timeout=validation_timeout
                            )
                            if deleted:
                                # Determine reason for deletion
                                if '%' in file_path.name:
                                    reason = "invalid name pattern"
                                else:
                                    try:
                                        stat = file_path.stat()
                                        file_size_kb = stat.st_size / 1024.0
                                        if file_size_kb < self._recording_min_file_size_kb:
                                            reason = f"size < {self._recording_min_file_size_kb} KB"
                                        else:
                                            reason = "corrupted/invalid video file"
                                    except Exception:
                                        reason = "corrupted/invalid video file"
                                self.logger.info(f"Deleted recording file: {file_path} ({reason})")
                                continue

                            # If not deleted, add to checked only if file is mature (avoid skipping future checks when still active)
                            try:
                                stat = file_path.stat()
                                file_age = time.time() - stat.st_mtime
                                if file_age >= 60.0:  # consider mature after 60s
                                    self._recording_checked_files.add(file_path)
                            except Exception:
                                pass
                    except Exception as e:
                        self.logger.error(f"Error checking small files: {e}")

                    time.sleep(5.0)  # Check every 5 seconds

            # Store thread reference (will be started after pipeline is PLAYING)
            self._recording_check_thread = threading.Thread(target=check_small_files_periodically, daemon=True)

            self.logger.info(f"Recording branch location: {location}")

            # Check pipeline state before adding elements - elements should be added when pipeline is NULL or READY
            # Note: This method is called from _init_pipeline() which already holds pipeline_lock, so we don't acquire it here
            if not self.pipeline:
                raise RuntimeError("Pipeline is None, cannot setup recording branch")

            # Get current pipeline state (use timeout to avoid blocking)
            ret, current_state, pending_state = self.pipeline.get_state(Gst.SECOND)
            if ret == Gst.StateChangeReturn.FAILURE:
                raise RuntimeError("Failed to get pipeline state")

            # If pipeline is PLAYING or PAUSED, we need to handle state change carefully
            # Elements should ideally be added when pipeline is NULL or READY
            if current_state in (Gst.State.PLAYING, Gst.State.PAUSED):
                self.logger.warning(
                    f"Pipeline is in {current_state.value_nick} state when adding recording elements - this may cause issues")

            # Add elements to pipeline
            self.pipeline.add(videoconvert)
            self.pipeline.add(x264enc)
            self.pipeline.add(h264parse)
            self.pipeline.add(queue_before_mux)
            self.pipeline.add(splitmuxsink)

            # Check caps compatibility before linking
            # Get src pad from recording_queue to check caps
            try:
                recording_queue_src = recording_queue.get_static_pad("src")
                if recording_queue_src:
                    recording_queue_src.get_current_caps()
            except Exception:
                pass

            # Link elements with error checking
            # Check if recording_queue is already linked (should not be, but check anyway)
            try:
                recording_queue_src_pad = recording_queue.get_static_pad("src")
                if recording_queue_src_pad:
                    peer = recording_queue_src_pad.get_peer()
                    if peer:
                        self.logger.warning(
                            f"recording_queue src pad is already linked to {peer.get_parent().get_name() if peer.get_parent() else 'unknown'}, unlinking first")
                        recording_queue_src_pad.unlink(peer)
            except Exception:
                pass

            link_ok = True

            try:
                if not recording_queue.link(videoconvert):
                    self.logger.error("Failed to link recording_queue -> videoconvert")
                    link_ok = False
            except Exception as link_err:
                self.logger.error(f"Exception linking recording_queue -> videoconvert: {link_err}")
                link_ok = False

            if link_ok:
                try:
                    if not videoconvert.link(x264enc):
                        self.logger.error("Failed to link videoconvert -> x264enc")
                        link_ok = False
                except Exception as link_err:
                    self.logger.error(f"Exception linking videoconvert -> x264enc: {link_err}")
                    link_ok = False

            if link_ok:
                try:
                    if not x264enc.link(h264parse):
                        self.logger.error("Failed to link x264enc -> h264parse")
                        link_ok = False
                except Exception as link_err:
                    self.logger.error(f"Exception linking x264enc -> h264parse: {link_err}")
                    link_ok = False

            if link_ok:
                try:
                    if not h264parse.link(queue_before_mux):
                        self.logger.error("Failed to link h264parse -> queue_before_mux")
                        link_ok = False
                except Exception as link_err:
                    self.logger.error(f"Exception linking h264parse -> queue_before_mux: {link_err}")
                    link_ok = False

            if link_ok:
                try:
                    if not queue_before_mux.link(splitmuxsink):
                        self.logger.error("Failed to link queue_before_mux -> splitmuxsink")
                        link_ok = False
                except Exception as link_err:
                    self.logger.error(f"Exception linking queue_before_mux -> splitmuxsink: {link_err}")
                    link_ok = False

            if not link_ok:
                # Clean up partially linked elements
                self.logger.error("Failed to link recording branch elements, cleaning up...")
                try:
                    self._cleanup_recording_branch()
                except Exception as cleanup_err:
                    self.logger.error(f"Error during cleanup after failed linking: {cleanup_err}")
                raise RuntimeError("Failed to link recording branch elements")

            self._attach_legacy_first_mux_probe(queue_before_mux, location)

            # Verify that all links are actually established
            # Check the entire chain from recording_queue to splitmuxsink
            try:
                recording_queue_src = recording_queue.get_static_pad("src")
                if not recording_queue_src:
                    raise RuntimeError("recording_queue has no src pad")

                peer = recording_queue_src.get_peer()
                if not peer:
                    raise RuntimeError("recording_queue src pad is not linked")

                videoconvert_elem = peer.get_parent()
                if videoconvert_elem != videoconvert:
                    raise RuntimeError(
                        f"recording_queue is linked to wrong element: {videoconvert_elem.get_name() if videoconvert_elem else 'None'}")

                # Check the rest of the chain
                videoconvert_src = videoconvert.get_static_pad("src")
                if videoconvert_src:
                    x264enc_peer = videoconvert_src.get_peer()
                    if not x264enc_peer or x264enc_peer.get_parent() != x264enc:
                        raise RuntimeError("videoconvert is not properly linked to x264enc")
            except Exception as verify_err:
                self.logger.error(f"Failed to verify recording branch links: {verify_err}")
                try:
                    self._cleanup_recording_branch()
                except Exception as cleanup_err:
                    self.logger.error(f"Error during cleanup after verification failure: {cleanup_err}")
                raise RuntimeError(f"Recording branch verification failed: {verify_err}")

            # Sync state of elements with pipeline parent
            # This is safe to do when pipeline is NULL or READY, but may cause issues if PLAYING
            # We do it conditionally based on pipeline state
            # Note: This method is called from _init_pipeline() which already holds pipeline_lock, so we don't acquire it here
            ret, current_state, pending_state = self.pipeline.get_state(Gst.SECOND)
            if ret != Gst.StateChangeReturn.FAILURE:
                if current_state in (Gst.State.NULL, Gst.State.READY):
                    # Safe to sync state when pipeline is NULL or READY
                    try:
                        for elem in self._recording_elements:
                            elem.sync_state_with_parent()
                    except Exception as sync_err:
                        self.logger.warning(f"Failed to sync recording elements state: {sync_err}")
                        # Don't fail setup if sync fails - elements will sync automatically when pipeline goes to PLAYING
                else:
                    # Pipeline is PLAYING or PAUSED - elements will sync automatically when pipeline state changes
                    self.logger.debug("Pipeline is PLAYING/PAUSED - elements will sync automatically on state change")

            self.logger.info("Recording branch setup successfully")

        except Exception as e:
            # Avoid traceback flood for known filesystem issues; the caller will handle disabling recording.
            if isinstance(e, _RecordingFilesystemError):
                raise
            self.logger.error(f"Error setting up recording branch: {e}", exc_info=True)
            raise

    def _attach_legacy_first_mux_probe(self, queue_before_mux, location: str) -> None:
        from evileye.video_recorder.session_sidecar import (
            sidecar_path_from_splitmux_location,
            write_session_sidecar,
        )

        sidecar = sidecar_path_from_splitmux_location(location)
        state = {"written": False}

        def _on_buffer(pad, info):
            if state["written"]:
                return Gst.PadProbeReturn.OK
            buf = info.get_buffer()
            if buf is None:
                return Gst.PadProbeReturn.OK
            pts = getattr(buf, "pts", None)
            first_pts = None
            try:
                clock_none = getattr(Gst, "CLOCK_TIME_NONE", None)
                if pts is not None and pts >= 0 and (clock_none is None or pts != clock_none):
                    first_pts = int(pts)
            except Exception:
                first_pts = None
            try:
                write_session_sidecar(sidecar, time.time(), first_pts)
            except Exception:
                self.logger.exception("Failed to write session sidecar %s", sidecar)
            state["written"] = True
            for elem in (getattr(self, "_recording_queue_elem", None), queue_before_mux):
                if elem is None:
                    continue
                try:
                    elem.set_property("leaky", 2)
                except Exception:
                    pass
            return Gst.PadProbeReturn.REMOVE

        try:
            srcpad = queue_before_mux.get_static_pad("src")
            if srcpad is None:
                return
            srcpad.add_probe(Gst.PadProbeType.BUFFER, _on_buffer)
        except Exception:
            self.logger.exception("Failed to attach first-mux probe")

    def _cleanup_recording_branch(self, *, pipeline=None):
        """Clean up recording branch elements"""
        try:
            try:
                if self._gst_continuous_recorder is not None and pipeline is not None:
                    self._gst_continuous_recorder.stop_with_pipeline(pipeline=pipeline, Gst=Gst)
            except Exception:
                pass

            # Stop periodic check thread
            if self._recording_check_thread:
                self._recording_check_stop = True
                if self._recording_check_thread.is_alive():
                    self._recording_check_thread.join(timeout=2.0)
                self._recording_check_thread = None

            # Clean up recording elements
            # Note: Try to acquire lock, but don't block if it's already held (e.g., during pipeline shutdown)
            # Standard threading.Lock doesn't support timeout, so we use non-blocking acquire
            if pipeline is None:
                try:
                    # Try to acquire lock without blocking to avoid deadlock
                    lock_acquired = self.pipeline_lock.acquire(blocking=False)
                    try:
                        pipeline = self.pipeline
                    finally:
                        if lock_acquired:
                            self.pipeline_lock.release()
                    if not lock_acquired:
                        # Lock is held, get pipeline reference without lock (may be None, but that's OK)
                        # This is safe because we're only reading the reference, not modifying it
                        pipeline = self.pipeline
                except Exception:
                    # Fallback: get pipeline reference without lock
                    pipeline = self.pipeline

            if self._recording_elements:
                for elem in self._recording_elements:
                    try:
                        if not elem:
                            continue

                        # Set element state to NULL before removing
                        # This will automatically unlink all pads - no need to unlink manually
                        try:
                            ret = elem.set_state(Gst.State.NULL)
                            if ret == Gst.StateChangeReturn.ASYNC:
                                # Wait for state change to complete
                                elem.get_state(Gst.CLOCK_TIME_NONE)
                        except Exception:
                            pass

                        # Remove element from pipeline if pipeline exists
                        if pipeline:
                            try:
                                # Check if element is still in pipeline before removing
                                parent = elem.get_parent()
                                if parent == pipeline:
                                    pipeline.remove(elem)
                            except Exception:
                                # Element might already be removed or pipeline might be None
                                pass

                    except Exception:
                        pass

                self._recording_elements = []

            # Clear recording-related attributes
            self._recording_out_dir = None
            self._recording_checked_files = set()
            self._recording_check_stop = False
            self._recording_queue_elem = None

        except Exception as e:
            self.logger.error(f"Error cleaning up recording branch: {e}", exc_info=True)
