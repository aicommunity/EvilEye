from abc import ABC, abstractmethod
from queue import Queue
import threading
from time import sleep
from ..core.base_class import EvilEyeBase
from ..core.frame import Frame


class PreprocessingBase(EvilEyeBase):
    ResultType = Frame
    def __init__(self):
        super().__init__()

        self.run_flag = False
        self.queue_in = Queue(maxsize=2)
        self.queue_out = Queue()
        self.source_ids = []
        self.processing_thread = threading.Thread(target=self._process_impl)

    def set_params_impl(self):
        self.source_ids = self.params.get('source_ids', [])

    def get_params_impl(self):
        params = dict()
        params['source_ids'] = self.source_ids
        return params

    def put(self, det_info):
        if not self.queue_in.full():
            self.queue_in.put(det_info)
            return True
        else:
            old_info = self.queue_in.get()
            print(f"Preprocessing queue for {det_info.source_id} is full. Remove oldest frame {old_info.frame_id}")
        return False

    def get(self):
        if self.queue_out.empty():
            return None
        return self.queue_out.get()

    def get_queue_out_size(self):
        return self.queue_out.qsize()

    def get_source_ids(self):
        return self.source_ids

    def start(self):
        self.run_flag = True
        self.processing_thread.start()

    def stop(self):
        self.run_flag = False
        self.queue_in.put(None)
        if self.processing_thread.is_alive():
            self.processing_thread.join()
        print('Tracker stopped')

    def _process_impl(self):
        while self.run_flag:
            sleep(0.01)
            image = self.queue_in.get()
            if image is None:
                continue
            preprocessed_image = self._process_image(image)
            self.queue_out.put(preprocessed_image)

    @abstractmethod
    def _process_image(self, image):
        pass
