from abc import abstractmethod
from queue import Queue
import threading
import time
from time import sleep
from .object_detection_base import DetectionResultList
from .object_detection_base import DetectionResult
from ..capture.video_capture_base import CaptureImage
from timeit import default_timer as timer
import logging

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

    def __init__(self, stride: int, classes: list, source_ids: list, roi: list, inf_params: dict, queue_out: Queue, logger_name: str | None = None, parent_logger: logging.Logger | None = None):
        super().__init__()
        base_name = "evileye.detection_thread"
        full_name = f"{base_name}.{logger_name}" if logger_name else base_name
        self.logger = parent_logger or logging.getLogger(full_name)

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
        self.model_class_mapping = None

    def start(self):
        self.run_flag = True
        self.processing_thread.start()

    def stop(self):
        self.run_flag = False
        if self.processing_thread.is_alive():
            self.processing_thread.join()
        self.logger.info('Detection thread stopped')

    def put(self, image: CaptureImage, force=False):
        dropped_id = []
        if not self.run_flag:
            self.logger.warning(f"Detection thread not started. Put ignored for {image.source_id}:{image.frame_id}")
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

    def get_model_class_mapping(self) -> dict|None:
        return self.model_class_mapping
    
    def _update_model_class_mapping_from_model(self):
        """Update model_class_mapping from loaded model (to be implemented in subclasses)"""
        pass

    def _process_impl(self):
        while self.run_flag:
            self.init_detection_implementation()
            try:
                if not self.queue_in.empty():
                    image = self.queue_in.get()
                else:
                    image = None
            except ValueError as ex:
                self.logger.error(f"Exception in detection thread: _process_impl: {ex}")

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
            # self.logger.debug(f'TIME: {finish_it - start_it}')

    def process_stride(self, split_image):
        bboxes_coords = []
        confidences = []
        class_ids = []
        detection_result_list = DetectionResultList()

        images = []
        for img in split_image:
            images.append(img[0].image)
        # Pass sensible classes to model (IDs only) to avoid Ultralytics errors
        classes_arg = self._get_classes_arg_for_model()
        predict_results = self.predict(images) if classes_arg is None else self.predict(images)

        for i in range(len(split_image)):
            roi_bboxes, roi_confs, roi_ids = self.get_bboxes(predict_results[i], split_image[i])
            confidences.extend(roi_confs)
            class_ids.extend(roi_ids)
            bboxes_coords.extend(roi_bboxes)

        utils_module = get_utils()
        bboxes_coords, confidences, class_ids = utils_module.merge_roi_boxes(self.roi[0], bboxes_coords, confidences, class_ids)  # Объединение рамок из разных ROI
        bboxes_coords, confidences, class_ids = utils_module.non_max_sup(bboxes_coords, confidences, class_ids)

        # Centralized filtering by classes (IDs or names via model_class_mapping)
        bboxes_coords, confidences, class_ids = self._filter_detections(bboxes_coords, confidences, class_ids)

        detection_result_list.source_id = split_image[0][0].source_id
        detection_result_list.time_stamp = time.time()
        detection_result_list.frame_id = split_image[0][0].frame_id

        for bbox, class_id, conf in zip(bboxes_coords, class_ids, confidences):
            detection_result = DetectionResult()
            detection_result.bounding_box = [int(x) for x in bbox]
            detection_result.class_id = int(class_id)
            detection_result.confidence = conf
            detection_result_list.detections.append(detection_result)
        return detection_result_list

    def _get_classes_arg_for_model(self):
        """Return list of class IDs to pass into model or None if not applicable.
        Avoid passing string names into Ultralytics models.
        """
        try:
            if isinstance(self.classes, list) and self.classes and all(isinstance(c, int) for c in self.classes):
                return self.classes
            # If classes are names, we don't pass them to model to avoid errors
            return None
        except Exception:
            return None

    def _filter_detections(self, bboxes_coords, confidences, class_ids):
        """Apply class filtering by IDs or names using model_class_mapping.
        - If self.classes is list[int]: filter by IDs
        - If self.classes is list[str] and model_class_mapping is available: map names->IDs and filter
        - Otherwise: no filtering
        """
        try:
            if not isinstance(self.classes, list) or not self.classes:
                return bboxes_coords, confidences, class_ids

            # Filter by IDs directly
            if all(isinstance(c, int) for c in self.classes):
                desired_ids = set(self.classes)
            # Filter by names via mapping
            elif all(isinstance(c, str) for c in self.classes) and isinstance(self.model_class_mapping, dict) and self.model_class_mapping:
                desired_ids = {cid for name, cid in self.model_class_mapping.items() if name in self.classes}
                if not desired_ids:
                    return [], [], []
            else:
                return bboxes_coords, confidences, class_ids

            fb, fc, fi = [], [], []
            for b, c, i in zip(bboxes_coords, confidences, class_ids):
                cid = int(i)
                if cid in desired_ids:
                    fb.append(b)
                    fc.append(c)
                    fi.append(cid)
            return fb, fc, fi
        except Exception:
            return bboxes_coords, confidences, class_ids

    @abstractmethod
    def init_detection_implementation(self):
        pass

    @abstractmethod
    def predict(self, images: list):
        pass

    @abstractmethod
    def get_bboxes(self, result, roi):
        pass
