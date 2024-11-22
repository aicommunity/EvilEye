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


class DetectionThreadYolo:
    id_cnt = 0  # Переменная для присвоения каждому детектору своего идентификатора

    def __init__(self, model_name: str, classes: list, source_ids: list, roi: list, inf_params: dict, queue_out: Queue):
        super().__init__()

        #self.objects = []
        self.model_name = model_name
        self.model = None
        self.prev_time = 0  # Для параметра скважности, заданного временем; отсчет времени
        self.stride = 1  # Параметр скважности
        self.stride_cnt = self.stride  # Счетчик для кадров, которые необходимо пропустить
        self.classes = classes
        self.roi = roi #[[]]
        self.inf_params = inf_params
        self.run_flag = False
        self.queue_in = Queue(maxsize=2)
        self.queue_out = queue_out
        self.source_ids = source_ids
        self.processing_thread = threading.Thread(target=self._process_impl)

    def start(self):
        self.run_flag = True
        self.processing_thread.start()

    def stop(self):
        self.run_flag = False
        self.processing_thread.join()
        print('Detection stopped')

    def put(self, image, force=False):
        if not self.run_flag:
            print(f"Detection thread doesn't started. Put ignored for {image.source_id}:{image.frame_id}")

        if self.queue_in.full():
            if force:
                self.queue_in.get()
            else:
                return False
        self.queue_in.put(image)
        return True

    def _process_impl(self):
        while self.run_flag:
            if self.model is None:
                self.model = YOLO(self.model_name)
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
                roi_idx = self.source_ids.index(image.source_id)
                split_image = utils.create_roi(image, self.roi[roi_idx])
            detection_result_list = self.process_stride(split_image)
            if detection_result_list:
                self.queue_out.put([detection_result_list, image])

    def process_stride(self, split_image):
        bboxes_coords = []
        confidences = []
        class_ids = []
        detection_result_list = DetectionResultList()

        images = []
        for img in split_image:
            images.append(img[0].image)
        yolo_results = self.model.predict(source=images, classes=self.classes, verbose=False, **self.inf_params)

        for i in range(len(split_image)):
            roi_bboxes, roi_confs, roi_ids = self.get_bboxes(yolo_results[i], split_image[i])
            confidences.extend(roi_confs)
            class_ids.extend(roi_ids)
            bboxes_coords.extend(roi_bboxes)

        bboxes_coords, confidences, class_ids = utils.merge_roi_boxes(self.roi[0], bboxes_coords, confidences, class_ids)  # Объединение рамок из разных ROI
        bboxes_coords, confidences, class_ids = utils.non_max_sup(bboxes_coords, confidences, class_ids)

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

    def get_bboxes(self, result, roi):
        bboxes_coords = []
        confidences = []
        ids = []
        boxes = result.boxes.cpu().numpy()
        coords = boxes.xyxy
        confs = boxes.conf
        class_ids = boxes.cls
        for coord, class_id, conf in zip(coords, class_ids, confs):
            if int(class_id) not in self.classes:
                continue
            abs_coords = utils.roi_to_image(coord, roi[1][0], roi[1][1])  # Получаем координаты рамки в СК всего изображения
            bboxes_coords.append(abs_coords)
            confidences.append(conf)
            ids.append(class_id)
        return bboxes_coords, confidences, ids
