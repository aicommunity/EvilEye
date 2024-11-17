# from torch.multiprocessing.queue import Queue
from queue import Queue
import threading
from ultralytics import YOLO
from utils import utils
import object_detector
import time
from time import sleep
from object_detector.object_detection_base import DetectionResultList
from object_detector.object_detection_base import DetectionResult
from capture.video_capture_base import CaptureImage
from object_detector.detection_thread_yolo import DetectionThreadYolo



class ObjectDetectorYoloV8(object_detector.ObjectDetectorBase):
    id_cnt = 0  # Переменная для присвоения каждому детектору своего идентификатора

    def __init__(self):
        super().__init__()

        #self.objects = []
        self.model_name = None
        self.prev_time = 0  # Для параметра скважности, заданного временем; отсчет времени
        self.stride = 1  # Параметр скважности
        self.stride_cnt = self.stride  # Счетчик для кадров, которые необходимо пропустить
        self.num_detection_threads = 3
#        self.id = ObjectDetectorYoloV8.id_cnt  # ID детектора
        self.roi = [[]]
#        ObjectDetectorYoloV8.id_cnt += 1
#        print(self.id)
        self.detection_threads = []
        self.thread_counter = 0


    def init_impl(self):
        self.detection_threads = []
        inf_params = {"show": self.params['show'], 'conf': self.params['conf'], 'save': self.params['save']}

        for i in range(self.num_detection_threads):
            thread = DetectionThreadYolo(self.model_name, self.source_ids, self.roi, inf_params, self.queue_out)
            thread.start()
            self.detection_threads.append(thread)
        return True

    def release_impl(self):
        for i in range(self.num_detection_threads):
            self.detection_threads[i].stop()
        self.detection_threads = []

    def reset_impl(self):
        pass

    def set_params_impl(self):
        self.model_name = self.params['model']
        self.stride = self.params.get('vid_stride', 1)
        self.stride_cnt = self.stride
        self.source_ids = self.params.get('source_ids', [])
        self.num_detection_threads = self.params.get('num_detection_threads', 3)
        self.roi = self.params.get('roi', [[]])

    def default(self):
        self.model_name = None
        self.stride = 1
        self.stride_cnt = self.stride
        self.params.clear()

    def _process_impl(self):
        while self.run_flag:
            sleep(0.01)
            try:
                if not self.queue_in.empty():
                    image = self.queue_in.get()
                else:
                    image = None
            except ValueError:
                break
            if not image:
                continue

            self.detection_threads[self.thread_counter].put(image)
            self.thread_counter += 1
            if self.thread_counter >= self.num_detection_threads:
                self.thread_counter = 0

