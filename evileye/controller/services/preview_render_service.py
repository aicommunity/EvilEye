from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Optional

from evileye.core.logger import get_module_logger
from evileye.visualization_modules.preview_render import (
    PreviewRenderContext,
    render_preview_frame,
    serialize_preview_metadata,
)


@dataclass
class PreviewRenderJob:
    frame: object
    context: PreviewRenderContext
    source_id: int | None
    submitted_at: float = field(default_factory=time.time)


class PreviewRenderService:
    """Asynchronous preview renderer with latest-frame semantics."""

    def __init__(self):
        self.logger = get_module_logger("preview_render_service")
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)
        self._stop_event = threading.Event()
        self._workers: list[threading.Thread] = []
        self._pending_jobs: dict[str, PreviewRenderJob] = {}
        self._worker_count = 1
        self._streaming_service = None
        self._stats = {
            "submitted": 0,
            "replaced_latest": 0,
            "rendered": 0,
            "render_errors": 0,
            "last_render_ms": 0.0,
        }

    def configure(self, *, streaming_service=None, num_workers: int = 1) -> None:
        with self._condition:
            self._stop_event.clear()
            self._streaming_service = streaming_service
            self._worker_count = max(1, int(num_workers or 1))
            self._pending_jobs.clear()
            self._ensure_workers_locked()
            self._condition.notify_all()

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

    def wants_frame(self, source_id: int | None) -> bool:
        if self._streaming_service is None:
            return False
        try:
            return bool(self._streaming_service.has_consumers(source_id))
        except Exception:
            return True

    def submit_frame(self, frame, context: PreviewRenderContext) -> bool:
        if self._streaming_service is None:
            return False
        if getattr(frame, "image", None) is None:
            return False
        source_id = getattr(frame, "source_id", None)
        if not self.wants_frame(source_id):
            return False
        key = self._job_key(source_id)
        with self._condition:
            if key in self._pending_jobs:
                self._stats["replaced_latest"] += 1
            self._pending_jobs[key] = PreviewRenderJob(frame=frame, context=context, source_id=source_id)
            self._stats["submitted"] += 1
            self._condition.notify()
        return True

    def get_runtime_stats(self) -> dict:
        with self._condition:
            stats = dict(self._stats)
            stats["pending_jobs"] = len(self._pending_jobs)
            stats["worker_count"] = len(self._workers)
            return stats

    def _job_key(self, source_id: int | None) -> str:
        return f"src:{source_id}" if source_id is not None else "default"

    def _ensure_workers_locked(self) -> None:
        if self._workers:
            return
        for idx in range(self._worker_count):
            worker = threading.Thread(
                target=self._worker_loop,
                daemon=True,
                name=f"PreviewRenderer-{idx}",
            )
            worker.start()
            self._workers.append(worker)

    def _get_next_job(self) -> Optional[PreviewRenderJob]:
        with self._condition:
            while not self._stop_event.is_set() and not self._pending_jobs:
                self._condition.wait(timeout=0.5)
            if self._stop_event.is_set() or not self._pending_jobs:
                return None
            oldest_key = min(
                self._pending_jobs,
                key=lambda key: self._pending_jobs[key].submitted_at,
            )
            return self._pending_jobs.pop(oldest_key)

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            job = self._get_next_job()
            if job is None:
                continue
            try:
                import time
                started = time.perf_counter()
                rendered = render_preview_frame(job.frame, job.context)
                self._stats["rendered"] += 1
                self._stats["last_render_ms"] = (time.perf_counter() - started) * 1000.0
                if rendered is not None and self._streaming_service is not None:
                    image = getattr(rendered, "image", None)
                    shape = getattr(image, "shape", None)
                    meta = serialize_preview_metadata(
                        job.context,
                        shape,
                        frame_id=getattr(job.frame, "frame_id", None),
                        frame=job.frame,
                    )
                    self._streaming_service.submit_frame(
                        rendered,
                        metadata=meta,
                    )
            except Exception as exc:
                self._stats["render_errors"] += 1
                self.logger.warning("Async preview render failed: %s", exc, exc_info=True)
