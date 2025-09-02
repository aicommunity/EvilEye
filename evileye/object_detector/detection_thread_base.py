from abc import abstractmethod
from queue import Queue
import threading
import time
from time import sleep
from .object_detection_base import DetectionResultList
from .object_detection_base import DetectionResult
from ..capture.video_capture_base import CaptureImage
from timeit import default_timer as timer

# Import utils later to avoid circular imports
utils = None

def get_utils():
    global utils
    if utils is None:
        from evileye.utils import utils as utils_module
        utils = utils_module
    return utils


class DetectionThreadBase:
    id_cnt = 0  # Переменная для присвоения каждому детектору своего идентификатора

    def __init__(self, stride: int, classes: list, source_ids: list, roi: list, inf_params: dict, queue_out: Queue):
        super().__init__()

        self.prev_time = 0  # Для параметра скважности, заданного временем; отсчет времени
        self.stride = stride  # Параметр скважности
        self.stride_cnt = self.stride  # Счетчик для кадров, которые необходимо пропустить
        self.classes = classes
        self.roi = roi  # [[]]
        self.inf_params = inf_params
        self.run_flag = False
        self.queue_in = Queue(maxsize=2)
        self.queue_out = queue_out
        self.source_ids = source_ids
        self.processing_thread = threading.Thread(target=self._process_impl)
        self.roi_coords_per_camera = {source_id: roi_coords for source_id, roi_coords in zip(self.source_ids, self.roi)}

    def start(self):
        self.run_flag = True
        self.processing_thread.start()

    def stop(self):
        self.run_flag = False
        if self.processing_thread.is_alive():
            self.processing_thread.join()
        print('Detection thread stopped')

    def put(self, image: CaptureImage, force=False):
        dropped_id = []
        if not self.run_flag:
            print(f"Detection thread doesn't started. Put ignored for {image.source_id}:{image.frame_id}")
        if self.queue_in.full():
            if force:
                dropped_image = self.queue_in.get()
                dropped_id.append(dropped_image.source_id)
                dropped_id.append(dropped_image.frame_id)
            else:
                dropped_id.append(image.source_id)
                dropped_id.append(image.frame_id)
                return False, dropped_id
        self.queue_in.put(image)
        return True, dropped_id

    def _process_impl(self):
        while self.run_flag:
            self.init_detection_implementation()
            try:
                if not self.queue_in.empty():
                    image = self.queue_in.get()
                else:
                    image = None
            except ValueError as ex:
                print(f"Exception in detection thread: _process_impl: {ex}")

                break
            if not image:
                sleep(0.01)
                continue

            if not self.roi[0]:
                split_image = [[image, [0, 0]]]
            else:
                coords = self.roi_coords_per_camera[image.source_id]
                utils_module = get_utils()
                split_image = utils_module.create_roi(image, coords)
            detection_result_list = self.process_stride(split_image)
            if detection_result_list:
                self.queue_out.put([detection_result_list, image])
            # finish_it = timer()
            # print(f'TIME: {finish_it - start_it}')

    def process_stride(self, split_image):
        bboxes_coords = []
        confidences = []
        class_ids = []
        detection_result_list = DetectionResultList()

        images = []
        for img in split_image:
            images.append(img[0].image)
        predict_results = self.predict(images)

        for i in range(len(split_image)):
            roi_bboxes, roi_confs, roi_ids = self.get_bboxes(predict_results[i], split_image[i])
            confidences.extend(roi_confs)
            class_ids.extend(roi_ids)
            bboxes_coords.extend(roi_bboxes)

        utils_module = get_utils()
        bboxes_coords, confidences, class_ids = utils_module.merge_roi_boxes(self.roi[0], bboxes_coords, confidences, class_ids)  # Объединение рамок из разных ROI
        bboxes_coords, confidences, class_ids = utils_module.non_max_sup(bboxes_coords, confidences, class_ids)

        detection_result_list.source_id = split_image[0][0].source_id
        detection_result_list.time_stamp = time.time()
        detection_result_list.frame_id = split_image[0][0].frame_id

        for bbox, class_id, conf in zip(bboxes_coords, class_ids, confidences):
            detection_result = DetectionResult()
            detection_result.bounding_box = bbox
            detection_result.class_id = class_id
            detection_result.confidence = conf
            detection_result_list.detections.append(detection_result)
        return detection_result_list

    @abstractmethod
    def init_detection_implementation(self):
        pass

    @abstractmethod
    def predict(self, images: list):
        pass

    @abstractmethod
    def get_bboxes(self, result, roi):
        pass
