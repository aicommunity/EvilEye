from abc import ABC, abstractmethod
from dataclasses import dataclass
import threading
from queue import Empty, Queue
from typing import Any, Optional, Tuple

from ..core.base_class import EvilEyeBase
from .tracking_results import TrackingResultList


@dataclass
class DroppedFrameInfo:
    """Information about a dropped frame due to queue overflow."""

    source_id: int
    frame_id: int


class ObjectTrackingBase(EvilEyeBase):
    ResultType = TrackingResultList

    def __init__(self):
        super().__init__()

        self.run_flag = False
        # Default size increased from 2 to reduce drops under load.
        self.queue_in = Queue(maxsize=10)
        self.queue_out = Queue()
        self.queue_dropped_id = Queue()
        self.source_ids = []
        self.processing_thread = None

    def put(self, det_info: Tuple[Any, Any], force: bool = False) -> bool:
        dropped_info: Optional[DroppedFrameInfo] = None
        result = True
        if self.queue_in.full():
            if force:
                dropped_data = self.queue_in.get()
                dropped_info = DroppedFrameInfo(
                    source_id=dropped_data[1].source_id,
                    frame_id=dropped_data[1].frame_id,
                )
                result = True
            else:
                dropped_info = DroppedFrameInfo(
                    source_id=det_info[1].source_id,
                    frame_id=det_info[1].frame_id,
                )
                result = False
        if dropped_info is not None:
            self.queue_dropped_id.put(dropped_info)

        if result:
            self.queue_in.put(det_info)

        return result

    def get(self) -> Optional[Any]:
        """Get item from output queue without race conditions."""
        try:
            return self.queue_out.get_nowait()
        except Empty:
            return None

    def get_dropped_ids(self) -> list[DroppedFrameInfo]:
        res = []
        while not self.queue_dropped_id.empty():
            res.append(self.queue_dropped_id.get())
        return res

    def get_queue_out_size(self) -> int:
        return self.queue_out.qsize()

    def get_source_ids(self):
        return self.source_ids

    def start(self):
        self.run_flag = True
        self.processing_thread.start()

    def stop(self):
        self.run_flag = False
        self.queue_in.put(None)
        if self.processing_thread and self.processing_thread.is_alive():
            self.processing_thread.join()
        self.logger.info('Tracker stopped')

    def init_impl(self, **kwargs):
        # Allow overriding input queue size via params.
        queue_size = self.params.get("queue_size", self.queue_in.maxsize)
        if isinstance(queue_size, int) and queue_size > 0 and queue_size != self.queue_in.maxsize:
            self.queue_in = Queue(maxsize=queue_size)

        self.processing_thread = threading.Thread(target=self._process_impl)

    def release_impl(self):
        del self.processing_thread
        self.processing_thread = None

    @abstractmethod
    def _process_impl(self):
        pass
