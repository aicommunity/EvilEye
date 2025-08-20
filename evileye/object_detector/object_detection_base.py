from abc import ABC

from ..core.frame import CaptureImage

from ..core.base_class import EvilEyeBase
from queue import Queue
import threading
from time import sleep


class DetectionResult:
    def __init__(self):
        self.bounding_box = []
        self.confidence = 0.0
        self.class_id = None
        self.detection_data = dict()  # internal detection data


class DetectionResultList:
    def __init__(self):
        self.source_id = None
        self.frame_id = None
        self.time_stamp = None
        self.detections: list[DetectionResult] = []


class ObjectDetectorBase(EvilEyeBase, ABC):
    ResultType = DetectionResultList

    def __init__(self):
        super().__init__()

        self.run_flag = False
        self.queue_in = Queue(maxsize=2)
        self.queue_out = Queue()
        self.source_ids = []
        self.classes = []
        self.stride = 1  # Параметр скважности
        self.roi = [[]]
        self.queue_dropped_id = Queue()

        self.num_detection_threads = 3
        self.detection_threads = []
        self.thread_counter = 0

        self.processing_thread = None

    def put(self, image: CaptureImage) -> bool:
        if not self.queue_in.full():
            self.queue_in.put(image)
            return True
        print(f"Failed to put image {image.source_id}:{image.frame_id} to ObjectDetection queue. Queue is Full.")
        return False

    def get(self):
        if self.queue_out.empty():
            return None
        return self.queue_out.get()

    def get_dropped_ids(self) -> list:
        res = []
        while not self.queue_dropped_id.empty():
            res.append(self.queue_dropped_id.get())
        return res

    def get_queue_out_size(self) -> int:
        return self.queue_out.qsize()

    def get_source_ids(self) -> list:
        return self.source_ids

    def set_params_impl(self):
        super().set_params_impl()
        self.roi = self.params.get('roi', [[]])
        self.classes = self.params.get('classes', [])
        self.stride = self.params.get('vid_stride', 1)
        self.source_ids = self.params.get('source_ids', [])
        self.num_detection_threads = self.params.get('num_detection_threads', 3)

    def get_params_impl(self):
        params = dict()
        params['roi'] = self.roi
        params['classes'] = self.classes
        params['vid_stride'] = self.stride
        params['source_ids'] = self.source_ids
        params['num_detection_threads'] = self.num_detection_threads
        return params

    def get_debug_info(self, debug_info: dict):
        super().get_debug_info(debug_info)
        debug_info['run_flag'] = self.run_flag
        debug_info['roi'] = self.roi
        debug_info['classes'] = self.classes
        debug_info['source_ids'] = self.source_ids

    def start(self):
        self.run_flag = True
        if self.processing_thread:
            self.processing_thread.start()

    def stop(self):
        self.run_flag = False
        self.queue_in.put(None)
        # self.queue_in.put('STOP')
        if self.processing_thread and self.processing_thread.is_alive():
            self.processing_thread.join()
        print('Detection stopped')

    def init_impl(self):
        self.processing_thread = threading.Thread(target=self._process_impl)

    def release_impl(self):
        for i in range(len(self.detection_threads)):
            self.detection_threads[i].stop()

        self.detection_threads = []
        del self.processing_thread
        self.processing_thread = None

    def default(self):
        self.stride = 1

    def reset_impl(self):
        pass

    def _process_impl(self):
        while self.run_flag:
            if not self.is_inited:
                sleep(0.01)
                continue

            image = self.queue_in.get()
            if not image:
                continue

            res, dropped_id = self.detection_threads[self.thread_counter].put(image, force=True)
            if dropped_id:
                self.queue_dropped_id.put(dropped_id)
            self.thread_counter += 1
            if self.thread_counter >= self.num_detection_threads:
                self.thread_counter = 0
