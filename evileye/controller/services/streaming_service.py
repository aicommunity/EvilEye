from __future__ import annotations

import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional

from evileye.core.logger import get_module_logger

from .jpeg_encoder import JpegEncoderBackend, create_jpeg_encoder


@dataclass
class StreamFrameJob:
    pipeline_id: str
    image: Any
    source_id: Optional[int]
    frame_id: Optional[int]
    created_at: float


class FrameRelayClient:
    def __init__(self, base_url: str, *, token: str | None = None, timeout_sec: float = 0.5):
        self.base_url = base_url.rstrip("/")
        self.token = token or ""
        self.timeout_sec = max(0.1, float(timeout_sec))
        self.logger = get_module_logger("frame_relay")

    def publish_jpeg(self, pipeline_id: str, jpeg_bytes: bytes, *, source_id: int | None = None) -> bool:
        query = f"?source_id={source_id}" if source_id is not None else ""
        url = f"{self.base_url}/internal/frames/{pipeline_id}{query}"
        headers = {"Content-Type": "image/jpeg"}
        if self.token:
            headers["X-EvilEye-Internal-Token"] = self.token
        request = urllib.request.Request(url, data=jpeg_bytes, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_sec) as response:
                return 200 <= getattr(response, "status", 200) < 300
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            self.logger.debug("Frame relay publish failed: %s", exc)
            return False


class StreamingService:
    """Asynchronous preview publisher with latest-frame semantics."""

    def __init__(self):
        self.logger = get_module_logger("streaming_service")
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)
        self._stop_event = threading.Event()
        self._workers: list[threading.Thread] = []
        self._pending_jobs: dict[str, StreamFrameJob] = {}

        self._pipeline_id = "default"
        self._publish_fps = 5.0
        self._last_publish_ts_by_key: dict[str, float] = {}
        self._server_process_manager = None
        self._frame_relay: FrameRelayClient | None = None
        self._encoder: JpegEncoderBackend = create_jpeg_encoder()
        self._worker_count = 1

    @staticmethod
    def _job_key(job: StreamFrameJob) -> str:
        if job.source_id is None:
            return job.pipeline_id
        return f"{job.pipeline_id}:{job.source_id}"

    def configure(
        self,
        *,
        pipeline_id: str,
        publish_fps: float,
        server_process_manager=None,
        relay_base_url: str | None = None,
        relay_token: str | None = None,
        encoder_backend: str = "auto",
        jpeg_quality: int = 85,
        num_workers: int = 1,
    ) -> None:
        with self._condition:
            self._stop_event.clear()
            self._pipeline_id = pipeline_id or "default"
            self._publish_fps = max(0.0, float(publish_fps or 0.0))
            self._last_publish_ts_by_key.clear()
            self._server_process_manager = server_process_manager
            self._frame_relay = FrameRelayClient(relay_base_url, token=relay_token) if relay_base_url else None
            self._encoder = create_jpeg_encoder(encoder_backend, jpeg_quality)
            self._worker_count = max(1, int(num_workers or 1))
            self._pending_jobs.clear()
            self._ensure_workers_locked()
            self._condition.notify_all()

    def set_server_process_manager(self, manager) -> None:
        with self._condition:
            self._server_process_manager = manager
            self._condition.notify_all()

    def set_frame_relay(self, relay_base_url: str | None, relay_token: str | None = None) -> None:
        with self._condition:
            self._frame_relay = FrameRelayClient(relay_base_url, token=relay_token) if relay_base_url else None
            self._condition.notify_all()

    def submit_frame(self, frame) -> bool:
        image = getattr(frame, "image", None)
        if image is None:
            return False

        source_id = getattr(frame, "source_id", None)
        throttle_key = f"{self._pipeline_id}:{source_id}" if source_id is not None else self._pipeline_id
        if not self._should_publish(throttle_key):
            return False

        try:
            image_for_encode = image.copy()
        except Exception:
            image_for_encode = image

        job = StreamFrameJob(
            pipeline_id=self._pipeline_id,
            image=image_for_encode,
            source_id=getattr(frame, "source_id", None),
            frame_id=getattr(frame, "frame_id", None),
            created_at=time.time(),
        )
        with self._condition:
            self._pending_jobs[self._job_key(job)] = job
            self._condition.notify()
        return True

    def stop(self) -> None:
        self._stop_event.set()
        with self._condition:
            self._condition.notify_all()
        for worker in self._workers:
            if worker.is_alive():
                worker.join(timeout=2.0)
        self._workers.clear()
        with self._condition:
            self._pending_jobs.clear()

    def _ensure_workers_locked(self) -> None:
        if self._workers:
            return
        for idx in range(self._worker_count):
            worker = threading.Thread(
                target=self._worker_loop,
                daemon=True,
                name=f"StreamPublisher-{idx}",
            )
            worker.start()
            self._workers.append(worker)

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            job = self._get_next_job()
            if job is None:
                continue
            try:
                payload = self._encoder.encode(job.image)
                if not payload:
                    continue
                self._publish_jpeg(job.pipeline_id, payload, job)
            except Exception as e:
                self.logger.debug("Async preview publish failed: %s", e, exc_info=True)

    def _get_next_job(self) -> Optional[StreamFrameJob]:
        with self._condition:
            while not self._stop_event.is_set() and not self._pending_jobs:
                self._condition.wait(timeout=0.5)
            if self._stop_event.is_set():
                return None
            _, job = self._pending_jobs.popitem()
            return job

    def _should_publish(self, throttle_key: str) -> bool:
        has_local_stream = False
        try:
            from evileye.api.core.broker_access import get_broker

            has_local_stream = get_broker().is_stream_active(throttle_key) or get_broker().is_stream_active(self._pipeline_id)
        except Exception:
            has_local_stream = False

        has_server_preview_demand = False
        try:
            has_server_preview_demand = (
                self._server_process_manager is not None
                and self._server_process_manager.is_alive()
                and self._server_process_manager.has_preview_demand(throttle_key)
            )
        except Exception:
            has_server_preview_demand = False

        has_server_process = False
        try:
            has_server_process = (
                self._server_process_manager is not None
                and self._server_process_manager.is_alive()
            )
        except Exception:
            has_server_process = False

        has_relay = self._frame_relay is not None

        if has_local_stream or has_server_preview_demand or has_relay:
            return self._throttle_ok(throttle_key)

        # Fallback for embedded server + web-ui bootstrap: keep a very low-rate
        # preview heartbeat so snapshots do not stay permanently "not ready" if
        # explicit demand propagation is delayed or lost.
        if has_server_process:
            return self._throttle_ok(throttle_key, fps_override=min(self._publish_fps, 1.0))

        if not has_local_stream and not has_server_preview_demand and not has_relay:
            return False
        return self._throttle_ok(throttle_key)

    def _throttle_ok(self, throttle_key: str, *, fps_override: float | None = None) -> bool:
        effective_fps = self._publish_fps if fps_override is None else max(0.0, float(fps_override))
        if effective_fps <= 0.0:
            return True
        now = time.time()
        min_interval = 1.0 / effective_fps
        last_publish_ts = self._last_publish_ts_by_key.get(throttle_key, 0.0)
        if (now - last_publish_ts) < min_interval:
            return False
        self._last_publish_ts_by_key[throttle_key] = now
        return True

    def _publish_jpeg(self, pipeline_id: str, jpeg_bytes: bytes, job: StreamFrameJob) -> None:
        metadata = {
            "timestamp": job.created_at,
            "source_id": job.source_id,
            "frame_id": job.frame_id,
            "content_type": "image/jpeg",
        }
        from evileye.api.core.broker_access import get_broker

        get_broker().publish_jpeg(pipeline_id, jpeg_bytes, metadata=metadata)
        if job.source_id is not None:
            get_broker().publish_jpeg(f"{pipeline_id}:{job.source_id}", jpeg_bytes, metadata=metadata)
        if self._server_process_manager is not None:
            try:
                self._server_process_manager.publish_frame(pipeline_id, jpeg_bytes, metadata=metadata)
            except Exception:
                pass
        if self._frame_relay is not None:
            self._frame_relay.publish_jpeg(pipeline_id, jpeg_bytes, source_id=job.source_id)
