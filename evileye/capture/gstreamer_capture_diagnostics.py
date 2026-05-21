"""GStreamer capture mixin — see video_capture_gstreamer.py."""

from __future__ import annotations

from .gstreamer_capture_common import (
    CaptureConstants,
    Empty,
    Gst,
    Queue,
    threading,
    time,
)


class GStreamerCaptureDiagnosticsMixin:
    def _log_perf_stats(self, now: float) -> None:
        interval = now - self._perf_last_log
        if interval <= 0:
            interval = 1e-6

        frames = self._perf_frame_count
        fps = frames / interval if frames else 0.0
        avg_pull_ms = (self._perf_pull_total / frames) * 1000.0 if frames else 0.0
        avg_proc_ms = (self._perf_process_total / frames) * 1000.0 if frames else 0.0
        pts_fps = (self._perf_pts_count / self._perf_pts_accum) if self._perf_pts_accum > 0 else 0.0

        frame_buffer_size = 0
        if self.split_stream:
            try:
                frame_buffer_size = self.frame_buffer.qsize()
            except Exception:
                frame_buffer_size = -1

        recording_queue_buffers = None
        if self._recording_queue_elem is not None:
            try:
                recording_queue_buffers = self._recording_queue_elem.get_property("current-level-buffers")
            except Exception:
                recording_queue_buffers = None

        source_label = ",".join(str(name) for name in self.source_names) if self.source_names else str(
            self.source_address)
        msg_parts = [
            f"FPS={fps:.2f}",
            f"pull_wait={avg_pull_ms:.2f}ms",
            f"process={avg_proc_ms:.2f}ms"
        ]
        if pts_fps > 0:
            msg_parts.append(f"pts_fps={pts_fps:.2f}")
        if self.split_stream:
            msg_parts.append(f"frame_buffer={frame_buffer_size}")
        if self._perf_frame_buffer_full:
            msg_parts.append(f"buffer_overflows={self._perf_frame_buffer_full}")
        if recording_queue_buffers is not None:
            msg_parts.append(f"record_queue_buf={recording_queue_buffers}")

        # Логируем в DEBUG, чтобы не создавать флуд в логах
        self.logger.debug(f"Capture perf [{source_label}]: " + ", ".join(msg_parts))

        # Reset counters for next interval
        self._perf_last_log = now
        self._perf_frame_count = 0
        self._perf_pull_total = 0.0
        self._perf_process_total = 0.0
        self._perf_pts_accum = 0.0
        self._perf_pts_count = 0
        self._perf_frame_buffer_full = 0

    def _log_resource_stats(self, context: str) -> None:
        """Log lightweight RSS/threads/FD metrics to correlate with restarts."""
        from evileye.utils.resource_stats import collect_process_resource_stats, format_resource_stats_line

        stats = collect_process_resource_stats()
        if stats is None:
            return
        try:
            extra = f" restart_counter={self._restart_counter}"
            self.logger.info(format_resource_stats_line(context, stats, extra_suffix=extra))
        except Exception:
            pass

        # Recording queue backpressure visibility (continuous branch)
        try:
            if self._recording_queue_elem is not None:
                lvl = None
                try:
                    lvl = self._recording_queue_elem.get_property("current-level-buffers")
                except Exception:
                    lvl = None
                if lvl is not None:
                    self.logger.info(f"ResourceStats[{context}] record_queue_buf={lvl}")
        except Exception:
            pass

    def _maybe_schedule_malloc_trim(self, reason: str) -> None:
        """
        Best-effort memory trimming to return freed arenas to OS.

        Enabled via EVILEYE_MALLOC_TRIM=1/true/yes/on.
        By default runs asynchronously to avoid restart stalls.
        """
        try:
            import os as _os
            enabled = _os.environ.get("EVILEYE_MALLOC_TRIM", "").strip().lower() in {"1", "true", "yes", "on"}
            if not enabled:
                return
            async_mode = _os.environ.get("EVILEYE_MALLOC_TRIM_ASYNC", "1").strip().lower() in {"1", "true", "yes", "on"}
            min_interval_sec = float(_os.environ.get("EVILEYE_MALLOC_TRIM_MIN_INTERVAL_SEC", "60") or 60.0)
        except Exception:
            return

        now = time.time()
        try:
            with self._malloc_trim_lock:
                if self._malloc_trim_last_ts and (now - self._malloc_trim_last_ts) < min_interval_sec:
                    return
                self._malloc_trim_last_ts = now
        except Exception:
            return

        def _do_trim():
            start = time.perf_counter()
            try:
                try:
                    import gc as _gc
                    _gc.collect()
                except Exception:
                    pass
                try:
                    import ctypes as _ctypes
                    _libc = _ctypes.CDLL("libc.so.6")
                    try:
                        _libc.malloc_trim(0)
                    except Exception:
                        pass
                except Exception:
                    pass
            finally:
                dur_ms = (time.perf_counter() - start) * 1000.0
                try:
                    # Info-level so stalls are visible in user logs.
                    self.logger.info(
                        "MallocTrim: source=%s reason=%s async=%s duration_ms=%.1f",
                        self.source_names,
                        reason,
                        async_mode,
                        dur_ms,
                    )
                except Exception:
                    pass

        if async_mode:
            try:
                t = threading.Thread(target=_do_trim, name=f"evileye-malloc-trim-{getattr(self, 'source_id', 'n/a')}",
                                     daemon=True)
                t.start()
                return
            except Exception:
                # fall back to sync if thread creation fails
                pass

        _do_trim()

    def _record_perf_metrics(self, pull_time: float, process_time: float, buffer_pts: Optional[int]) -> None:
        try:
            self._perf_frame_count += 1
            self._perf_pull_total += pull_time
            self._perf_process_total += process_time

            clock_time_none = getattr(Gst, "CLOCK_TIME_NONE", None)
            if buffer_pts is not None and (
                    clock_time_none is None or buffer_pts != clock_time_none) and buffer_pts >= 0:
                if self._perf_last_pts is not None and buffer_pts >= self._perf_last_pts:
                    delta = (buffer_pts - self._perf_last_pts) / 1_000_000_000.0
                    if delta > 0:
                        self._perf_pts_accum += delta
                        self._perf_pts_count += 1
                self._perf_last_pts = buffer_pts

            now = time.time()
            # Периодически логируем perf-метрики, включая фактический FPS
            if now - self._perf_last_log >= self._perf_stats_interval:
                self._log_perf_stats(now)
        except Exception as e:
            self.logger.debug(f"Failed to record perf metrics: {e}")

    def _start_notify_worker(self) -> None:
        if self._notify_thread and self._notify_thread.is_alive():
            return
        if self._notify_queue is None:
            self._notify_queue = Queue(maxsize=3)
        self._notify_stop.clear()

        def _worker():
            while not self._notify_stop.is_set():
                try:
                    item = self._notify_queue.get(timeout=0.5)
                except Empty:
                    continue
                try:
                    if not item:
                        continue
                    # Snapshot subscribers list to avoid races if changed
                    subs = list(self.subscribers) if self.subscribers else []
                    if not subs:
                        continue
                    for capture_image in item:
                        for sub in subs:
                            try:
                                if callable(sub):
                                    sub(capture_image)
                                else:
                                    if hasattr(sub, 'process_frame'):
                                        sub.process_frame(capture_image)
                                    elif hasattr(sub, 'update'):
                                        sub.update()
                            except Exception as ex:
                                try:
                                    self.logger.error(f"Error notifying subscriber {type(sub)}: {ex}")
                                except Exception:
                                    pass
                finally:
                    try:
                        self._notify_queue.task_done()
                    except Exception:
                        pass

        self._notify_thread = threading.Thread(target=_worker, daemon=True, name="GstNotifyWorker")
        self._notify_thread.start()

    def _stop_notify_worker(self) -> None:
        try:
            self._notify_stop.set()
        except Exception:
            pass
        t = self._notify_thread
        if t and t.is_alive():
            try:
                if threading.current_thread() is t:
                    return
            except Exception:
                pass
            try:
                t.join(timeout=1.5)
            except Exception:
                pass
        self._notify_thread = None
        # Drain queue to release queued frames promptly
        q = self._notify_queue
        if q is not None:
            try:
                while True:
                    q.get_nowait()
                    q.task_done()
            except Exception:
                pass
