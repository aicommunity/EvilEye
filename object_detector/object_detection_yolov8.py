import cv2
import numpy as np
import ultralytics
from ultralytics import YOLO
from utils import utils
import object_detector
import threading
from threading import Thread
import time


class ObjectDetectorYoloV8(object_detector.ObjectDetectorBase):
    def __init__(self):
        super().__init__()
        self.bboxes_coords = []
        self.confidences = []
        self.class_ids = []
        self.is_actual = []  # Флаг, показывающий актуальная рамка или нет
        self.model_name = None
        self.model = None
        self.prev_time = 0  # Для параметра скважности, заданного временем; отсчет времени
        self.stride = 1  # Параметр скважности
        self.stride_cnt = self.stride  # Счетчик для кадров, которые необходимо пропустить

    def init_impl(self):
        self.model = YOLO(self.model_name)
        return True

    def reset_impl(self):
        pass

    def set_params_impl(self):
        self.model_name = self.params['model']
        self.stride = self.params.get('vid_stride', 1)
        self.stride_cnt = self.stride

    def default(self):
        self.model_name = None
        self.model = None
        self.stride = 1
        self.stride_cnt = self.stride
        self.params.clear()

    def process_impl(self, image, all_roi):
        if not all_roi:
            roi = [[image, [0, 0]]]
        else:
            roi = utils.create_roi(image, all_roi)  # Приводим ROI к виду, необходимому для функции детекции
        if self.params.get('stride_type', 'frames') == "time":  # В зависимости от параметра скважности запускаем соответствующую функцию
            bboxes_coords, confidences, class_ids, is_actual = self.process_time_stride(image, roi)
        else:
            bboxes_coords, confidences, class_ids, is_actual = self.process_frame_stride(image, roi)
        self.draw_boxes(image, self.bboxes_coords[-1], self.confidences[-1], self.class_ids[-1])
        return bboxes_coords, confidences, class_ids, is_actual

    def process_time_stride(self, image, all_roi):
        bboxes_coords = []
        confidences = []
        class_ids = []
        is_actual = False
        inf_params = {"show": self.params['show'], 'conf': self.params['conf'], 'save': self.params['save']}
        curr_time = int(time.time() * 1000)
        if curr_time - self.prev_time >= self.stride:  # Если прошло нужное количество времени, запускаем детекцию
            self.prev_time = curr_time
            for roi in all_roi:
                results = self.model(source=roi[0], **inf_params)
                if len(results[0]) == 0:  # Если детекций не было, пропускаем
                    continue
                bboxes_coord, confidence, class_id = self.get_bboxes(results[0], roi)  # Получаем координаты рамок на изображении
                confidences.extend(confidence)
                class_ids.extend(class_id)
                bboxes_coords.extend(bboxes_coord)
            bboxes_coords, confidences, class_ids = utils.non_max_sup(bboxes_coords, confidences, class_ids)
            bboxes_coords, confidences, class_ids = utils.merge_roi_boxes(self.params['roi'][0], bboxes_coords, confidences, class_ids)  # Объединение рамок из разных ROI
            is_actual = True
            self.confidences.append(confidences)
            self.class_ids.append(class_ids)
            self.bboxes_coords.append(bboxes_coords)
            self.is_actual.append(is_actual)
        else:
            is_actual = False
            self.bboxes_coords.append(self.bboxes_coords[-1])
            self.class_ids.append(self.class_ids[-1])
            self.confidences.append(self.confidences[-1])
            self.is_actual.append(is_actual)
        return bboxes_coords, confidences, class_ids, is_actual

    def process_frame_stride(self, image, all_roi):
        bboxes_coords = []
        confidences = []
        class_ids = []
        is_actual = False
        inf_params = {"show": self.params['show'], 'conf': self.params['conf'], 'save': self.params['save']}
        if self.stride_cnt == self.stride:  # Если пропущено указанное количество кадров, запускаем детекцию
            self.stride_cnt = 1
            for roi in all_roi:
                results = self.model(source=roi[0], **inf_params)
                if len(results[0]) == 0:  # Если детекций не было, пропускаем
                    continue
                bboxes_coord, confidence, class_id = self.get_bboxes(results[0], roi)  # Получаем координаты рамок на изображении
                confidences.extend(confidence)
                class_ids.extend(class_id)
                bboxes_coords.extend(bboxes_coord)
            bboxes_coords, confidences, class_ids = utils.non_max_sup(bboxes_coords, confidences, class_ids)
            bboxes_coords, confidences, class_ids = utils.merge_roi_boxes(self.params['roi'][0], bboxes_coords, confidences, class_ids)  # Объединение рамок из разных ROI
            is_actual = True
            self.confidences.append(confidences)
            self.class_ids.append(class_ids)
            self.bboxes_coords.append(bboxes_coords)
            self.is_actual.append(is_actual)
        else:
            is_actual = False
            self.stride_cnt += 1
            self.bboxes_coords.append(self.bboxes_coords[-1])
            self.class_ids.append(self.class_ids[-1])
            self.confidences.append(self.confidences[-1])
            self.is_actual.append(is_actual)
        return bboxes_coords, confidences, class_ids, is_actual

    def draw_boxes(self, image, bboxes_coords, confidences, class_ids):
        for coord, class_id, conf in zip(bboxes_coords, class_ids, confidences):
            cv2.rectangle(image, (int(coord[0]), int(coord[1])),
                          (int(coord[2]), int(coord[3])), (0, 255, 0), thickness=8)
            cv2.putText(image, str(self.model.names[class_id]) + " " + "{:.2f}".format(conf),
                        (int(coord[0]), int(coord[1]) - 10), cv2.FONT_HERSHEY_SIMPLEX, 1,
                        (255, 255, 255), 2)

    def get_bboxes(self, result, roi):
        bboxes_coords = []
        confidences = []
        ids = []
        boxes = result.boxes.cpu().numpy()
        coords = boxes.xyxy
        confs = boxes.conf
        class_ids = boxes.cls
        for coord, class_id, conf in zip(coords, class_ids, confs):
            if self.model.names[class_id] not in ['car', 'truck', 'bus', 'person']:
                continue
            abs_coords = utils.roi_to_image(coord, roi[1][0], roi[1][1])  # Получаем координаты рамки в СК всего изображения
            bboxes_coords.append(abs_coords)
            confidences.append(conf)
            ids.append(class_id)
        return bboxes_coords, confidences, ids
