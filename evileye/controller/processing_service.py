"""Helpers for the Controller main processing loop."""

from __future__ import annotations

import time
from timeit import default_timer as timer
from typing import Any, List, Optional, Sequence, Tuple


class ProcessingService:
    """Stateless helpers extracted from Controller.run() for readability and testing."""

    @staticmethod
    def should_log_resource_stats(
        last_ts: float,
        interval_sec: float,
        now_ts: Optional[float] = None,
    ) -> bool:
        now = now_ts if now_ts is not None else time.time()
        every = float(interval_sec or 0.0)
        if every <= 0:
            return False
        return last_ts <= 0 or (now - last_ts) >= every

    @staticmethod
    def compute_loop_sleep_seconds(target_fps: Optional[float], elapsed_seconds: float) -> float:
        if target_fps:
            sleep_seconds = 1.0 / float(target_fps) - elapsed_seconds
            if sleep_seconds <= 0.0:
                return 0.001
            return sleep_seconds
        return 0.03

    @staticmethod
    def collect_processing_frames(
        vis_frames: Optional[Sequence],
        fallback_frames: Optional[Sequence],
    ) -> List[Any]:
        processing_frames: List[Any] = []
        try:
            for item in vis_frames or []:
                if isinstance(item, (tuple, list)) and len(item) == 2:
                    _, img = item
                    processing_frames.append(img)
                else:
                    processing_frames.append(item)
        except Exception:
            processing_frames = []
        if not processing_frames and fallback_frames:
            processing_frames = list(fallback_frames)
        return processing_frames

    @staticmethod
    def perf_diag_timers(enabled: bool) -> Tuple[Optional[float], ...]:
        if not enabled:
            return (None, None, None, None, None, None)
        return (timer(), timer(), timer(), timer(), timer(), timer())
