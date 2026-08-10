"""GStreamer capture mixin — see video_capture_gstreamer.py."""

from __future__ import annotations

from .gstreamer_capture_common import (
    CaptureConstants,
    CaptureDeviceType,
    CaptureImage,
    Empty,
    Frame,
    Full,
    Gst,
    List,
    Optional,
    Queue,
    Tuple,
    datetime,
    deque,
    np,
    threading,
    time,
)


class GStreamerCaptureFramesMixin:
    def _extract_frame_data(self, sample: Any) -> Tuple[np.ndarray, int, int, Optional[float]]:
        """Extract frame data from GStreamer sample.
        
        Args:
            sample: GStreamer sample object
            
        Returns:
            Tuple of (frame_data, width, height, pts_value)
            
        Raises:
            Exception: If frame extraction fails
        """
        buffer = sample.get_buffer()
        caps = sample.get_caps()
        pts_value = buffer.pts if buffer else None

        # Get frame dimensions
        structure = caps.get_structure(0)
        width = structure.get_int("width")[1]
        height = structure.get_int("height")[1]

        # Try to get FPS from caps if not set (optimized: only check once per session)
        # Cache structure check to avoid repeated field lookups
        if self.source_fps is None and structure is not None:
            try:
                if structure.has_field("framerate"):
                    num, den = structure.get_fraction("framerate")
                    if den != 0:
                        self.source_fps = float(num) / float(den)
            except Exception:
                pass

        # Map buffer and extract frame data
        map_info = None
        try:
            success, map_info = buffer.map(Gst.MapFlags.READ)
            if not success:
                raise RuntimeError("Failed to map buffer")

            # Convert buffer to numpy array
            frame_data = np.frombuffer(map_info.data, dtype=np.uint8)
            frame_data = frame_data.reshape((height, width, 3))

            # Copy is necessary: GStreamer buffer is read-only and may be reused
            # Copy once here to avoid issues with split_stream, recording, and subscriber processing
            frame_data = frame_data.copy()

            return frame_data, width, height, pts_value
        finally:
            # Always unmap buffer to prevent memory leaks
            if map_info is not None:
                try:
                    buffer.unmap(map_info)
                except Exception:
                    pass

    def _grab_frames(self):
        """
        Monitor pipeline state and reconnect if needed (similar to OpenCV reconnect logic).
        """
        while self.run_flag and not self.stop_event.is_set():
            if not self.is_inited or self.pipeline is None:
                # Check if reconnection is already in progress (for both IP cameras and video files)
                if self._reconnecting:
                    self.logger.debug(f"Reconnection already in progress for {self.source_names}, waiting...")
                    time.sleep(CaptureConstants.RECONNECT_SLEEP_LONG)
                    continue

                # For IP cameras, use reconnect loop instead of direct init()
                if self.source_type == CaptureDeviceType.IpCamera:
                    self.logger.info(
                        f"Source {self.source_names} not initialized (is_inited={self.is_inited}, pipeline={self.pipeline is not None}), starting reconnect loop")
                    threading.Thread(target=self._reconnect_loop, daemon=True).start()
                    # Wait a bit before checking again
                    time.sleep(CaptureConstants.RECONNECT_MONITOR_INTERVAL)
                else:
                    # For video files, try direct init with backoff (same scheme as OpenCV and _reconnect_loop)
                    self.logger.debug(
                        f"Video file {self.source_names} not initialized (is_inited={self.is_inited}, pipeline={self.pipeline is not None}), attempting reconnect")
                    try:
                        cfg = (self.params or {}).get('reconnect', {})
                    except Exception:
                        cfg = {}
                    # IMPORTANT: For VideoFile sources (especially with loop_play), long reconnect backoff
                    # translates directly into 30-60s "stalls" after restarts. Use fast defaults unless
                    # the user explicitly overrides reconnect params.
                    fast_defaults = {
                        "initial_delay_sec": 0.5,
                        "backoff_step_sec": 1.0,
                        "max_delay_sec": 5.0,
                    }
                    initial_delay_sec = float(cfg.get('initial_delay_sec', fast_defaults["initial_delay_sec"]))
                    backoff_step_sec = float(cfg.get('backoff_step_sec', fast_defaults["backoff_step_sec"]))
                    max_delay_sec = float(cfg.get('max_delay_sec', fast_defaults["max_delay_sec"]))
                    if self._reconnect_attempt == 0:
                        wait_time = 0.0
                    else:
                        wait_time = min(max_delay_sec,
                                        initial_delay_sec + (self._reconnect_attempt - 1) * backoff_step_sec)
                    if wait_time > 0:
                        try:
                            if wait_time >= 5.0:
                                self.logger.info(
                                    "Reconnect backoff wait %.1fs for %s (attempt=%d, cfg=%s)",
                                    wait_time,
                                    self.source_names,
                                    self._reconnect_attempt,
                                    cfg,
                                )
                        except Exception:
                            pass
                        time.sleep(wait_time)
                    if self.run_flag:
                        try:
                            if self.init():
                                self._reconnect_attempt = 0
                                timestamp = datetime.datetime.now()
                                self.logger.info(
                                    f"Reconnected to source: {self.source_names} (is_inited={self.is_inited}, is_working={self.is_working})")
                                self._record_reconnect(timestamp)
                                for sub in self.subscribers:
                                    sub.update()
                            else:
                                self._reconnect_attempt += 1
                                self.logger.warning(
                                    f"Reconnection attempt failed for {self.source_names} (init() returned False)")
                        except Exception as e:
                            self._reconnect_attempt += 1
                            self.logger.error(
                                f"Reconnection failed: {e} (is_inited={self.is_inited}, is_working={self.is_working})")
                continue

            # Active pipeline state check
            try:
                if self.pipeline:
                    ret, state, pending = self.pipeline.get_state(0)
                    # Комбинированная проверка: ret == SUCCESS И state == PLAYING для основной проверки
                    # Но если ret == FAILURE, но state == PLAYING и кадры приходят, не помечаем как "not working"
                    if ret == Gst.StateChangeReturn.SUCCESS and state == Gst.State.PLAYING:
                        # Нормальный случай: pipeline в PLAYING и get_state() вернул SUCCESS
                        # Check if we're actually receiving frames
                        now = time.time()
                        last_frame_time = 0

                        # Prefer "last sample pulled" timestamp (more reliable) and fall back to stored frames.
                        try:
                            if self._last_sample_wall_ts:
                                last_frame_time = self._last_sample_wall_ts
                        except Exception:
                            pass
                        if not last_frame_time:
                            with self.frame_lock:
                                if self.split_stream:
                                    if self.last_frame:
                                        last_frame_time = getattr(self.last_frame, 'time_stamp', 0)
                                    elif not self.frame_buffer.empty():
                                        try:
                                            temp_frame = self.frame_buffer.get_nowait()
                                            if temp_frame:
                                                last_frame_time = getattr(temp_frame, 'time_stamp', 0)
                                            try:
                                                self.frame_buffer.put_nowait(temp_frame)
                                            except Full:
                                                pass
                                        except Empty:
                                            pass
                                else:
                                    if self.last_frame:
                                        last_frame_time = getattr(self.last_frame, 'time_stamp', 0)

                        # Проверяем таймаут только если кадры действительно не приходят
                        if last_frame_time > 0:
                            time_since_last_frame = now - float(last_frame_time)
                            if time_since_last_frame > CaptureConstants.FRAME_TIMEOUT_SECONDS:
                                # No frames for timeout period
                                # Улучшенная диагностика: проверяем состояние pipeline и кадров
                                pipeline_diag = f"state={state}, ret={ret}, pending={pending}"
                                frame_diag = f"last_frame_time={last_frame_time:.3f}, time_since={time_since_last_frame:.1f}s"
                                if self.split_stream:
                                    frame_diag += f", frame_buffer_size={self.frame_buffer.qsize()}"

                                # For VideoFile with loop_play, don't stop working - trigger restart instead
                                if self.source_type == CaptureDeviceType.VideoFile and self.loop_play:
                                    if self.is_working:
                                        self.logger.warning(
                                            f"Pipeline PLAYING but no frames received after {time_since_last_frame:.1f}s "
                                            f"for {self.source_names} (VideoFile with loop_play), triggering restart. "
                                            f"Diagnostics: {pipeline_diag}, {frame_diag}"
                                        )
                                        # Don't set is_working = False for VideoFile with loop_play
                                        # Instead, trigger restart immediately (handled below)
                                    # Mark as not working temporarily to trigger restart logic
                                    self.is_working = False
                                else:
                                    # For IP cameras and other sources, mark as not working
                                    if self.is_working:
                                        self.logger.warning(
                                            f"Pipeline PLAYING but no frames received after {time_since_last_frame:.1f}s "
                                            f"for {self.source_names}, marking as not working. "
                                            f"Diagnostics: {pipeline_diag}, {frame_diag}"
                                        )
                                        self.is_working = False
                            # Если кадры приходят (time_since_last_frame <= FRAME_TIMEOUT_SECONDS), pipeline работает
                        # Если last_frame_time == 0, значит кадров еще не было - это нормально при инициализации
                    elif ret != Gst.StateChangeReturn.SUCCESS and state == Gst.State.PLAYING:
                        # Специальный случай: ret == FAILURE, но state == PLAYING
                        # Это может быть асинхронное изменение состояния
                        # Проверяем, приходят ли кадры - если да, не помечаем как "not working"
                        now = time.time()
                        last_frame_time = 0

                        with self.frame_lock:
                            if self.split_stream:
                                if self.last_frame:
                                    last_frame_time = getattr(self.last_frame, 'time_stamp', 0)
                                elif not self.frame_buffer.empty():
                                    try:
                                        temp_frame = self.frame_buffer.get_nowait()
                                        if temp_frame:
                                            last_frame_time = getattr(temp_frame, 'time_stamp', 0)
                                        try:
                                            self.frame_buffer.put_nowait(temp_frame)
                                        except Full:
                                            pass
                                    except Empty:
                                        pass
                            else:
                                if self.last_frame:
                                    last_frame_time = getattr(self.last_frame, 'time_stamp', 0)

                        if last_frame_time > 0:
                            time_since_last_frame = now - last_frame_time
                            # Если кадры приходят (time_since < таймаут), НЕ помечаем как "not working"
                            if time_since_last_frame >= CaptureConstants.FRAME_TIMEOUT_SECONDS:
                                # Кадры не приходят - помечаем как "not working"
                                if self.is_working:
                                    # Убрано отладочное сообщение для уменьшения флуда
                                    self.is_working = False
                            else:
                                # Кадры приходят (time_since < таймаут) - НЕ помечаем как "not working"
                                # Это нормальная ситуация для ret == FAILURE при асинхронном изменении состояния
                                if not self.is_working:
                                    # Восстанавливаем is_working без логирования (избегаем флуда)
                                    self.is_working = True
                        # Если last_frame_time == 0, это может быть сразу после инициализации
                        # Не помечаем как "not working" сразу, даем время на получение первого кадра
                        # Но если прошло много времени после инициализации, помечаем как "not working"
                        else:
                            # Проверяем, прошло ли время после инициализации
                            if self._init_time:
                                time_since_init = now - self._init_time
                                if time_since_init > CaptureConstants.INIT_GRACE_PERIOD_SECONDS:
                                    # Прошло достаточно времени после инициализации, но кадров нет
                                    if self.is_working:
                                        # Убрано отладочное сообщение для уменьшения флуда
                                        self.is_working = False
                            # Если _init_time нет, это может быть старая инициализация - не трогаем is_working
                    else:
                        # Pipeline not in PLAYING state или ret != SUCCESS и state != PLAYING
                        if self.is_working:
                            # Убрано отладочное сообщение для уменьшения флуда
                            pass
                        self.is_working = False
            except Exception as e:
                self.logger.debug(f"Error checking pipeline state: {e}")

            # Check if pipeline is still working and needs reconnection
            if not self.is_working:
                # For IP cameras, use reconnect loop
                if self.source_type == CaptureDeviceType.IpCamera:
                    if self.run_flag and not self._reconnecting:
                        # Улучшенная диагностика состояния потока перед реконнектом
                        pipeline_state_str = "unknown"
                        last_frame_info = "no frames"
                        should_reconnect = True
                        now = time.time()
                        try:
                            if self.pipeline:
                                ret, state, pending = self.pipeline.get_state(0)
                                pipeline_state_str = f"state={state}, ret={ret}, pending={pending}"

                                # КРИТИЧНО: Если state == PLAYING и кадры приходят, НЕ реконнектим
                                if state == Gst.State.PLAYING:
                                    try:
                                        with self.frame_lock:
                                            last_frame_time = 0
                                            if self.last_frame:
                                                last_frame_time = getattr(self.last_frame, 'time_stamp', 0)
                                            elif self.split_stream and not self.frame_buffer.empty():
                                                try:
                                                    temp_frame = self.frame_buffer.get_nowait()
                                                    if temp_frame:
                                                        last_frame_time = getattr(temp_frame, 'time_stamp', 0)
                                                    self.frame_buffer.put_nowait(temp_frame)
                                                except (Empty, Full):
                                                    pass

                                            if last_frame_time > 0:
                                                time_since_last = now - last_frame_time
                                                last_frame_info = f"last_frame_time={last_frame_time:.3f}, time_since={time_since_last:.1f}s"

                                                # Если кадры приходят (time_since < FRAME_TIMEOUT_SECONDS), НЕ реконнектим
                                                if time_since_last < CaptureConstants.FRAME_TIMEOUT_SECONDS:
                                                    should_reconnect = False
                                                    # Восстанавливаем is_working, так как pipeline работает (без логирования для уменьшения флуда)
                                                    self.is_working = True
                                            else:
                                                last_frame_info = "no frames yet"
                                    except Exception as e:
                                        last_frame_info = f"error checking frames: {e}"
                            else:
                                pipeline_state_str = "pipeline=None"
                        except Exception as e:
                            pipeline_state_str = f"error getting state: {e}"

                        # Реконнектим только если действительно нужно
                        if should_reconnect:
                            try:
                                cfg_nf = (self.params or {}).get("noframes_restart", {}) or {}
                                cfg_rc = (self.params or {}).get("reconnect", {}) or {}
                            except Exception:
                                cfg_nf, cfg_rc = {}, {}
                            min_interval = float(
                                cfg_nf.get(
                                    "min_interval_sec",
                                    cfg_rc.get(
                                        "min_interval_sec",
                                        CaptureConstants.NOFRAMES_RECONNECT_MIN_INTERVAL_SEC,
                                    ),
                                )
                            )
                            from .reconnect_policy import allow_noframes_reconnect

                            if not allow_noframes_reconnect(
                                float(getattr(self, "_noframes_restart_last_ts", 0.0) or 0.0),
                                now,
                                min_interval,
                            ):
                                should_reconnect = False
                                self.logger.info(
                                    "Skipping IpCamera reconnect for %s: cooldown "
                                    "(last_success_ago=%.1fs < min_interval=%.1fs)",
                                    self.source_names,
                                    now - float(getattr(self, "_noframes_restart_last_ts", 0.0) or 0.0),
                                    min_interval,
                                )

                        if should_reconnect and not self._reconnecting:
                            self.logger.info(
                                f"Pipeline not working, starting reconnect loop for {self.source_names}. "
                                f"Diagnostics: {pipeline_state_str}, {last_frame_info}, "
                                f"is_inited={self.is_inited}, _reconnecting={self._reconnecting}"
                            )
                            threading.Thread(target=self._reconnect_loop, daemon=True).start()
                        elif should_reconnect and self._reconnecting:
                            self.logger.debug(
                                "Reconnect already in progress for %s; not starting another thread",
                                self.source_names,
                            )
                # For video files with loop_play, check if reconnection is needed
                elif self.source_type == CaptureDeviceType.VideoFile and self.loop_play:
                    # Don't reconnect if already reconnecting (via EOS handler or previous attempt)
                    if not self._reconnecting:
                        # For VideoFile with loop_play, always restart if not working
                        # This handles cases where pipeline is valid but not receiving frames
                        with self.pipeline_lock:
                            pipeline_valid = (self.pipeline is not None)
                            pipeline_playing = False
                            if pipeline_valid:
                                try:
                                    ret, state, pending = self.pipeline.get_state(0)
                                    pipeline_playing = (
                                                ret == Gst.StateChangeReturn.SUCCESS and state == Gst.State.PLAYING)
                                except Exception:
                                    pass

                        # For VideoFile with loop_play: always restart when not working
                        # Even if pipeline appears valid and playing, if we're not receiving frames, restart
                        # This ensures continuous playback even after temporary stalls
                        # IMPORTANT: For VideoFile with loop_play, we always restart when is_working=False
                        # because the timeout means we're not receiving frames, regardless of pipeline state
                        # Anti-flap: if we are restarting too often due to "no frames", throttle restarts.
                        # Also apply a simple backoff by effectively increasing the no-frames timeout after each restart.
                        now_ts = time.time()
                        should_restart = True
                        try:
                            cfg_nf = (self.params or {}).get("noframes_restart", {})
                        except Exception:
                            cfg_nf = {}
                        # For VideoFile(loop_play) we want fast recovery: avoid large restart backoffs
                        # that cause long visible freezes between restarts.
                        min_interval_sec = float(cfg_nf.get("min_interval_sec", 1.0))
                        max_timeout_sec = float(cfg_nf.get("max_timeout_sec", 120.0))
                        base_timeout_sec = float(cfg_nf.get("base_timeout_sec", CaptureConstants.FRAME_TIMEOUT_SECONDS))

                        # If we restarted recently, don't restart again immediately.
                        if self._noframes_restart_last_ts and (
                                now_ts - self._noframes_restart_last_ts) < min_interval_sec:
                            should_restart = False
                            try:
                                self.logger.warning(
                                    f"Skipping noframes restart for {self.source_names}: "
                                    f"last_restart_ago={(now_ts - self._noframes_restart_last_ts):.1f}s < min_interval_sec={min_interval_sec:.1f}s"
                                )
                            except Exception:
                                pass

                        # For VideoFile(loop_play), do not apply multiplicative backoff here: it creates long gaps
                        # between restart attempts (tens of seconds) and makes short clips unusable.
                        effective_timeout = min(max_timeout_sec, base_timeout_sec)
                        try:
                            # Only restart if the latest observed gap is >= effective_timeout.
                            # We recompute gap quickly (best-effort) to avoid relying on earlier branch state.
                            last_seen = 0.0
                            try:
                                last_seen = float(self._last_sample_wall_ts or 0.0)
                            except Exception:
                                last_seen = 0.0
                            if not last_seen:
                                with self.frame_lock:
                                    if self.last_frame is not None:
                                        last_seen = float(getattr(self.last_frame, "time_stamp", 0) or 0.0)
                            if last_seen > 0 and (now_ts - last_seen) < effective_timeout:
                                should_restart = False
                        except Exception:
                            pass

                        if should_restart:
                            # Trigger restart similar to EOS handler
                            self._reconnecting = True
                            try:
                                self.logger.info(
                                    f"Auto-restarting pipeline for {self.source_names} after no frames "
                                    f"(pipeline_valid={pipeline_valid}, is_inited={self.is_inited}, pipeline_playing={pipeline_playing})"
                                )
                                self._restart_counter += 1
                                self._log_resource_stats("before_restart_noframes")
                                self._teardown_pipeline("noframes_auto_restart", join_main_loop=False)
                                self._noframes_restart_last_ts = now_ts
                                self._noframes_restart_consecutive += 1
                                # Reset init time to allow first frame detection after restart
                                self._init_time = None
                                time.sleep(0.1)

                                # Reinitialize pipeline
                                self._init_pipeline()

                                # Verify pipeline is actually initialized and playing
                                with self.pipeline_lock:
                                    if self.pipeline is not None:
                                        ret, state, pending = self.pipeline.get_state(0)
                                        if ret == Gst.StateChangeReturn.SUCCESS and state == Gst.State.PLAYING:
                                            # CRITICAL: Set is_inited flag after successful _init_pipeline()
                                            # is_working will be set in _on_new_sample when first frame is received
                                            self.is_inited = True
                                            self.logger.info(
                                                f"Auto-restarted pipeline for {self.source_names} after no frames "
                                                f"(is_inited={self.is_inited}, is_working={self.is_working}, state={state})"
                                            )
                                            self._log_resource_stats("after_restart_noframes")
                                            # We got back to PLAYING; keep consecutive count until first frame arrives.
                                            # Once frames arrive, _on_new_sample will mark working and the state will naturally stabilize.
                                        else:
                                            self.logger.warning(
                                                f"Auto-restart: pipeline created but not PLAYING (state={state}, ret={ret}) for {self.source_names}"
                                            )
                                            self.is_inited = False
                                            self.is_working = False
                                    else:
                                        self.logger.error(
                                            f"Auto-restart: pipeline is None after _init_pipeline() for {self.source_names}"
                                        )
                                        self.is_inited = False
                                        self.is_working = False
                            except Exception as e:
                                self.logger.error(f"Error during auto-restart for {self.source_names}: {e}",
                                                  exc_info=True)
                                self.is_inited = False
                                self.is_working = False
                            finally:
                                self._reconnecting = False
                else:
                    # If we are working again, reset noframes consecutive counter.
                    if self._noframes_restart_consecutive:
                        self._noframes_restart_consecutive = 0

            # Sleep according to monitor interval
            try:
                cfg = (self.params or {}).get('reconnect', {})
                monitor_sleep = float(cfg.get('monitor_interval_sec', CaptureConstants.RECONNECT_MONITOR_INTERVAL))
            except Exception:
                monitor_sleep = CaptureConstants.RECONNECT_MONITOR_INTERVAL
            if self.stop_event.wait(monitor_sleep):
                break

    def _notify_subscribers_async(self, capture_images: List[CaptureImage]) -> None:
        """Notify subscribers asynchronously about new frames.
        
        Optimized: Only notify if there are subscribers, and use a single thread for all notifications.
        
        Args:
            capture_images: List of CaptureImage objects to notify about
        """
        # Early exit if no subscribers - avoid unnecessary work
        if not self.subscribers:
            return

        q = self._notify_queue
        if q is None:
            return
        # Ensure worker is running (it can be stopped during teardown/reconnect)
        self._start_notify_worker()
        # Bounded queue: drop oldest batch if full to avoid memory buildup
        try:
            q.put_nowait(capture_images)
        except Full:
            try:
                q.get_nowait()
                q.task_done()
            except Exception:
                pass
            try:
                q.put_nowait(capture_images)
            except Exception:
                pass

    def _on_new_sample(self, appsink: Any) -> Any:
        """
        Callback for new frame from GStreamer pipeline.
        """
        pull_duration = 0.0
        try:
            pull_start = time.perf_counter()
            sample = appsink.emit("pull-sample")
            pull_duration = time.perf_counter() - pull_start
            if sample:
                processing_start = time.perf_counter()
                # Mark that we are actively receiving samples from GStreamer.
                # Do this early (after pull-sample succeeded) so monitoring doesn't trigger false "no frames".
                try:
                    self._last_sample_wall_ts = time.time()
                except Exception:
                    pass
                # Extract frame data first (before checking is_working)
                # This allows us to process the frame even if is_working is False initially
                try:
                    frame_data, width, height, pts_value = self._extract_frame_data(sample)
                except Exception as e:
                    process_time = time.perf_counter() - processing_start
                    self._record_perf_metrics(pull_duration, process_time, None)
                    self.logger.error(f"Failed to extract frame data: {e}")
                    return Gst.FlowReturn.ERROR

                # Process frame metadata (optimized: only if needed for video files)
                buffer = sample.get_buffer()
                # For video files, we need frame metadata; for live sources, it's optional
                if self.source_type == CaptureDeviceType.VideoFile:
                    current_video_frame, current_video_position = self._process_gstreamer_frame_metadata(buffer,
                                                                                                         frame_data)
                else:
                    # For live sources, use simpler metadata processing
                    current_video_frame = None
                    current_video_position = None

                # Maintain rolling FPS estimate as fallback (optimized: only update when needed)
                now = time.time()
                # Only update FPS estimate if not already set or if we need to recalculate
                if self.source_fps is None:
                    self._fps_times.append(now)
                    if len(self._fps_times) > 30:
                        self._fps_times.pop(0)
                    if len(self._fps_times) >= 2:
                        dt = self._fps_times[-1] - self._fps_times[0]
                        if dt > 0:
                            self.source_fps = (len(self._fps_times) - 1) / dt

                # Track callback frequency for diagnostics (optimized: only log periodically)
                self._callback_count += 1
                if now - self._callback_last_log >= 5.0:
                    source_label = ",".join(str(name) for name in self.source_names) if self.source_names else str(
                        self.source_address)
                    callback_fps = self._callback_count / (now - self._callback_last_log)
                    self.logger.debug(
                        f"Capture callback [{source_label}]: {callback_fps:.2f} callbacks/sec, callback_count={self._callback_count}")
                    self._callback_count = 0
                    self._callback_last_log = now

                # Create CaptureImage objects
                # Optimized: Increment frame_id_counter early to avoid race conditions
                frame_id = self.frame_id_counter
                self.frame_id_counter += 1

                if self.split_stream and self.src_coords and self.num_split > 0:
                    try:
                        capture_images = self._handle_split_stream(
                            src_image=frame_data,
                            frame_id=frame_id,
                            timestamp=now,
                            current_video_frame=current_video_frame,
                            current_video_position=current_video_position
                        )
                    except Exception as e:
                        self.logger.error(f"Error in _handle_split_stream for {self.source_names}: {e}", exc_info=True)
                        capture_images = []

                    # Mark as working when we receive first valid frame after init
                    # IMPORTANT: For split streams, we mark as working even if capture_images is empty initially
                    # This allows subsequent frames to be processed
                    if self._init_time and not self.is_working:
                        if (now - self._init_time) < CaptureConstants.INIT_GRACE_PERIOD_SECONDS:
                            if capture_images:
                                self.logger.info(
                                    f"First frame received {(now - self._init_time):.1f}s after init - marking as working")
                                self.is_working = True
                                # Frames are flowing again: clear noframes restart backoff.
                                try:
                                    self._noframes_restart_consecutive = 0
                                except Exception:
                                    pass
                            else:
                                # Even if split failed, we received a frame from GStreamer
                                # Mark as working to allow subsequent frames to be processed
                                self.logger.warning(
                                    f"First frame received but split returned empty for {self.source_names} - marking as working anyway")
                                self.is_working = True
                                try:
                                    self._noframes_restart_consecutive = 0
                                except Exception:
                                    pass

                    # If still not working after init grace period, skip frame
                    if not self.is_working:
                        process_time = time.perf_counter() - processing_start
                        self._record_perf_metrics(pull_duration, process_time, pts_value)
                        return Gst.FlowReturn.OK

                    # Store frames
                    if capture_images:
                        for img in capture_images:
                            self._store_frame(img, is_split=True)
                        # Store first frame as last_frame for compatibility
                        with self.frame_lock:
                            self.last_frame = capture_images[0]
                        # Notify subscribers asynchronously (only if there are subscribers)
                        if self.subscribers:
                            self._notify_subscribers_async(capture_images)

                        # Сбрасываем счетчик UDP ошибок при успешном получении кадра (поток восстановился)
                        if self._udp_error_count > 0:
                            self._udp_error_count = 0
                            self._last_udp_error_time = None
                    else:
                        # Log warning if split stream returns empty list (shouldn't happen normally)
                        if self.is_working:
                            self.logger.warning(
                                f"Split stream returned empty capture_images for {self.source_names} (frame_id={frame_id}, is_working={self.is_working}, frame_shape={frame_data.shape if frame_data is not None else None})")
                        # Even if capture_images is empty, we still received a frame from GStreamer
                        # Update last_frame with a dummy CaptureImage to track frame reception time
                        # This prevents false "no frames" warnings when frames are received but split fails
                        try:
                            # Create a minimal CaptureImage with current timestamp to track frame reception
                            dummy_image = self._create_capture_image(
                                image=None,  # No image data, just timestamp tracking
                                frame_id=frame_id,
                                timestamp=now,
                                source_id=self.source_ids[0] if self.source_ids else 0,
                                current_video_frame=current_video_frame,
                                current_video_position=current_video_position
                            )
                            with self.frame_lock:
                                # Always update to track latest frame reception time
                                self.last_frame = dummy_image
                        except Exception as e:
                            self.logger.debug(f"Failed to create dummy frame for timestamp tracking: {e}")
                else:
                    # Single stream
                    source_id = self.source_ids[0] if self.source_ids else 0
                    capture_image = self._create_capture_image(
                        image=frame_data,
                        frame_id=frame_id,
                        timestamp=now,
                        source_id=source_id,
                        current_video_frame=current_video_frame,
                        current_video_position=current_video_position
                    )

                    # Mark as working when we receive first frame after init
                    if self._init_time and not self.is_working:
                        if (now - self._init_time) < CaptureConstants.INIT_GRACE_PERIOD_SECONDS:
                            self.logger.info(
                                f"First frame received {(now - self._init_time):.1f}s after init - marking as working")
                            self.is_working = True
                            try:
                                self._noframes_restart_consecutive = 0
                            except Exception:
                                pass

                    # If still not working after init grace period, skip frame
                    if not self.is_working:
                        process_time = time.perf_counter() - processing_start
                        self._record_perf_metrics(pull_duration, process_time, pts_value)
                        return Gst.FlowReturn.OK

                    # Store frame
                    self._store_frame(capture_image, is_split=False)

                    # Сбрасываем счетчик UDP ошибок при успешном получении кадра (поток восстановился)
                    if self._udp_error_count > 0:
                        self._udp_error_count = 0
                        self._last_udp_error_time = None

                    # Notify subscribers asynchronously (only if there are subscribers)
                    # Check before calling to avoid unnecessary thread creation
                    if self.subscribers:
                        self._notify_subscribers_async([capture_image])

                process_time = time.perf_counter() - processing_start
                self._record_perf_metrics(pull_duration, process_time, pts_value)
                return Gst.FlowReturn.OK
        except Exception as e:
            self.logger.error(f"Error processing frame: {e}")
            return Gst.FlowReturn.ERROR

    def _process_gstreamer_frame_metadata(self, buffer, frame_data: np.ndarray) -> tuple[int | None, float | None]:
        """Process frame metadata for GStreamer (video position, frame number).
        
        Args:
            buffer: GStreamer buffer object
            frame_data: Extracted frame data
            
        Returns:
            Tuple of (current_video_frame, current_video_position)
        """
        current_video_frame = None
        current_video_position = None

        if self.source_type == CaptureDeviceType.VideoFile:
            try:
                # Prefer buffer PTS for accurate position
                pts_ns = buffer.pts
                if pts_ns is not None and pts_ns != Gst.CLOCK_TIME_NONE and pts_ns >= 0:
                    self.video_current_position = float(pts_ns) / 1e6  # ms
                else:
                    ok, pos_ns = self.pipeline.query_position(Gst.Format.TIME)
                    if ok and pos_ns is not None and pos_ns >= 0:
                        self.video_current_position = float(pos_ns) / 1e6  # milliseconds
                    else:
                        self.video_current_position = None
            except Exception:
                self.video_current_position = None

            # Approximate current frame if fps is known
            if self.source_fps and self.video_current_position is not None:
                self.video_current_frame = int((self.video_current_position / 1000.0) * self.source_fps)
            else:
                if self.video_current_frame is None:
                    self.video_current_frame = 0
                else:
                    self.video_current_frame += 1
            current_video_frame = self.video_current_frame
            current_video_position = self.video_current_position

        return current_video_frame, current_video_position

    def _reconnect_loop(self):
        """Reconnect loop for IP cameras (similar to OpenCV _grab_frames reconnect logic)"""
        if not self.run_flag:
            return
        # Prevent multiple simultaneous reconnect attempts
        if self._reconnecting:
            return
        self._reconnecting = True
        try:
            # Prevent races with monitor thread and force not working state
            self.is_inited = False
            self.is_working = False
            # Read reconnect settings from params if provided
            try:
                cfg = (self.params or {}).get('reconnect', {})
            except Exception:
                cfg = {}
            max_attempts = int(cfg.get('max_attempts', 0))  # 0 => infinite by default
            initial_delay_sec = float(cfg.get('initial_delay_sec', CaptureConstants.RECONNECT_INITIAL_DELAY_SEC))
            max_delay_sec = float(cfg.get('max_delay_sec', CaptureConstants.RECONNECT_MAX_DELAY_SEC))
            backoff_step_sec = float(cfg.get('backoff_step_sec', CaptureConstants.RECONNECT_BACKOFF_STEP_SEC))
            min_first_backoff_sec = float(
                cfg.get('min_first_backoff_sec', CaptureConstants.RECONNECT_MIN_FIRST_BACKOFF_SEC)
            )
            attempt = 0
            from .reconnect_policy import reconnect_wait_sec
            while self.run_flag and not self.stop_event.is_set() and (max_attempts == 0 or attempt < max_attempts):
                # First attempt immediate only for a fresh session; later attempts use backoff.
                # If we already had a successful reconnect recently, still apply min first backoff
                # when attempt>0 inside this loop.
                wait_time = reconnect_wait_sec(
                    attempt,
                    initial_delay_sec=initial_delay_sec,
                    backoff_step_sec=backoff_step_sec,
                    max_delay_sec=max_delay_sec,
                    min_first_backoff_sec=0.0 if attempt == 0 else min_first_backoff_sec,
                )
                if wait_time > 0:
                    self.logger.debug(
                        f"Waiting {wait_time:.1f}s before reconnect attempt {attempt + 1} for {self.source_names}")
                    if self.stop_event.wait(wait_time):
                        break
                attempt += 1
                if not self.is_working and self.run_flag:
                    try:
                        total_str = ("∞" if max_attempts == 0 else str(max_attempts))
                        self.logger.info(
                            f"Reconnecting to source {self.source_names} (attempt {attempt}/{total_str}), backoff={wait_time:.1f}s")
                        # Release old pipeline (with timeout to prevent blocking)
                        try:
                            import threading as _thr_rel
                            release_done = _thr_rel.Event()

                            def _release_worker():
                                try:
                                    self.release()
                                except Exception as e:
                                    self.logger.debug(f"Error in release during reconnect: {e}")
                                finally:
                                    release_done.set()

                            release_thread = _thr_rel.Thread(target=_release_worker, daemon=True)
                            release_thread.start()
                            # Wait up to 2 seconds for release
                            if not release_done.wait(2.0):
                                self.logger.warning(
                                    f"Release timeout after 2s for {self.source_names}; continuing anyway")
                        except Exception as e:
                            self.logger.debug(f"Error starting release thread: {e}")
                        # Wait a bit before retry
                        if self.stop_event.wait(2.0):
                            break
                        # Try to reinitialize with timeout and protocol fallback
                        init_ok = False
                        init_err = None
                        import threading as _thr
                        done_evt = _thr.Event()
                        init_thread = None

                        def _try_init():
                            nonlocal init_ok, init_err
                            try:
                                # Call init() which now has its own internal timeout
                                # init() returns False on failure, True on success
                                self.logger.debug(f"Calling init() for {self.source_names} (attempt {attempt})")
                                result = self.init()
                                init_ok = (result is True)
                                if not init_ok:
                                    init_err = RuntimeError("init() returned False")
                                    self.logger.debug(f"init() returned False for {self.source_names}")
                                else:
                                    self.logger.debug(f"init() returned True for {self.source_names}")
                            except Exception as e:
                                init_err = e
                                init_ok = False
                                self.logger.debug(f"init() raised exception for {self.source_names}: {e}")
                            finally:
                                done_evt.set()

                        init_thread = _thr.Thread(target=_try_init, daemon=True)
                        init_thread.start()
                        # Wait up to 8s for init (init() itself has 6s timeout, so total ~8s to allow for thread overhead)
                        if not done_evt.wait(8.0):
                            self.logger.warning(
                                f"Reconnect init timeout after 8s for {self.source_names}; forcing cleanup and retry")
                            # Force aggressive cleanup (don't call release() here - it's already called at the start of the attempt)
                            try:
                                with self.pipeline_lock:
                                    if self.pipeline is not None:
                                        try:
                                            self.logger.debug(f"Force setting pipeline to NULL for {self.source_names}")
                                            self.pipeline.set_state(Gst.State.NULL)
                                        except Exception as e:
                                            self.logger.debug(f"Error setting pipeline to NULL: {e}")
                                        self.pipeline = None
                                    self.bus = None
                                    self.appsink = None
                            except Exception as e:
                                self.logger.debug(f"Error in aggressive cleanup: {e}")
                            # Mark as not initialized
                            self.is_inited = False
                            self.is_working = False
                            init_ok = False
                            # Log current state for debugging
                            self.logger.debug(
                                f"After timeout cleanup: is_inited={self.is_inited}, is_working={self.is_working}, pipeline={self.pipeline is not None}")
                            # Continue to the retry logic below - don't call release() here as it may block
                        elif init_err is not None:
                            self.logger.error(f"Reconnect init error: {init_err}")
                            # Store error for protocol switching logic
                            self._last_init_error = init_err
                            init_ok = False
                        else:
                            # Check if init actually succeeded
                            init_ok = self.is_inited and self.is_working
                            if not init_ok:
                                self.logger.debug(
                                    f"init() completed but is_inited={self.is_inited}, is_working={self.is_working} for {self.source_names}")

                        # CRITICAL: Always check init_ok and log failure if needed, then continue loop
                        if init_ok:
                            timestamp = datetime.datetime.now()
                            self.logger.info(f"Reconnected to source: {self.source_names}")
                            self._record_reconnect(timestamp)
                            try:
                                self._noframes_restart_last_ts = time.time()
                            except Exception:
                                pass
                            for sub in self.subscribers:
                                sub.update()
                            break
                        else:
                            # Log failure and continue to next attempt - THIS MUST BE REACHED
                            self.logger.warning(
                                f"Reconnection attempt {attempt} failed for {self.source_names}; will retry (init_ok={init_ok}, is_inited={self.is_inited}, is_working={self.is_working})")
                            # Protocol switching logic removed - always use UDP, never switch to TCP automatically
                            # If UDP fails, it's likely a network/camera issue, not a protocol issue
                            # User can manually configure TCP if needed, but we never switch automatically
                            # Continue loop - this is critical to ensure retries happen
                            continue
                    except Exception as e:
                        self.logger.error(f"Reconnection error: {e}")
                        # Continue loop even on exception
                        continue
            if max_attempts and attempt >= max_attempts:
                self.logger.error(f"Failed to reconnect after {max_attempts} attempts")
        finally:
            self._reconnecting = False

    def _retrieve_frames(self) -> None:
        """
        Retrieve frames (not used in this implementation).
        
        GStreamer handles frame retrieval automatically via callbacks.
        """
        pass

    def _store_frame(self, capture_image: CaptureImage, is_split: bool = False) -> None:
        """Store frame in buffer and update counters.
        
        Args:
            capture_image: CaptureImage object to store
            is_split: Whether this is a split stream frame
        """
        with self.frame_lock:
            if is_split:
                # For split streams, store in frame_buffer
                # Optimized: Try to add frame, if full, remove multiple old frames to make room
                # This reduces buffer overflows by being more aggressive about clearing old frames
                try:
                    self.frame_buffer.put(capture_image, block=False)
                    # Track frame ID for diagnostics
                    self._frame_buffer_deque.append(capture_image.frame_id)
                except Full:
                    self._perf_frame_buffer_full += 1
                    # Remove multiple old frames to make room (more aggressive clearing)
                    # Remove up to 50% of buffer to make room for new frames
                    frames_removed = 0
                    buffer_size = self.frame_buffer.qsize()
                    max_removals = max(1, buffer_size // 2)  # Remove up to 50% of buffer
                    while frames_removed < max_removals:
                        try:
                            old_frame = self.frame_buffer.get_nowait()
                            # Explicitly free memory from old frame
                            if old_frame is not None:
                                old_frame.image = None
                            old_frame = None
                            frames_removed += 1
                        except Empty:
                            break
                    # Try to add new frame
                    try:
                        self.frame_buffer.put_nowait(capture_image)
                        self._frame_buffer_deque.append(capture_image.frame_id)
                    except Full:
                        # If still full after clearing, drop the new frame (shouldn't happen often)
                        self.logger.debug(
                            f"Frame buffer still full after clearing {frames_removed} frames, dropping frame for source {capture_image.source_id}")
            else:
                # For single stream, store as last_frame
                # Free memory from old last_frame AFTER storing new one
                # Since get_frames_impl now creates copies, it's safe to free old frame
                old_last_frame = self.last_frame
                self.last_frame = capture_image
                # Free old frame memory (safe now because get_frames_impl creates copies)
                if old_last_frame is not None:
                    old_last_frame.image = None
            self.frame_id_counter += 1

    def get_frames_impl(self) -> List[CaptureImage]:
        """
        Get latest captured frames.
        For split_stream, returns all split frames from frame_buffer.
        For single stream, returns a copy of last_frame (like OpenCV implementation).
        """
        frames = []
        if not self.is_working:
            return frames

        # Track get() calls for diagnostics
        self._get_call_count += 1
        now = time.time()
        if now - self._get_call_last_log >= 5.0:
            source_label = ",".join(str(name) for name in self.source_names) if self.source_names else str(
                self.source_address)
            get_fps = self._get_call_count / (now - self._get_call_last_log)
            self.logger.debug(
                f"Capture get() calls [{source_label}]: {get_fps:.2f} calls/sec, get_call_count={self._get_call_count}")
            self._get_call_count = 0
            self._get_call_last_log = now

        if self.split_stream:
            # For split streams, get all frames from frame_buffer
            with self.frame_lock:
                while not self.frame_buffer.empty():
                    try:
                        frame = self.frame_buffer.get_nowait()
                        frames.append(frame)
                    except Empty:
                        break
        else:
            # For single stream, create a copy of last_frame (like OpenCV does)
            # This prevents race condition when old frame memory is freed in _store_frame
            last_frame_ref = None
            frame_id = None
            timestamp = None
            source_id = None
            current_video_frame = None
            current_video_position = None
            image_copy = None

            try:
                # Get reference to last_frame with minimal lock time
                with self.frame_lock:
                    if self.last_frame:
                        # Track if we're returning the same frame multiple times (indicates pipeline is faster than GStreamer)
                        current_frame_id = self.last_frame.frame_id
                        if current_frame_id == self._last_returned_frame_id:
                            # Same frame returned again - pipeline is calling get() faster than GStreamer produces frames
                            self._same_frame_count += 1
                        else:
                            self._last_returned_frame_id = current_frame_id
                            if self._same_frame_count > 0:
                                # Log if we had repeated frames
                                source_label = ",".join(
                                    str(name) for name in self.source_names) if self.source_names else str(
                                    self.source_address)
                                self.logger.debug(
                                    f"Capture get() [{source_label}]: returned same frame {self._same_frame_count} times before new frame")
                                self._same_frame_count = 0
                        # Only copy reference and metadata while holding lock (very fast)
                        last_frame_ref = self.last_frame
                        frame_id = last_frame_ref.frame_id
                        timestamp = last_frame_ref.time_stamp
                        source_id = last_frame_ref.source_id
                        current_video_frame = last_frame_ref.current_video_frame
                        current_video_position = last_frame_ref.current_video_position
                        # Get reference to image (don't copy yet - do it outside lock)
                        image_ref = last_frame_ref.image
                    else:
                        last_frame_ref = None
                        image_ref = None

                # Copy image and create new CaptureImage outside of lock
                # This prevents blocking _store_frame() which also needs frame_lock
                if last_frame_ref is not None:
                    # Optimization: Only copy if there are subscribers or if frame might be accessed concurrently
                    # For single stream without subscribers, we can avoid the copy since get() is called from main thread
                    # and _store_frame() already completed. However, to be safe, we still copy if subscribers exist.
                    # If no subscribers, we can reuse the reference (but still need to copy metadata to avoid race conditions)
                    if self.subscribers:
                        # Copy image data outside lock (may take time for large images)
                        # Required when subscribers might access frame concurrently
                        image_copy = image_ref.copy() if image_ref is not None else None
                    else:
                        # No subscribers - can reuse reference, but need to be careful about thread safety
                        # Since get() is called from main thread and _store_frame() already completed,
                        # the reference should be safe. However, to avoid potential issues with frame updates,
                        # we still do a shallow copy of the array (view) which is much faster than deep copy.
                        # Actually, for safety, we still do a copy, but this is a known optimization point.
                        image_copy = image_ref.copy() if image_ref is not None else None

                    copied_frame = self._create_capture_image(
                        image=image_copy,
                        frame_id=frame_id,
                        timestamp=timestamp,
                        source_id=source_id,
                        current_video_frame=current_video_frame,
                        current_video_position=current_video_position
                    )
                    frames.append(copied_frame)
            except Exception as e:
                # Log error but don't break the flow - return empty list if copy fails
                self.logger.error(f"Error creating frame copy in get_frames_impl: {e}", exc_info=True)

        return frames
