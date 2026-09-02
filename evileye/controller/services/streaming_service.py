from __future__ import annotations

import http.client
import json
import os
import socket
import threading
import time
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import urlparse

from evileye.core.logger import get_module_logger
from evileye.core.runtime_services import get_frame_broker

from .jpeg_encoder import JpegEncoderBackend, create_jpeg_encoder


def _unix_relay_url(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme == "unix" and (parsed.path or url.startswith("unix://")):
        return url
    return None


@dataclass
class StreamFrameJob:
    pipeline_id: str
    image: Any
    source_id: Optional[int]
    frame_id: Optional[int]
    created_at: float
    objects: list[dict[str, Any]] | None = None
    zones: list[dict[str, Any]] | None = None
    signalization: bool = False
    metadata: dict[str, Any] | None = None
    full_frame: bool = False
    alias_source_ids: list[int] | None = None


class FrameRelayClient:
    """Latest-frame relay. Unix socket is fire-and-forget (never HTTPS)."""

    def __init__(self, base_url: str, *, token: str | None = None, timeout_sec: float = 0.2):
        self.base_url = base_url.rstrip("/")
        self.token = token or ""
        self.timeout_sec = max(0.05, float(timeout_sec))
        self.logger = get_module_logger("frame_relay")
        self._last_warn_ts = 0.0
        self._lock = threading.Lock()
        self._pending: dict[str, tuple[str, bytes, int | None, dict[str, Any] | None]] = {}
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._conn: http.client.HTTPConnection | None = None
        self._unix_sock: socket.socket | None = None
        self._thread = threading.Thread(target=self._loop, daemon=True, name="FrameRelay")
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._close_conn()

    def _close_conn(self) -> None:
        conn = self._conn
        self._conn = None
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
        us = self._unix_sock
        self._unix_sock = None
        if us is not None:
            try:
                us.close()
            except OSError:
                pass

    def publish_jpeg(
        self,
        pipeline_id: str,
        jpeg_bytes: bytes,
        *,
        source_id: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        key = f"{pipeline_id}:{source_id}" if source_id is not None else pipeline_id
        with self._lock:
            self._pending[key] = (pipeline_id, jpeg_bytes, source_id, metadata)
        self._wake.set()
        return True

    def _log_publish_failure(self, exc: Exception) -> None:
        # EAGAIN / timeout = drop-old under load; do not alarm every 30s.
        if isinstance(exc, (TimeoutError, socket.timeout, BlockingIOError)):
            self.logger.debug("Frame relay dropped (busy): %s", exc)
            return
        err = getattr(exc, "errno", None)
        if err in {11, 32, 104}:  # EAGAIN, EPIPE, ECONNRESET
            self.logger.debug("Frame relay dropped: %s", exc)
            return
        now = time.time()
        if now - self._last_warn_ts >= 30.0:
            self.logger.warning("Frame relay publish failed: %s", exc)
            self._last_warn_ts = now
        else:
            self.logger.debug("Frame relay publish failed: %s", exc)

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._wake.wait(timeout=0.5)
            self._wake.clear()
            while not self._stop.is_set():
                with self._lock:
                    if not self._pending:
                        break
                    _key, item = self._pending.popitem()
                pipeline_id, jpeg_bytes, source_id, metadata = item
                try:
                    self._post(pipeline_id, jpeg_bytes, source_id=source_id, metadata=metadata)
                except Exception as exc:
                    self._log_publish_failure(exc)

    def _unix_path(self) -> str | None:
        parsed = urlparse(self.base_url)
        if parsed.scheme != "unix":
            return None
        return parsed.path or None

    def _request_path(self, pipeline_id: str, source_id: int | None) -> str:
        query = f"?source_id={source_id}" if source_id is not None else ""
        parsed = urlparse(self.base_url)
        prefix = (parsed.path or "").rstrip("/") or "/api/v1"
        return f"{prefix}/internal/frames/{pipeline_id}{query}"

    def _get_unix_sock(self) -> socket.socket:
        if self._unix_sock is not None:
            return self._unix_sock
        path = self._unix_path()
        if not path:
            raise RuntimeError("not a unix relay url")
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout_sec)
        sock.connect(path)
        self._unix_sock = sock
        return sock

    def _get_conn(self) -> http.client.HTTPConnection:
        if self._conn is not None:
            return self._conn
        parsed = urlparse(self.base_url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        if parsed.scheme == "https":
            from evileye.api.core.ssl_files import ssl_context_for_relay

            self._conn = http.client.HTTPSConnection(
                host,
                port,
                timeout=self.timeout_sec,
                context=ssl_context_for_relay(self.base_url),
            )
        else:
            self._conn = http.client.HTTPConnection(host, port, timeout=self.timeout_sec)
        return self._conn

    def _post_unix(
        self,
        pipeline_id: str,
        jpeg_bytes: bytes,
        *,
        source_id: int | None,
        metadata: dict[str, Any] | None,
    ) -> bool:
        from evileye.api.core.internal_unix import encode_frame_packet

        packet = encode_frame_packet(
            token=self.token,
            rid=pipeline_id,
            source_id=source_id,
            jpeg_bytes=jpeg_bytes,
            metadata=metadata,
        )
        try:
            sock = self._get_unix_sock()
            sock.sendall(packet)
            return True
        except Exception as exc:
            self._close_conn()
            self._log_publish_failure(exc)
            # One immediate reconnect + resend so API sock recreate recovers fast.
            try:
                sock = self._get_unix_sock()
                sock.sendall(packet)
                return True
            except Exception as retry_exc:
                self._close_conn()
                self._log_publish_failure(retry_exc)
                return False

    def _post(
        self,
        pipeline_id: str,
        jpeg_bytes: bytes,
        *,
        source_id: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        if self._unix_path():
            return self._post_unix(
                pipeline_id, jpeg_bytes, source_id=source_id, metadata=metadata
            )
        # Never POST frames to HTTPS/HTTP :8181 — that stalls the public TLS port.
        return False


def _downscale_image(image: Any, max_edge: int) -> Any:
    if image is None or max_edge <= 0:
        return image
    try:
        import cv2  # type: ignore
        import numpy as np  # type: ignore

        if not isinstance(image, np.ndarray):
            return image
        h, w = image.shape[:2]
        edge = max(h, w)
        if edge <= max_edge:
            return image
        scale = max_edge / float(edge)
        new_w = max(1, int(w * scale))
        new_h = max(1, int(h * scale))
        return cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)
    except Exception:
        return image


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
        self._relay_token: str | None = None
        self._encoder: JpegEncoderBackend = create_jpeg_encoder()
        self._worker_count = 1
        self._preview_max_edge = 960
        self._stats = {
            "submitted": 0,
            "copied_images": 0,
            "used_owned_images": 0,
            "encoded": 0,
            "publish_errors": 0,
            "last_encode_ms": 0.0,
        }

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
            preview_max_edge: int = 960,
    ) -> None:
        with self._condition:
            self._stop_event.clear()
            self._pipeline_id = pipeline_id or "default"
            self._publish_fps = max(0.0, float(publish_fps or 0.0))
            self._last_publish_ts_by_key.clear()
            self._server_process_manager = server_process_manager
            self._relay_token = relay_token
            if self._frame_relay is not None:
                try:
                    self._frame_relay.close()
                except Exception:
                    pass
            self._frame_relay = (
                FrameRelayClient(_unix_relay_url(relay_base_url), token=relay_token)
                if _unix_relay_url(relay_base_url)
                else None
            )
            self._encoder = create_jpeg_encoder(encoder_backend, jpeg_quality)
            self._worker_count = max(1, int(num_workers or 1))
            self._preview_max_edge = max(0, int(preview_max_edge or 0))
            self._pending_jobs.clear()
            self._ensure_workers_locked()
            self._condition.notify_all()

    def set_server_process_manager(self, manager) -> None:
        with self._condition:
            self._server_process_manager = manager
            self._condition.notify_all()

    def set_frame_relay(self, relay_base_url: str | None, relay_token: str | None = None) -> None:
        with self._condition:
            if relay_token is not None:
                self._relay_token = relay_token
            if self._frame_relay is not None:
                try:
                    self._frame_relay.close()
                except Exception:
                    pass
            unix_url = _unix_relay_url(relay_base_url)
            self._frame_relay = FrameRelayClient(unix_url, token=relay_token) if unix_url else None
            if unix_url:
                self.logger.info("Frame relay enabled: %s", unix_url)
            elif relay_base_url:
                self.logger.warning("Ignoring non-unix frame relay URL: %s", relay_base_url)
            self._condition.notify_all()

    def _ensure_frame_relay_locked(self) -> None:
        if self._frame_relay is not None:
            return
        if os.environ.get("EVILEYE_MANAGED_RUN") != "1":
            return
        from evileye.api.core.internal_unix import internal_relay_target_url

        unix_url = _unix_relay_url(internal_relay_target_url())
        if not unix_url:
            return
        self._frame_relay = FrameRelayClient(unix_url, token=self._relay_token or "")
        self.logger.info("Lazy frame relay enabled: %s", unix_url)

    def submit_frame(
        self,
        frame,
        *,
        metadata: dict[str, Any] | None = None,
        objects: list[dict[str, Any]] | None = None,
        zones: list[dict[str, Any]] | None = None,
        signalization: bool = False,
    ) -> bool:
        image = getattr(frame, "image", None)
        if image is None:
            return False

        source_id = getattr(frame, "source_id", None)
        throttle_key = f"{self._pipeline_id}:{source_id}" if source_id is not None else self._pipeline_id
        if not self._should_publish(throttle_key):
            return False

        if bool(getattr(frame, "_streaming_image_owned", False)):
            image_for_encode = image
            self._stats["used_owned_images"] += 1
        else:
            try:
                image_for_encode = image.copy()
                self._stats["copied_images"] += 1
            except Exception:
                image_for_encode = image

        # Prefer explicit metadata payload; fallback to legacy args/attrs.
        metadata_payload = dict(metadata or {})
        objects_meta = (
            metadata_payload.get("objects")
            if "objects" in metadata_payload
            else (objects if objects is not None else getattr(frame, "_stream_objects", None))
        )
        zones_meta = (
            metadata_payload.get("zones")
            if "zones" in metadata_payload
            else (zones if zones is not None else getattr(frame, "_stream_zones", None))
        )
        signal_meta = bool(
            metadata_payload.get("signalization", signalization or bool(getattr(frame, "_stream_signalization", False)))
        )

        job = StreamFrameJob(
            pipeline_id=self._pipeline_id,
            image=image_for_encode,
            source_id=getattr(frame, "source_id", None),
            frame_id=getattr(frame, "frame_id", None),
            created_at=time.time(),
            objects=list(objects_meta or []),
            zones=list(zones_meta or []),
            signalization=bool(signal_meta),
            metadata=metadata_payload,
        )
        with self._condition:
            self._pending_jobs[self._job_key(job)] = job
            self._stats["submitted"] += 1
            self._condition.notify()
        return True

    def submit_full_frame(self, image, *, primary_source_id: int, source_ids: list[int] | None = None) -> bool:
        """Publish uncropped capture frame for split-editor preview.

        Broker keys: ``{pipeline}:full:{primary}`` and aliases ``{pipeline}:full:{each_id}``.

        Only publishes when there is explicit ``:full:`` demand (split editor / ``?full=true``).
        Crop/Live demand must not trigger full-frame encode — native JPEGs starve grid previews.
        """
        if image is None or primary_source_id is None:
            return False
        throttle_key = f"{self._pipeline_id}:full:{int(primary_source_id)}"
        ids = list(source_ids or []) or [int(primary_source_id)]
        if not self._should_publish(throttle_key):
            return False
        try:
            image_for_encode = image.copy()
            self._stats["copied_images"] += 1
        except Exception:
            image_for_encode = image
        job = StreamFrameJob(
            pipeline_id=self._pipeline_id,
            image=image_for_encode,
            source_id=int(primary_source_id),
            frame_id=None,
            created_at=time.time(),
            objects=[],
            zones=[],
            signalization=False,
            metadata={},
            full_frame=True,
            alias_source_ids=[int(x) for x in ids],
        )
        with self._condition:
            self._pending_jobs[f"full:{int(primary_source_id)}"] = job
            self._stats["submitted"] += 1
            self._condition.notify()
        return True

    def has_consumers(self, source_id: int | None = None) -> bool:
        throttle_key = f"{self._pipeline_id}:{source_id}" if source_id is not None else self._pipeline_id
        has_local_stream, has_server_preview_demand, has_server_process, has_relay = self._get_consumer_state(
            throttle_key)
        if has_local_stream:
            return True
        if has_server_preview_demand:
            level = self._get_preview_demand_level(throttle_key)
            return self._fps_for_demand_level(level) > 0.0
        # External OS Web UI (evileye service install): no ServerProcessManager demand queue —
        # keep publishing over HTTPS relay so Live preview works.
        if has_relay and self._publish_fps > 0.0:
            return True
        heartbeat_fps = self._get_heartbeat_fps()
        if has_server_process and heartbeat_fps > 0.0:
            return True
        return False

    def get_runtime_stats(self) -> dict:
        with self._condition:
            stats = dict(self._stats)
            stats["pending_jobs"] = len(self._pending_jobs)
            stats["worker_count"] = len(self._workers)
            return stats

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
                encode_started = time.perf_counter()
                # Keep native resolution for split-editor full frames so src_coords align.
                if job.full_frame:
                    image = job.image
                else:
                    image = _downscale_image(job.image, self._preview_max_edge)
                payload = self._encoder.encode(image)
                self._stats["last_encode_ms"] = (time.perf_counter() - encode_started) * 1000.0
                if not payload:
                    continue
                self._stats["encoded"] += 1
                self._publish_jpeg(job.pipeline_id, payload, job)
            except Exception as e:
                self._stats["publish_errors"] += 1
                self.logger.debug("Async preview publish failed: %s", e, exc_info=True)

    def _get_next_job(self) -> Optional[StreamFrameJob]:
        with self._condition:
            while not self._stop_event.is_set() and not self._pending_jobs:
                self._condition.wait(timeout=0.5)
            if self._stop_event.is_set() or not self._pending_jobs:
                return None
            oldest_key = min(
                self._pending_jobs,
                key=lambda key: self._pending_jobs[key].created_at,
            )
            return self._pending_jobs.pop(oldest_key)

    def _should_publish(self, throttle_key: str) -> bool:
        has_local_stream, has_server_preview_demand, has_server_process, has_relay = self._get_consumer_state(
            throttle_key)

        if has_local_stream:
            return self._throttle_ok(throttle_key, fps_override=self._publish_fps)

        if has_server_preview_demand:
            level = self._get_preview_demand_level(throttle_key)
            fps = self._fps_for_demand_level(level)
            if fps <= 0.0:
                return False
            return self._throttle_ok(throttle_key, fps_override=fps)

        if has_relay and self._publish_fps > 0.0:
            return self._throttle_ok(throttle_key, fps_override=self._publish_fps)

        heartbeat_fps = self._get_heartbeat_fps()
        if has_server_process and heartbeat_fps > 0.0:
            return self._throttle_ok(throttle_key, fps_override=heartbeat_fps)

        return False

    def _get_preview_demand_level(self, throttle_key: str) -> str:
        if self._server_process_manager is None:
            return "idle"
        try:
            return self._server_process_manager.get_preview_demand_level(throttle_key)
        except Exception:
            return "idle"

    def _get_heartbeat_fps(self) -> float:
        try:
            return max(0.0, float(os.getenv("EVILEYE_PREVIEW_HEARTBEAT_FPS", "0")))
        except Exception:
            return 0.0

    def _get_grid_fps(self) -> float:
        try:
            return max(0.0, float(os.getenv("EVILEYE_PREVIEW_GRID_FPS", "5.0")))
        except Exception:
            return 5.0

    def _fps_for_demand_level(self, level: str) -> float:
        if level == "stream":
            return self._publish_fps
        if level == "grid":
            return self._get_grid_fps()
        return 0.0

    def _get_consumer_state(self, throttle_key: str) -> tuple[bool, bool, bool, bool]:
        has_local_stream = False
        try:
            broker = get_frame_broker()
            has_local_stream = broker.is_stream_active(throttle_key) or broker.is_stream_active(self._pipeline_id)
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
        return has_local_stream, has_server_preview_demand, has_server_process, has_relay

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
            "ts": job.created_at,
            "source_id": job.source_id,
            "frame_id": job.frame_id,
            "content_type": "image/jpeg",
            "objects": list(job.objects or []),
            "zones": list(job.zones or []),
            "signalization": bool(job.signalization),
            "full_frame": bool(job.full_frame),
        }
        extra_meta = job.metadata or {}
        for key in ("event_labels", "event_color", "debug_rois", "overlay"):
            if key in extra_meta:
                metadata[key] = extra_meta[key]
        broker = get_frame_broker()
        if job.full_frame and job.source_id is not None:
            aliases = list(job.alias_source_ids or [job.source_id])
            for sid in aliases:
                key = f"{pipeline_id}:full:{int(sid)}"
                sid_meta = dict(metadata)
                sid_meta["source_id"] = int(sid)
                sid_meta["full_frame"] = True
                broker.publish_jpeg(key, jpeg_bytes, metadata=sid_meta)
                if self._server_process_manager is not None:
                    try:
                        # Key is already ``{pipeline}:full:{sid}``; IPC must not alias as crop.
                        self._server_process_manager.publish_frame(key, jpeg_bytes, metadata=sid_meta)
                    except Exception:
                        pass
            return
        broker.publish_jpeg(pipeline_id, jpeg_bytes, metadata=metadata)
        if job.source_id is not None:
            broker.publish_jpeg(f"{pipeline_id}:{job.source_id}", jpeg_bytes, metadata=metadata)
        if self._server_process_manager is not None:
            try:
                self._server_process_manager.publish_frame(pipeline_id, jpeg_bytes, metadata=metadata)
            except Exception:
                pass
        if self._frame_relay is not None:
            self._frame_relay.publish_jpeg(
                pipeline_id,
                jpeg_bytes,
                source_id=job.source_id,
                metadata=metadata,
            )
            return
        with self._condition:
            self._ensure_frame_relay_locked()
        if self._frame_relay is not None:
            self._frame_relay.publish_jpeg(
                pipeline_id,
                jpeg_bytes,
                source_id=job.source_id,
                metadata=metadata,
            )
