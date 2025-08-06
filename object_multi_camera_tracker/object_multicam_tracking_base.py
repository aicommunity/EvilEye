from typing import List
from abc import ABC, abstractmethod
import core
from queue import Queue
import threading
from object_tracker.tracking_results import TrackingResult, TrackingResultList

class ObjectMultiCameraTrackingBase(core.EvilEyeBase):
    ResultType = TrackingResultList

    def __init__(self):
        super().__init__()

        self.run_flag = False
        self.queue_in = Queue(maxsize=2)
        self.queue_out = Queue()
        self.source_ids = []
        self.processing_thread = threading.Thread(target=self._process_impl)

    def put(self, track_info: List[TrackingResultList]):
        if not self.queue_in.full():
            self.queue_in.put(track_info)
            return True
        
        designator = '; '.join(f"{t[0].source_id}:{t[0].frame_id}" for t in track_info)
        print(f"Failed to put tracking info {designator} to ObjectMultiCameraTrackingBase queue. Queue is Full.")
        return False

    def get(self):
        if self.queue_out.empty():
            return None
        return self.queue_out.get()

    def get_oueue_out_size(self):
        return self.queue_out.qsize()

    def get_source_ids(self):
        return self.source_ids

    def start(self):
        self.run_flag = True
        self.processing_thread.start()

    def stop(self):
        self.run_flag = False
        self.queue_in.put(None)
        self.processing_thread.join()
        print('Tracker stopped')

    @abstractmethod
    def _process_impl(self):
        pass
