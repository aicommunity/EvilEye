from abc import ABC, abstractmethod
import cv2
import numpy as np
import ultralytics
from ultralytics import YOLO


class ObjectDetector(ABC):

    @abstractmethod
    def detect(self, image, roi, show, conf, save):
        pass


class YoloV8ObjectDetector(ObjectDetector):
    def __init__(self, model_name):
        self.model = YOLO(model_name)

    def detect(self, image, all_roi, show, conf, save):
        bboxes_coords = []
        confidences = []
        class_ids = []
        for roi in all_roi:
            results = self.model(source=roi[0], show=show, conf=conf, save=save)
            if len(results[0]) == 0:  # Если детекций не было, пропускаем
                continue
            for result in results:
                bboxes_coord, confidence, class_id = self.get_bboxes(result, roi)  # Получаем координаты рамок на изображении
                confidences.extend(confidence)
                class_ids.extend(class_id)
                bboxes_coords.extend(bboxes_coord)
        bboxes_coords, confidences, class_ids = non_max_sup(bboxes_coords, confidences, class_ids)
        self.draw_boxes(image, bboxes_coords, confidences, class_ids)
        return bboxes_coords, confidences, class_ids

    def draw_boxes(self, image, bboxes_coords, confidences, class_ids):
        for coord, class_id, conf in zip(bboxes_coords, class_ids, confidences):
            cv2.rectangle(image, (int(coord[0]), int(coord[1])),
                          (int(coord[2]), int(coord[3])), (0, 255, 0))
            cv2.putText(image, str(self.model.names[class_id]) + " " + "{:.2f}".format(conf),
                                (int(coord[0]), int(coord[1]) - 10), cv2.FONT_HERSHEY_SIMPLEX, 1,
                                (255, 255, 255), 2)

    def get_bboxes(self, result, roi):
        bboxes_coords = []
        confidences = []
        ids = []
        boxes = result.boxes.numpy()
        coords = boxes.xyxy
        confs = boxes.conf
        class_ids = boxes.cls
        for coord, class_id, conf in zip(coords, class_ids, confs):
            if self.model.names[class_id] not in ['car', 'truck', 'bus', 'person']:
                continue
            abs_coords = self.rel_to_abs(coord, roi[1][0], roi[1][1])  # Получаем координаты рамки в СК всего изображения
            bboxes_coords.append(abs_coords)
            confidences.append(conf)
            ids.append(class_id)
        return bboxes_coords, confidences, ids

    @staticmethod
    def rel_to_abs(coords, x0, y0):
        abs_coords = [x0 + int(coords[0]), y0 + int(coords[1]), x0 + int(coords[2]), y0 + int(coords[3])]
        return abs_coords


def non_max_sup(boxes_coords, confidences, class_ids):
    confidences = np.array(confidences, dtype='float64')
    boxes_coords = np.array(boxes_coords, dtype='float64')
    class_ids = np.array(class_ids, dtype='float64')
    sorted_idxs = np.argsort(confidences)
    iou_thresh = 0.3
    keep_idxs = []
    while len(sorted_idxs) > 0:
        last = len(sorted_idxs) - 1
        suppress_idxs = [last]  # Индекс рамки с наибольшей вероятностью
        keep_idxs.append(sorted_idxs[last])
        for i in range(len(sorted_idxs) - 1):
            idx = sorted_idxs[i]
            iou = boxes_iou(boxes_coords[sorted_idxs[last]], boxes_coords[idx])
            if iou > iou_thresh: # Если iou превышает порог, то добавляем данную рамку на удаление
                suppress_idxs.append(i)
        sorted_idxs = np.delete(sorted_idxs, suppress_idxs)
    boxes_coords = boxes_coords[keep_idxs].tolist()
    class_ids = class_ids[keep_idxs].tolist()
    confidences = confidences[keep_idxs].tolist()
    return boxes_coords, confidences, class_ids


def boxes_iou(box1, box2):
    if (((box1[0] <= box2[0] and box1[1] <= box2[1]) and (box2[2] <= box1[2] and box2[3] <= box1[3])) or  # Находится ли один bbox внутри другого
            ((box2[0] <= box1[0] and box2[1] <= box1[1]) and (box1[2] <= box2[2] and box1[3] <= box2[3]))):
        return 1.0
    x_left = max(box1[0], box2[0])
    y_top = max(box1[1], box2[1])
    x_right = min(box1[2], box2[2])
    y_bottom = min(box1[3], box2[3])
    if x_right - x_left + 1 <= 0 or y_bottom - y_top + 1 <= 0:  # Если рамки никак не пересекаются
        return -1.0
    area1 = (box1[2] - box1[0] + 1) * (box1[3] - box1[1] + 1)
    area2 = (box2[2] - box2[0] + 1) * (box2[3] - box2[1] + 1)
    intersection = (x_right - x_left + 1) * (y_bottom - y_top + 1)
    iou = intersection / float(area1 + area2 - intersection)
    return iou
