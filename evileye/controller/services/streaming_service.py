from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path
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
        self._last_publish_ts = 0.0
        self._frame_dir: Optional[Path] = None
        self._server_process_manager = None
        self._encoder: JpegEncoderBackend = create_jpeg_encoder()
        self._worker_count = 1

    def configure(
        self,
        *,
        pipeline_id: str,
        publish_fps: float,
        frame_dir: Optional[Path],
        server_process_manager=None,
        encoder_backend: str = "auto",
        jpeg_quality: int = 85,
        num_workers: int = 1,
    ) -> None:
        with self._condition:
            self._stop_event.clear()
            self._pipeline_id = pipeline_id or "default"
            self._publish_fps = max(0.0, float(publish_fps or 0.0))
            self._last_publish_ts = 0.0
            self._frame_dir = Path(frame_dir) if frame_dir else None
            if self._frame_dir:
                self._frame_dir.mkdir(parents=True, exist_ok=True)
            self._server_process_manager = server_process_manager
            self._encoder = create_jpeg_encoder(encoder_backend, jpeg_quality)
            self._worker_count = max(1, int(num_workers or 1))
            self._pending_jobs.clear()
            self._ensure_workers_locked()
            self._condition.notify_all()

    def set_server_process_manager(self, manager) -> None:
        with self._condition:
            self._server_process_manager = manager
            self._condition.notify_all()

    def submit_frame(self, frame) -> bool:
        image = getattr(frame, "image", None)
        if image is None:
            return False

        if not self._should_publish():
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
            self._pending_jobs[job.pipeline_id] = job
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

    def _should_publish(self) -> bool:
        if self._frame_dir:
            return self._throttle_ok()

        has_local_stream = False
        try:
            from evileye.api.core.broker_access import get_broker

            has_local_stream = get_broker().is_stream_active(self._pipeline_id)
        except Exception:
            has_local_stream = False

        has_server_process = False
        try:
            has_server_process = (
                self._server_process_manager is not None
                and self._server_process_manager.is_alive()
            )
        except Exception:
            has_server_process = False

        if not has_local_stream and not has_server_process:
            return False
        return self._throttle_ok()

    def _throttle_ok(self) -> bool:
        if self._publish_fps <= 0.0:
            return True
        now = time.time()
        min_interval = 1.0 / self._publish_fps
        if (now - self._last_publish_ts) < min_interval:
            return False
        self._last_publish_ts = now
        return True

    def _publish_jpeg(self, pipeline_id: str, jpeg_bytes: bytes, job: StreamFrameJob) -> None:
        metadata = {
            "timestamp": job.created_at,
            "source_id": job.source_id,
            "frame_id": job.frame_id,
            "content_type": "image/jpeg",
        }
        if self._frame_dir:
            try:
                tmp = self._frame_dir / ".latest.tmp"
                final = self._frame_dir / "latest.jpg"
                tmp.write_bytes(jpeg_bytes)
                tmp.replace(final)
            except Exception as e:
                self.logger.warning("Frame file write failed: %s", e)
            return

        from evileye.api.core.broker_access import get_broker

        get_broker().publish_jpeg(pipeline_id, jpeg_bytes, metadata=metadata)
        if self._server_process_manager is not None:
            try:
                self._server_process_manager.publish_frame(pipeline_id, jpeg_bytes, metadata=metadata)
            except Exception:
                pass
