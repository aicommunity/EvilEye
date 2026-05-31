import threading
import multiprocessing as mp
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple
import time
from evileye.core.logger import get_module_logger


@dataclass
class FramePayload:
    data: bytes
    timestamp: float
    metadata: dict[str, Any] = field(default_factory=dict)


class FrameBroker:
    """Thread-safe storage of JPEG frames for multiple pipelines

    When the web server runs in a separate process, frames arrive
    via an ``mp.Queue`` that is polled by a background thread.  In
    single-process mode the controller publishes frames directly
    through ``publish_jpeg()``
    """

    def __init__(self):
        self.logger = get_module_logger("api.frame_broker")
        self._lock = threading.Lock()
        self._frames: Dict[str, FramePayload] = {}
        self._active_streams: Dict[str, threading.Event] = {}
        self._max_frame_age_seconds = 30.0
        self._max_frames_per_pipeline = 10

        # IPC support: when set, a background thread reads from this queue
        self._ipc_queue: Optional[mp.Queue] = None
        self._ipc_thread: Optional[threading.Thread] = None
        self._ipc_stop = threading.Event()
        self._stats = {
            "published_payloads": 0,
            "ipc_received": 0,
            "last_payload_bytes": 0,
        }

    # -- IPC bridge ------------------------------------------------------

    def set_ipc_queue(self, queue: mp.Queue) -> None:
        """Attach an mp.Queue and start a listener thread

        The controller (in the main process) puts (pipeline_id, jpeg_bytes)
        tuples into this queue.  The broker reads them and stores locally
        """
        self._ipc_queue = queue
        self._ipc_stop.clear()
        self._ipc_thread = threading.Thread(
            target=self._ipc_listener_loop, daemon=True,
        )
        self._ipc_thread.start()
        self.logger.info("IPC frame listener started")

    def _ipc_listener_loop(self):
        while not self._ipc_stop.is_set():
            try:
                item = self._ipc_queue.get(timeout=0.5)
                if item is None:
                    break
                if isinstance(item, tuple) and len(item) == 3:
                    pipeline_id, jpeg_bytes, metadata = item
                else:
                    pipeline_id, jpeg_bytes = item
                    metadata = None
                self._stats["ipc_received"] += 1
                self.publish_jpeg(pipeline_id, jpeg_bytes, metadata=metadata)
                source_id = (metadata or {}).get("source_id") if isinstance(metadata, dict) else None
                if source_id is not None:
                    self.publish_jpeg(f"{pipeline_id}:{source_id}", jpeg_bytes, metadata=metadata)
            except Exception:
                continue

    def stop_ipc(self):
        self._ipc_stop.set()
        if self._ipc_queue is not None:
            try:
                self._ipc_queue.put_nowait(None)
            except Exception:
                pass
        if self._ipc_thread and self._ipc_thread.is_alive():
            self._ipc_thread.join(timeout=2.0)

    # -- Frame storage ---------------------------------------------------

    def _cleanup_old_frames(self, max_age_seconds: Optional[float] = None) -> None:
        if max_age_seconds is None:
            max_age_seconds = self._max_frame_age_seconds

        current_time = time.time()
        cutoff_time = current_time - max_age_seconds

        pipelines_to_remove = []
        for pipeline_id, payload in list(self._frames.items()):
            if payload.timestamp < cutoff_time:
                pipelines_to_remove.append((pipeline_id, payload.timestamp))

        for pipeline_id, timestamp in pipelines_to_remove:
            del self._frames[pipeline_id]

        if len(self._frames) > self._max_frames_per_pipeline * max(1, len(self._active_streams)):
            sorted_frames = sorted(self._frames.items(), key=lambda x: x[1].timestamp)
            frames_to_remove = len(self._frames) - (self._max_frames_per_pipeline * max(1, len(self._active_streams)))
            removed_count = 0
            for pipeline_id, _ in sorted_frames:
                if pipeline_id not in self._active_streams and removed_count < frames_to_remove:
                    del self._frames[pipeline_id]
                    removed_count += 1

    def publish_payload(
            self,
            pipeline_id: str,
            payload: bytes,
            *,
            metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        with self._lock:
            self._frames[pipeline_id] = FramePayload(
                data=payload,
                timestamp=time.time(),
                metadata=dict(metadata or {}),
            )
            self._stats["published_payloads"] += 1
            self._stats["last_payload_bytes"] = len(payload) if payload is not None else 0
            self._cleanup_old_frames()
        self.logger.debug(f"Published frame for pipeline '{pipeline_id}'")

    def get_runtime_stats(self) -> dict:
        with self._lock:
            stats = dict(self._stats)
            stats["frames_keys"] = len(self._frames)
            stats["active_streams"] = len(self._active_streams)
            stats["estimated_bytes"] = sum(len(payload.data) for payload in self._frames.values())
            return stats

    def publish_jpeg(
            self,
            pipeline_id: str,
            jpeg_bytes: bytes,
            metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        meta = dict(metadata or {})
        meta.setdefault("content_type", "image/jpeg")
        self.publish_payload(pipeline_id, jpeg_bytes, metadata=meta)

    def latest_jpeg(self, pipeline_id: str) -> Optional[bytes]:
        payload = self.latest_payload(pipeline_id)
        return payload.data if payload else None

    def latest_payload(self, pipeline_id: str) -> Optional[FramePayload]:
        with self._lock:
            payload = self._frames.get(pipeline_id)
            if not payload:
                return None
            return payload

    def start_stream(self, pipeline_id: str) -> threading.Event:
        with self._lock:
            if pipeline_id not in self._active_streams:
                self._active_streams[pipeline_id] = threading.Event()
                self.logger.info(f"Started stream for pipeline '{pipeline_id}'")
            return self._active_streams[pipeline_id]

    def stop_stream(self, pipeline_id: str) -> bool:
        with self._lock:
            if pipeline_id in self._active_streams:
                self._active_streams[pipeline_id].set()
                del self._active_streams[pipeline_id]
                self.logger.info(f"Stopped stream for pipeline '{pipeline_id}'")
                return True
            self.logger.warning(f"No active stream found for pipeline '{pipeline_id}'")
            return False

    def is_stream_active(self, pipeline_id: str) -> bool:
        with self._lock:
            return pipeline_id in self._active_streams

    def get_stream_event(self, pipeline_id: str) -> Optional[threading.Event]:
        with self._lock:
            return self._active_streams.get(pipeline_id)

    def clear_pipeline(self, pipeline_id: str) -> None:
        with self._lock:
            if pipeline_id in self._frames:
                del self._frames[pipeline_id]
                self.logger.info(f"Cleared frames for pipeline '{pipeline_id}'")

    def clear_all(self) -> None:
        with self._lock:
            self._frames.clear()
            self.logger.info("Cleared all frames")
