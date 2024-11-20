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

        # self.objects = []
        self.model_name = None
        self.classes = []
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
        inf_params = {"show": self.params.get('show', False), 'conf': self.params.get('conf', 0.25),
                      'save': self.params.get('save', False), "imgsz": self.params.get('inference_size', 640),
                      "device": self.params.get('device', None)}

        for i in range(self.num_detection_threads):
            thread = DetectionThreadYolo(self.model_name, self.classes, self.source_ids, self.roi, inf_params,
                                         self.queue_out)
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
        self.classes = self.params['classes']
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
            if not self.is_inited:
                sleep(0.01)
                continue

            image = self.queue_in.get()
            if not image:
                continue

            if not self.detection_threads[self.thread_counter].put(image, force=True):
                print(
                    f"Failed to put image {image.source_id}:{image.frame_id} to detection thread {self.thread_counter}")
            self.thread_counter += 1
            if self.thread_counter >= self.num_detection_threads:
                self.thread_counter = 0
            '''
            is_image_put = False
            for i in range(self.num_detection_threads):
                if self.detection_threads[self.thread_counter].put(image):
                    is_image_put = True
                    self.thread_counter += 1
                    if self.thread_counter >= self.num_detection_threads:
                        self.thread_counter = 0
                    break
                else:
                    self.thread_counter += 1
                    if self.thread_counter >= self.num_detection_threads:
                        self.thread_counter = 0


            if not is_image_put:
                print(f"Failed to put image {image.source_id}:{image.frame_id} to detection thread")
            '''
